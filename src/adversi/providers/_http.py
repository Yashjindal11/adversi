"""Shared HTTP helpers for providers built on httpx."""

from __future__ import annotations

import os

import httpx

from adversi.errors import (
    AuthenticationError,
    ConfigurationError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
)


def resolve_api_key(
    provider: str, api_key: str | None, api_key_env: str | None, *, required: bool
) -> str | None:
    if api_key:
        return api_key
    if api_key_env:
        value = os.environ.get(api_key_env)
        if value:
            return value
    if required:
        hint = f" Set the {api_key_env} environment variable." if api_key_env else ""
        raise ConfigurationError(f"No API key configured for provider '{provider}'.{hint}")
    return None


def raise_for_status(provider: str, response: httpx.Response) -> None:
    if response.is_success:
        return
    code = response.status_code
    try:
        detail = response.text[:500]
    except Exception:
        detail = "<unreadable body>"
    message = f"{provider} returned HTTP {code}: {detail}"
    if code == 429:
        raise RateLimitError(message, provider=provider, status_code=code)
    if code in (401, 403):
        raise AuthenticationError(message, provider=provider, status_code=code)
    retryable = code >= 500 or code in (408, 409)
    raise ProviderError(message, provider=provider, status_code=code, retryable=retryable)


def translate_transport_error(provider: str, exc: Exception) -> ProviderError:
    if isinstance(exc, httpx.TimeoutException):
        return ProviderTimeoutError(f"{provider} request timed out", provider=provider)
    return ProviderError(f"{provider} transport error: {exc}", provider=provider, retryable=True)
