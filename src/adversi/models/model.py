"""``Model``: a configured handle to one model on one provider.

``Model`` owns everything that is not vendor-specific: retries with backoff,
timeouts, concurrency and rate limits, response caching, token/cost accounting and
budget enforcement. Providers only translate wire formats.
"""

from __future__ import annotations

import asyncio
import random
import time
import weakref
from collections.abc import AsyncIterator, Sequence
from typing import Any

from adversi._sync import run_blocking
from adversi.errors import ConfigurationError, ProviderError, ProviderTimeoutError
from adversi.models.cache import ResponseCache, request_key
from adversi.models.pricing import Price
from adversi.models.ratelimit import RateLimiter
from adversi.observability.usage import current_tracker
from adversi.providers.base import Message, ModelProvider, ModelRequest, ModelResponse, ToolSpec
from adversi.providers.registry import create_provider

_LoopState = tuple[
    "weakref.ref[asyncio.AbstractEventLoop]",
    ModelProvider,
    asyncio.Semaphore | None,
    RateLimiter | None,
]


def parse_model_spec(spec: str) -> tuple[str, str]:
    """``"openai:gpt-4o-mini"`` -> ``("openai", "gpt-4o-mini")``. Model names may contain ':'."""
    provider, sep, model = spec.partition(":")
    if not sep or not provider or not model:
        raise ConfigurationError(f"model spec must look like 'provider:model', got {spec!r}")
    return provider, model


