from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from adversi.errors import AdverSIError

T = TypeVar("T")


def run_blocking(coro: Coroutine[Any, Any, T]) -> T:
    """``asyncio.run`` with a helpful error inside notebooks and other running loops."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise AdverSIError(
        "a synchronous AdverSI method was called inside a running event loop "
        "(e.g. Jupyter or an async app); use the async variant: `await ai.run(...)`"
    )
