"""Workflow engine: an ordered list of steps operating on a shared RunContext."""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from adversi._sync import run_blocking
from adversi.claims.policy import StatusPolicy
from adversi.errors import AdverSIError, BudgetExceededError
from adversi.models.model import Model
from adversi.observability.events import EventBus, EventHandler, EventType
from adversi.observability.usage import Budget, UsageTracker, reset_tracker, set_tracker
from adversi.orchestration.context import ModelMap, RunContext
from adversi.protocol.outcome import RunError, StepRecord
from adversi.protocol.result import AdverSIResult
from adversi.tools.base import Tool
from adversi.tools.documents import Document
from adversi.tools.registry import create_tool

if TYPE_CHECKING:
    from adversi.agents.agent import Agent


class StepError(AdverSIError):
    pass


class Step(ABC):
    """One stage of a workflow.

    Subclasses implement :meth:`run`, reading and writing ``ctx``. Steps must not
    depend on each other directly: everything flows through the RunContext, so steps
    can be reordered, removed or replaced.
    """

    kind: ClassVar[str] = "step"

    def __init__(self, *, name: str | None = None, required: bool = False) -> None:
        self.name = name or self.kind
        self.required = required

    @property
    def agents(self) -> list[Agent]:
        return []

    def config(self) -> dict[str, Any]:
        return {}

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "agents": [a.describe() for a in self.agents],
            **self.config(),
        }

    @abstractmethod
    async def run(self, ctx: RunContext) -> None: ...


class Workflow:
    """An executable sequence of steps.

    ``models`` may be a single default model or a mapping of agent-name / role-name to
    model, with an optional ``"default"`` key.
    """

    def __init__(
        self,
        steps: Sequence[Step],
        *,
        name: str = "custom",
        model: Model | str | None = None,
        models: Mapping[str, Model | str] | None = None,
        tools: Sequence[Tool | str] = (),
        budget: Budget | None = None,
        policy: StatusPolicy | None = None,
        max_concurrency: int = 8,
        fail_fast: bool = False,
        mode: str | None = None,
        profile: str | None = None,
        include_trace: bool = True,
        config_snapshot: dict[str, Any] | None = None,
    ) -> None:
        if not steps:
            raise ValueError("a workflow needs at least one step")
        names = [s.name for s in steps]
        if len(set(names)) != len(names):
            raise ValueError(f"step names must be unique, got {names}")
        overrides = dict(models or {})
        default = model if model is not None else overrides.pop("default", None)
        self.steps = list(steps)
        self.name = name
        self.models = ModelMap(default, overrides)
        self.tools = [create_tool(t) if isinstance(t, str) else t for t in tools]
        self.budget = budget
        self.policy = policy or StatusPolicy()
        self.max_concurrency = max_concurrency
        self.fail_fast = fail_fast
        self.mode = mode
        self.profile = profile
        self.include_trace = include_trace
        self.config_snapshot = config_snapshot or {}

    def describe(self) -> dict[str, Any]:
        return {
            "workflow": self.name,
            "mode": self.mode,
            "profile": self.profile,
            "default_model": self.models.default.settings() if self.models.default else None,
            "model_overrides": {k: m.settings() for k, m in self.models.overrides.items()},
            "steps": [s.describe() for s in self.steps],
            "tools": [t.name for t in self.tools],
            "policy": {
                "require_external_evidence": self.policy.require_external_evidence,
                "min_reliability": self.policy.min_reliability,
            },
            "budget": self.budget.__dict__ if self.budget else None,
            **({"user_config": self.config_snapshot} if self.config_snapshot else {}),
        }

    async def run(
        self,
        question: str,
        *,
        documents: Sequence[Document] = (),
        context: str | None = None,
        run_id: str | None = None,
        on_event: EventHandler | Sequence[EventHandler] = (),
    ) -> AdverSIResult:
        if not question.strip():
            raise ValueError("question must not be empty")
        run_id = run_id or uuid.uuid4().hex[:12]
        events = EventBus(run_id)
        for handler in [on_event] if callable(on_event) else on_event:
            events.subscribe(handler)
        events.emit(
            EventType.RUN_STARTED,
            question=question,
            workflow=self.name,
            mode=self.mode,
            steps=[s.name for s in self.steps],
        )
        tracker = UsageTracker(self.budget)
        token = set_tracker(tracker)
        ctx = RunContext(
            run_id=run_id,
            question=question,
            context=context,
            models=self.models,
            events=events,
            usage=tracker,
            documents=documents,
            tools=self.tools,
            policy=self.policy,
            max_concurrency=self.max_concurrency,
        )
        try:
            for step in self.steps:
                if not await self._run_step(step, ctx):
                    break
        finally:
            reset_tracker(token)

        result_tools = sorted(
            {t.name for t in ctx.tools}
            | {t.name for s in self.steps for a in s.agents for t in a.tools}
        )
        total = tracker.total()
        events.emit(
            EventType.RUN_COMPLETED if not ctx.errors else EventType.RUN_FAILED,
            errors=len(ctx.errors),
            calls=total.calls,
            input_tokens=total.input_tokens,
            output_tokens=total.output_tokens,
            cost_usd=total.cost_usd,
        )
        return ctx.build_result(
            workflow=self.name,
            mode=self.mode,
            profile=self.profile,
            config=self.describe(),
            tools=result_tools,
            include_trace=self.include_trace,
        )

    async def _run_step(self, step: Step, ctx: RunContext) -> bool:
        """Run one step. Returns False if the workflow should stop."""
        record = StepRecord(
            name=step.name, kind=step.kind, config=step.config(), started_at=datetime.now(UTC)
        )
        ctx.events.emit(EventType.STEP_STARTED, step=step.name, kind=step.kind)
        t0 = time.perf_counter()
        keep_going = True
        try:
            await step.run(ctx)
            ctx.events.emit(
                EventType.STEP_COMPLETED,
                step=step.name,
                duration_s=round(time.perf_counter() - t0, 3),
            )
        except BudgetExceededError as exc:
            record.ok = False
            ctx.errors.append(
                RunError(step=step.name, type="BudgetExceededError", message=str(exc))
            )
            ctx.events.emit(EventType.BUDGET_EXCEEDED, step=step.name, message=str(exc))
            keep_going = False
            if self.fail_fast:
                raise
        except Exception as exc:
            record.ok = False
            ctx.errors.append(RunError(step=step.name, type=type(exc).__name__, message=str(exc)))
            ctx.events.emit(
                EventType.STEP_FAILED, step=step.name, error=f"{type(exc).__name__}: {exc}"
            )
            if self.fail_fast:
                raise
            keep_going = not step.required
        finally:
            record.duration_s = round(time.perf_counter() - t0, 3)
            ctx.steps.append(record)
        return keep_going

    def run_sync(self, question: str, **kwargs: Any) -> AdverSIResult:
        """Blocking convenience wrapper. Not usable inside a running event loop."""
        return run_blocking(self.run(question, **kwargs))
