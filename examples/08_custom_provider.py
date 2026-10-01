"""A custom model provider.

Implement ``ModelProvider.complete`` (translate ModelRequest -> your API -> ModelResponse)
and register it. Retries, timeouts, caching, budgets and token accounting are handled
by ``adversi.Model``; raise ``ProviderError(retryable=...)`` so it can do its job.

Packages can also register providers without code changes via the entry point group
``adversi.providers`` in their pyproject.toml:

    [project.entry-points."adversi.providers"]
    mycorp = "mycorp_adversi:make_provider"
"""

from __future__ import annotations

import os
import time

import httpx

from adversi import AdverSI, ModelProvider, ProviderError, register_provider
from adversi.protocol import TokenUsage
from adversi.providers import ModelRequest, ModelResponse, ProviderCapabilities


class InternalGatewayProvider(ModelProvider):
    """Example: a company gateway with a non-OpenAI JSON API."""

    name = "gateway"
    capabilities = ProviderCapabilities(tool_calling=False, json_mode=True)

    def __init__(self, base_url: str, token_env: str = "GATEWAY_TOKEN") -> None:
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {os.environ.get(token_env, '')}"},
            timeout=60,
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        start = time.perf_counter()
        try:
            r = await self.client.post(
                "/generate",
                json={
                    "model": request.model,
                    "prompt": [{"role": m.role, "text": m.content} for m in request.messages],
                    "temperature": request.temperature,
                    "json": request.response_schema is not None,
                },
            )
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.name, retryable=True) from exc
        if r.status_code >= 400:
            raise ProviderError(
                r.text[:300],
                provider=self.name,
                status_code=r.status_code,
                retryable=r.status_code >= 500,
            )
        data = r.json()
        return ModelResponse(
            content=data["text"],
            usage=TokenUsage(
                input_tokens=data.get("in_tokens", 0), output_tokens=data.get("out_tokens", 0)
            ),
            model=request.model,
            provider=self.name,
            latency_s=time.perf_counter() - start,
        )

    async def aclose(self) -> None:
        await self.client.aclose()


register_provider(
    "gateway",
    lambda **opts: InternalGatewayProvider(opts.get("base_url", "http://localhost:9000")),
    description="Internal model gateway",
    overwrite=True,
)

if __name__ == "__main__":
    # Now usable anywhere a model spec is accepted, including adversi.toml and the CLI.
    ai = AdverSI("gateway:house-model-7b", mode="debate", profile="fast")
    print(ai.run_sync("Is it safe to cache user session tokens in localStorage?").to_markdown())
