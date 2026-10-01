from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from adversi.agents.agent import Agent
from adversi.errors import BudgetExceededError
from adversi.orchestration.context import RunContext
from adversi.protocol.outcome import RunError

T = TypeVar("T", bound=BaseModel)


async def call_agent(
    ctx: RunContext,
    agent: Agent,
    *,
    step: str,
    task: str,
    schema: type[T],
    allow_tools: bool = True,
) -> T:
    async with ctx.semaphore:
        return await agent.respond(
            ctx, step=step, task=task, schema=schema, allow_tools=allow_tools
        )


async def call_agents(
    ctx: RunContext,
    agents: Sequence[Agent],
    tasks: Sequence[str],
    *,
    step: str,
    schema: type[T],
    allow_tools: bool = True,
) -> list[T | None]:
    """Run agents concurrently. Failures are recorded and returned as None.

    Budget exhaustion is re-raised after all calls settle so the workflow stops.
    """
    results: list[Any] = await asyncio.gather(
        *(
            call_agent(ctx, a, step=step, task=t, schema=schema, allow_tools=allow_tools)
            for a, t in zip(agents, tasks, strict=True)
        ),
        return_exceptions=True,
    )
    out: list[T | None] = []
    budget_error: BudgetExceededError | None = None
    for agent, res in zip(agents, results, strict=True):
        if isinstance(res, BudgetExceededError):
            budget_error = res
            out.append(None)
        elif isinstance(res, BaseException):
            if not isinstance(res, Exception):
                raise res
            ctx.errors.append(
                RunError(step=step, agent=agent.name, type=type(res).__name__, message=str(res))
            )
            out.append(None)
        else:
            out.append(res)
    if budget_error is not None and all(o is None for o in out):
        raise budget_error
    if budget_error is not None:
        ctx.errors.append(
            RunError(step=step, type="BudgetExceededError", message=str(budget_error))
        )
    return out


def clip(text: str, n: int = 400) -> str:
    return text if len(text) <= n else text[: n - 1] + "\u2026"
