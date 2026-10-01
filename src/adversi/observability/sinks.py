"""Built-in event sinks."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TextIO

from adversi.observability.events import Event, EventType


class JSONLSink:
    """Append every event as one JSON line. Usable as an EventBus handler."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def __call__(self, event: Event) -> None:
        with self._lock:
            self._fh.write(event.model_dump_json() + "\n")
            self._fh.flush()

    def close(self) -> None:
        self._fh.close()


class LoggingSink:
    """Forward events to the stdlib ``logging`` system."""

    _LEVELS = {
        EventType.STEP_FAILED: logging.WARNING,
        EventType.AGENT_FAILED: logging.WARNING,
        EventType.RUN_FAILED: logging.ERROR,
        EventType.BUDGET_EXCEEDED: logging.WARNING,
        EventType.WARNING: logging.WARNING,
        EventType.EVIDENCE_REJECTED: logging.INFO,
    }

    def __init__(self, logger: logging.Logger | None = None, level: int = logging.DEBUG) -> None:
        self.logger = logger or logging.getLogger("adversi.events")
        self.level = level

    def __call__(self, event: Event) -> None:
        level = self._LEVELS.get(event.type, self.level)
        self.logger.log(
            level,
            "%s step=%s agent=%s %s",
            event.type.value,
            event.step,
            event.agent,
            event.data,
        )
