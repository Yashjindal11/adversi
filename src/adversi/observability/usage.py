"""Token/cost accounting and budget enforcement for a run.

The active tracker is held in a context variable so that every ``Model`` call made
inside a run is attributed to it without threading a tracker through every API.
"""

from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass

from adversi.errors import BudgetExceededError
from adversi.protocol.outcome import TokenUsage, UsageSummary


@dataclass(frozen=True)
class Budget:
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None
    max_model_calls: int | None = None


class UsageTracker:
    def __init__(self, budget: Budget | None = None) -> None:
        self.budget = budget or Budget()
        self.by_model: dict[str, UsageSummary] = {}
        self._lock = threading.Lock()

    def check_budget(self) -> None:
        """Raise before a call is made if the budget is already exhausted."""
        total = self.total()
        b = self.budget
        if b.max_model_calls is not None and total.calls >= b.max_model_calls:
            raise BudgetExceededError(f"model call budget exhausted ({b.max_model_calls} calls)")
        if b.max_total_tokens is not None and total.total_tokens >= b.max_total_tokens:
            raise BudgetExceededError(f"token budget exhausted ({b.max_total_tokens} tokens)")
        if (
            b.max_cost_usd is not None
            and total.cost_usd is not None
            and total.cost_usd >= b.max_cost_usd
        ):
            raise BudgetExceededError(f"cost budget exhausted (${b.max_cost_usd:.4f})")

    def record(
        self, model_id: str, usage: TokenUsage, *, cost_usd: float | None, latency_s: float
    ) -> None:
        with self._lock:
            s = self.by_model.setdefault(model_id, UsageSummary())
            s.calls += 1
            s.input_tokens += usage.input_tokens
            s.output_tokens += usage.output_tokens
            s.latency_s += latency_s
            if cost_usd is not None:
                s.cost_usd = (s.cost_usd or 0.0) + cost_usd

    def total(self) -> UsageSummary:
        with self._lock:
            out = UsageSummary()
            for s in self.by_model.values():
                out.calls += s.calls
                out.input_tokens += s.input_tokens
                out.output_tokens += s.output_tokens
                out.latency_s += s.latency_s
                if s.cost_usd is not None:
                    out.cost_usd = (out.cost_usd or 0.0) + s.cost_usd
            return out


_current_tracker: contextvars.ContextVar[UsageTracker | None] = contextvars.ContextVar(
    "adversi_usage_tracker", default=None
)


def current_tracker() -> UsageTracker | None:
    return _current_tracker.get()


def set_tracker(tracker: UsageTracker | None) -> contextvars.Token[UsageTracker | None]:
    return _current_tracker.set(tracker)


def reset_tracker(token: contextvars.Token[UsageTracker | None]) -> None:
    _current_tracker.reset(token)
