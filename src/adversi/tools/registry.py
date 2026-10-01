"""Name-based tool registry used by config files, the CLI and the server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from adversi.errors import ConfigurationError
from adversi.tools.base import Tool

ToolFactory = Callable[..., Tool]
_FACTORIES: dict[str, ToolFactory] = {}


def register_tool(name: str, factory: ToolFactory, *, overwrite: bool = False) -> None:
    if name in _FACTORIES and not overwrite:
        raise ConfigurationError(f"tool '{name}' is already registered")
    _FACTORIES[name] = factory


def available_tools() -> list[str]:
    return sorted(_FACTORIES)


def create_tool(name: str, **options: Any) -> Tool:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ConfigurationError(
            f"unknown tool '{name}'. Available: {', '.join(available_tools())}"
        )
    return factory(**options)


def _web_search(**options: Any) -> Tool:
    from adversi.tools.web import BraveSearchBackend, web_search_tool

    backend = options.pop("backend", None) or BraveSearchBackend(options.pop("api_key", None))
    return web_search_tool(backend, **options)


def _calculator(**_: Any) -> Tool:
    from adversi.tools.calculator import calculator_tool

    return calculator_tool()


def _fetch_url(**options: Any) -> Tool:
    from adversi.tools.web import fetch_url_tool

    return fetch_url_tool(**options)


register_tool("calculator", _calculator)
register_tool("fetch_url", _fetch_url)
register_tool("web_search", _web_search)
