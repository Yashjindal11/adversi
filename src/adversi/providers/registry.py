"""Provider registry.

Providers are registered by name with a factory callable. Third-party packages can
register providers without touching AdverSI via the ``adversi.providers`` entry-point
group, whose objects must be ``ProviderFactory`` callables.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any

from adversi.errors import ConfigurationError
from adversi.providers.base import ModelProvider, ProviderCapabilities

ProviderFactory = Callable[..., ModelProvider]


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    factory: ProviderFactory
    description: str = ""
    api_key_env: str | None = None
    default_base_url: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def configured(self) -> bool:
        return self.api_key_env is None or bool(os.environ.get(self.api_key_env))


_REGISTRY: dict[str, ProviderInfo] = {}
_entry_points_loaded = False


def register_provider(
    name: str,
    factory: ProviderFactory,
    *,
    description: str = "",
    api_key_env: str | None = None,
    default_base_url: str | None = None,
    overwrite: bool = False,
) -> None:
    if name in _REGISTRY and not overwrite:
        raise ConfigurationError(f"provider '{name}' is already registered")
    _REGISTRY[name] = ProviderInfo(
        name=name,
        factory=factory,
        description=description,
        api_key_env=api_key_env,
        default_base_url=default_base_url,
    )


def unregister_provider(name: str) -> None:
    _REGISTRY.pop(name, None)


def _load_entry_points() -> None:
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    _entry_points_loaded = True
    for ep in entry_points(group="adversi.providers"):
        if ep.name not in _REGISTRY:
            register_provider(ep.name, ep.load(), description=f"plugin: {ep.value}")


def available_providers() -> dict[str, ProviderInfo]:
    _load_entry_points()
    return dict(_REGISTRY)


def create_provider(name: str, **options: Any) -> ModelProvider:
    _load_entry_points()
    info = _REGISTRY.get(name)
    if info is None:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise ConfigurationError(f"unknown provider '{name}'. Registered providers: {known}")
    return info.factory(**options)


# -- built-in providers -------------------------------------------------------------


def _openai_compatible_factory(
    name: str,
    default_base_url: str | None,
    api_key_env: str | None,
    *,
    require_key: bool,
    capabilities: ProviderCapabilities | None = None,
) -> ProviderFactory:
    def factory(**options: Any) -> ModelProvider:
        from adversi.providers.openai_compat import OpenAICompatibleProvider

        base_url = options.pop("base_url", None) or default_base_url
        if not base_url:
            raise ConfigurationError(f"provider '{name}' requires base_url")
        caps = options.pop("capabilities", None) or capabilities
        if isinstance(caps, dict):
            caps = ProviderCapabilities(**caps)
        return OpenAICompatibleProvider(
            name=name,
            base_url=base_url,
            api_key_env=options.pop("api_key_env", api_key_env),
            require_api_key=options.pop("require_api_key", require_key),
            capabilities=caps,
            **options,
        )

    return factory


def _anthropic_factory(**options: Any) -> ModelProvider:
    from adversi.providers.anthropic import AnthropicProvider

    options.pop("capabilities", None)
    return AnthropicProvider(**options)


_BUILTINS: list[tuple[str, str | None, str | None, bool, ProviderCapabilities | None, str]] = [
    ("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", True, None, "OpenAI API"),
    (
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "GEMINI_API_KEY",
        True,
        None,
        "Google Gemini via its OpenAI-compatible endpoint",
    ),
    (
        "ollama",
        "http://localhost:11434/v1",
        None,
        False,
        ProviderCapabilities(tool_calling=True, json_mode=True, json_schema=True, streaming=True),
        "Local models served by Ollama",
    ),
    (
        "huggingface",
        "https://router.huggingface.co/v1",
        "HF_TOKEN",
        True,
        ProviderCapabilities(tool_calling=True, json_mode=False, json_schema=False, streaming=True),
        "Hugging Face Inference Providers router (or a TGI server via base_url)",
    ),
    (
        "openai_compatible",
        None,
        "OPENAI_COMPATIBLE_API_KEY",
        False,
        ProviderCapabilities(tool_calling=True, json_mode=True, json_schema=False, streaming=True),
        "Any OpenAI-compatible server (vLLM, LM Studio, llama.cpp, gateways); set base_url",
    ),
]

for _name, _url, _env, _req, _caps, _desc in _BUILTINS:
    register_provider(
        _name,
        _openai_compatible_factory(_name, _url, _env, require_key=_req, capabilities=_caps),
        description=_desc,
        api_key_env=_env if _req else None,
        default_base_url=_url,
    )

register_provider(
    "anthropic",
    _anthropic_factory,
    description="Anthropic Messages API",
    api_key_env="ANTHROPIC_API_KEY",
    default_base_url="https://api.anthropic.com",
)
