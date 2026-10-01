"""Exception hierarchy. Everything AdverSI raises deliberately derives from AdverSIError."""

from __future__ import annotations


class AdverSIError(Exception):
    """Base class for all AdverSI errors."""


class ConfigurationError(AdverSIError):
    """Invalid configuration, unknown provider/role/tool, missing credentials."""


class ProviderError(AdverSIError):
    """A model provider call failed."""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable


class RateLimitError(ProviderError):
    def __init__(self, message: str, *, provider: str = "", status_code: int | None = 429) -> None:
        super().__init__(message, provider=provider, status_code=status_code, retryable=True)


class AuthenticationError(ProviderError):
    def __init__(self, message: str, *, provider: str = "", status_code: int | None = 401) -> None:
        super().__init__(message, provider=provider, status_code=status_code, retryable=False)


class ProviderTimeoutError(ProviderError):
    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(message, provider=provider, retryable=True)


class StructuredOutputError(AdverSIError):
    """A model did not return output matching the requested schema."""

    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


class BudgetExceededError(AdverSIError):
    """A configured token/cost/call budget was exhausted."""


class ToolError(AdverSIError):
    """A tool rejected its input or failed in a way the caller should see."""
