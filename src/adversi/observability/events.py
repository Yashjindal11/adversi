"""Structured run events. Every observable action in a run is emitted as an :class:`Event`."""

from __future__ import annotations

import inspect
import itertools
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("adversi")


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    MODEL_CALL = "model.call"
    MODEL_RETRY = "model.retry"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    SOURCE_CREATED = "source.created"
    CLAIM_CREATED = "claim.created"
    CLAIM_MERGED = "claim.merged"
    CLAIM_STATUS = "claim.status"
    EVIDENCE_CREATED = "evidence.created"
    EVIDENCE_REJECTED = "evidence.rejected"
    ASSUMPTION_CREATED = "assumption.created"
    DEBATE_TURN = "debate.turn"
    CHALLENGE_CREATED = "challenge.created"
    REBUTTAL_CREATED = "rebuttal.created"
    CRITIQUE_CREATED = "critique.created"
    JUDGMENT_COMPLETED = "judgment.completed"
    SYNTHESIS_COMPLETED = "synthesis.completed"
    BUDGET_EXCEEDED = "budget.exceeded"
    WARNING = "warning"


class Event(BaseModel):
    model_config = ConfigDict(extra="ignore")

    seq: int
    type: EventType
    run_id: str
    timestamp: datetime
    step: str | None = None
    agent: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


EventHandler = Callable[[Event], Any]


class EventBus:
    """Synchronous fan-out of events to subscribers.

    Handlers must be cheap and non-blocking; a failing handler is logged and never
    breaks the run. Async consumers (e.g. websockets) should push into a queue.
    """

    def __init__(self, run_id: str, *, keep_history: bool = True) -> None:
        self.run_id = run_id
        self._handlers: list[EventHandler] = []
        self._seq = itertools.count(1)
        self.keep_history = keep_history
        self.history: list[Event] = []

    def subscribe(self, handler: EventHandler) -> Callable[[], None]:
        if inspect.iscoroutinefunction(handler):
            raise TypeError("EventBus handlers must be synchronous; push to a queue instead.")
        self._handlers.append(handler)
        return lambda: self._handlers.remove(handler)

    def emit(
        self,
        type: EventType,
        *,
        step: str | None = None,
        agent: str | None = None,
        **data: Any,
    ) -> Event:
        event = Event(
            seq=next(self._seq),
            type=type,
            run_id=self.run_id,
            timestamp=datetime.now(UTC),
            step=step,
            agent=agent,
            data=data,
        )
        if self.keep_history:
            self.history.append(event)
        for handler in list(self._handlers):
            try:
                handler(event)
            except Exception:  # a broken observer must never break a run
                logger.exception("event handler failed for %s", event.type)
        return event
