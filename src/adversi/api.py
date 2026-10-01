"""High-level entry point.

from adversi import AdverSI

ai = AdverSI("openai:gpt-4o-mini", mode="research", profile="fast")
result = ai.run_sync("Does remote work reduce productivity?")
print(result.to_markdown())
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from adversi._sync import run_blocking
from adversi.agents.agent import Agent
from adversi.claims.policy import StatusPolicy
from adversi.config.loader import ConfigBuilder, load_config
from adversi.config.schema import AdverSIConfig
from adversi.models.model import Model
from adversi.observability.events import EventHandler
from adversi.observability.usage import Budget
from adversi.protocol.result import AdverSIResult
from adversi.tools.base import Tool
from adversi.tools.documents import Document
from adversi.workflows.base import Workflow
from adversi.workflows.presets import build_workflow


class AdverSI:
    """Facade over :func:`build_workflow` / :class:`Workflow` for the common case.

    Args:
        model: default model for every agent (``"provider:model"`` or :class:`Model`).
        models: per-role or per-agent-name overrides, e.g. ``{"judge": "anthropic:..."}``.
        mode: ``simple | debate | adversarial | research | peer_review | jury``.
        profile: ``fast | balanced | deep``.
        tools: :class:`Tool` objects or registered tool names (``"calculator"``...).
        agents: custom agents; replace built-ins with the same role/name.
        workflow: a fully custom workflow; all other workflow arguments are ignored.
    """

    def __init__(
        self,
        model: Model | str | None = None,
        *,
        models: Mapping[str, Model | str] | None = None,
        mode: str = "research",
        profile: str = "balanced",
        tools: Sequence[Tool | str] = (),
        agents: Sequence[Agent] = (),
        domain: str | None = None,
        budget: Budget | None = None,
        policy: StatusPolicy | None = None,
        max_concurrency: int = 8,
        workflow: Workflow | None = None,
        **profile_overrides: Any,
    ) -> None:
        if workflow is not None:
            self.workflow = workflow
            return
        self.workflow = build_workflow(
            mode,
            profile,
            model=model,
            models=models,
            agents=agents,
            tools=tools,
            domain=domain,
            budget=budget,
            policy=policy,
            max_concurrency=max_concurrency,
            profile_overrides=profile_overrides,
        )

    @classmethod
    def from_config(
        cls,
        config: str | Path | AdverSIConfig | None = None,
        *,
        model: str | None = None,
        mode: str | None = None,
        profile: str | None = None,
    ) -> AdverSI:
        cfg = config if isinstance(config, AdverSIConfig) else load_config(config)
        return cls(
            workflow=ConfigBuilder(cfg).workflow(default_model=model, mode=mode, profile=profile)
        )

    async def run(
        self,
        question: str,
        *,
        documents: Sequence[Document | str] = (),
        context: str | None = None,
        run_id: str | None = None,
        on_event: EventHandler | Sequence[EventHandler] = (),
    ) -> AdverSIResult:
        docs = [d if isinstance(d, Document) else Document(content=d) for d in documents]
        return await self.workflow.run(
            question, documents=docs, context=context, run_id=run_id, on_event=on_event
        )

    def run_sync(self, question: str, **kwargs: Any) -> AdverSIResult:
        return run_blocking(self.run(question, **kwargs))