class Model:
    """A model bound to a provider plus call settings.

    Examples::

        Model("openai:gpt-4o-mini", temperature=0.2)
        Model("ollama:llama3.1:8b")
        Model(provider="openai_compatible", model="qwen2.5",
              provider_options={"base_url": "http://localhost:8000/v1"})
        Model(provider=MyProvider(), model="my-model")
    """

    def __init__(
        self,
        spec: str | None = None,
        *,
        provider: str | ModelProvider | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        seed: int | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 3,
        max_concurrency: int | None = 8,
        requests_per_minute: float | None = None,
        price: Price | None = None,
        cache: ResponseCache | None = None,
        provider_options: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if spec is not None:
            if provider is not None or model is not None:
                raise ConfigurationError("pass either a spec string or provider=/model=, not both")
            provider, model = parse_model_spec(spec)
        if provider is None or not model:
            raise ConfigurationError("Model requires a provider and a model name")
        self.model_name = model
        self._provider_instance = provider if isinstance(provider, ModelProvider) else None
        self.provider_name = provider.name if isinstance(provider, ModelProvider) else provider
        self.provider_options = dict(provider_options or {})
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.seed = seed
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.max_concurrency = max_concurrency
        self.requests_per_minute = requests_per_minute
        self.price = price
        self.cache = cache
        self.extra = dict(extra or {})
        # Async primitives and HTTP clients are bound to an event loop; keep one per loop
        # so that repeated ``run_sync`` calls (each with a fresh loop) keep working.
        self._loop_state: dict[int, _LoopState] = {}

    @property
    def id(self) -> str:
        return f"{self.provider_name}:{self.model_name}"

    def __repr__(self) -> str:
        return f"Model({self.id!r})"

    def settings(self) -> dict[str, Any]:
        """Reproducibility snapshot. Never includes credentials."""
        return {
            "id": self.id,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "seed": self.seed,
            "extra": self.extra,
            "base_url": self.provider_options.get("base_url"),
        }

    def with_settings(self, **overrides: Any) -> Model:
        """Copy with different call settings.

        Unless concurrency or rate limits are overridden, the copy shares this model's
        HTTP client, semaphore and rate limiter, so limits apply across both.
        """
        shares_limits = (
            "max_concurrency" not in overrides and "requests_per_minute" not in overrides
        )
        clone = Model(
            provider=self._provider_instance or self.provider_name,
            model=overrides.pop("model", self.model_name),
            temperature=overrides.pop("temperature", self.temperature),
            max_tokens=overrides.pop("max_tokens", self.max_tokens),
            top_p=overrides.pop("top_p", self.top_p),
            seed=overrides.pop("seed", self.seed),
            timeout_s=overrides.pop("timeout_s", self.timeout_s),
            max_retries=overrides.pop("max_retries", self.max_retries),
            max_concurrency=overrides.pop("max_concurrency", self.max_concurrency),
            requests_per_minute=overrides.pop("requests_per_minute", self.requests_per_minute),
            price=overrides.pop("price", self.price),
            cache=overrides.pop("cache", self.cache),
            provider_options=self.provider_options,
            extra={**self.extra, **overrides.pop("extra", {})},
        )
        if overrides:
            raise TypeError(f"unknown settings: {sorted(overrides)}")
        if shares_limits:
            clone._loop_state = self._loop_state
        return clone

    # -- internals -----------------------------------------------------------------

    def _state(self) -> tuple[ModelProvider, asyncio.Semaphore | None, RateLimiter | None]:
        loop = asyncio.get_running_loop()
        entry = self._loop_state.get(id(loop))
        # id() values are reused after a loop is garbage collected, so confirm identity.
        if entry is None or entry[0]() is not loop:
            provider = self._provider_instance or create_provider(
                self.provider_name, **self.provider_options
            )
            sem = asyncio.Semaphore(self.max_concurrency) if self.max_concurrency else None
            limiter = RateLimiter(self.requests_per_minute) if self.requests_per_minute else None
            for key, (ref, *_rest) in list(self._loop_state.items()):
                if ref() is None or ref().is_closed():  # type: ignore[union-attr]
                    del self._loop_state[key]
            entry = (weakref.ref(loop), provider, sem, limiter)
            self._loop_state[id(loop)] = entry
        return entry[1], entry[2], entry[3]

    @property
    def capabilities(self) -> Any:
        return self._state()[0].capabilities

    def build_request(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        response_schema: dict[str, Any] | None = None,
        schema_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelRequest:
        return ModelRequest(
            model=self.model_name,
            messages=list(messages),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            seed=self.seed,
            tools=list(tools),
            response_schema=response_schema,
            response_schema_name=schema_name,
            extra=self.extra,
            metadata=metadata or {},
        )

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        response_schema: dict[str, Any] | None = None,
        schema_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse:
        request = self.build_request(
            messages,
            tools=tools,
            response_schema=response_schema,
            schema_name=schema_name,
            metadata=metadata,
        )
        return await self.send(request)

    async def send(self, request: ModelRequest) -> ModelResponse:
        tracker = current_tracker()
        key = request_key(self.provider_name, request) if self.cache else None
        if self.cache and key:
            hit = self.cache.get(key)
            if hit is not None:
                hit.cached = True
                return hit

        if tracker:
            tracker.check_budget()

        provider, sem, limiter = self._state()
        response = await self._send_with_retries(provider, sem, limiter, request)
        if tracker:
            cost = self.price.cost(response.usage) if self.price else None
            tracker.record(self.id, response.usage, cost_usd=cost, latency_s=response.latency_s)
        if self.cache and key:
            self.cache.set(key, response)
        return response

    async def _send_with_retries(
        self,
        provider: ModelProvider,
        sem: asyncio.Semaphore | None,
        limiter: RateLimiter | None,
        request: ModelRequest,
    ) -> ModelResponse:
        attempt = 0
        while True:
            try:
                if limiter:
                    await limiter.acquire()
                start = time.perf_counter()
                if sem:
                    async with sem:
                        response = await asyncio.wait_for(
                            provider.complete(request), self.timeout_s
                        )
                else:
                    response = await asyncio.wait_for(provider.complete(request), self.timeout_s)
                if not response.latency_s:
                    response.latency_s = time.perf_counter() - start
                return response
            except TimeoutError as exc:
                error: ProviderError = ProviderTimeoutError(
                    f"{self.id} timed out after {self.timeout_s}s", provider=self.provider_name
                )
                error.__cause__ = exc
            except ProviderError as exc:
                error = exc
            if not error.retryable or attempt >= self.max_retries:
                raise error
            attempt += 1
            delay = min(30.0, 0.5 * 2**attempt) * (0.5 + random.random())  # noqa: S311
            await asyncio.sleep(delay)

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        tracker = current_tracker()
        if tracker:
            tracker.check_budget()
        provider, _, _ = self._state()
        async for chunk in provider.stream(self.build_request(messages)):
            yield chunk

    def complete_sync(self, messages: Sequence[Message], **kwargs: Any) -> ModelResponse:
        return run_blocking(self.complete(messages, **kwargs))

    async def aclose(self) -> None:
        """Close the provider bound to the current event loop."""
        entry = self._loop_state.pop(id(asyncio.get_running_loop()), None)
        if entry is not None and self._provider_instance is None:
            await entry[1].aclose()


def as_model(value: Model | str) -> Model:
    return value if isinstance(value, Model) else Model(value)
