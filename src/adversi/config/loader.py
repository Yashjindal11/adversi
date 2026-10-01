"""Loading config files and turning them into runnable objects."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from adversi.agents.agent import Agent
from adversi.agents.roles import domain_expert, get_role
from adversi.claims.policy import StatusPolicy
from adversi.config.schema import AdverSIConfig, ModelConfig
from adversi.errors import ConfigurationError
from adversi.models.cache import ResponseCache, SQLiteCache
from adversi.models.model import Model, parse_model_spec
from adversi.observability.usage import Budget
from adversi.tools.base import Tool
from adversi.tools.registry import create_tool
from adversi.workflows.base import Workflow
from adversi.workflows.presets import build_workflow

DEFAULT_CONFIG_NAMES = ("adversi.toml", "adversi.yaml", "adversi.yml")


def load_config(path: str | Path | None = None) -> AdverSIConfig:
    """Load a config file. With no path, look for a default file in the cwd; else defaults."""
    if path is None:
        for name in DEFAULT_CONFIG_NAMES:
            if Path(name).exists():
                path = name
                break
        else:
            return AdverSIConfig()
    p = Path(path)
    if not p.exists():
        raise ConfigurationError(f"config file not found: {p}")
    text = p.read_text(encoding="utf-8")
    data: Any
    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise ConfigurationError("YAML config requires: pip install 'adversi[yaml]'") from exc
        data = yaml.safe_load(text) or {}
    else:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(f"{p}: {exc}") from exc
    return parse_config(data, source=str(p))


def parse_config(data: dict[str, Any], *, source: str = "<config>") -> AdverSIConfig:
    try:
        return AdverSIConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(f"invalid configuration in {source}:\n{exc}") from exc


class ConfigBuilder:
    """Materialises models, agents and tools from an :class:`AdverSIConfig`."""

    def __init__(self, config: AdverSIConfig) -> None:
        self.config = config
        self.cache: ResponseCache | None = (
            SQLiteCache(config.cache.path) if config.cache.enabled else None
        )
        self._models: dict[str, Model] = {}

    def _provider_options(self, provider: str) -> tuple[str, dict[str, Any]]:
        pc = self.config.providers.get(provider)
        if pc is None:
            return provider, {}
        opts: dict[str, Any] = {}
        if pc.base_url:
            opts["base_url"] = pc.base_url
        if pc.api_key_env:
            opts["api_key_env"] = pc.api_key_env
        if pc.timeout_s:
            opts["timeout_s"] = pc.timeout_s
        if pc.headers:
            opts["headers"] = pc.headers
        if pc.capabilities is not None:
            opts["capabilities"] = pc.capabilities
        return pc.type or provider, opts

    def _make_model(self, mc: ModelConfig) -> Model:
        provider, name = parse_model_spec(mc.model)
        provider_type, opts = self._provider_options(provider)
        return Model(
            provider=provider_type,
            model=name,
            temperature=mc.temperature,
            max_tokens=mc.max_tokens,
            top_p=mc.top_p,
            seed=mc.seed,
            timeout_s=mc.timeout_s,
            max_retries=mc.max_retries,
            max_concurrency=mc.max_concurrency,
            requests_per_minute=mc.requests_per_minute,
            price=mc.price,
            cache=self.cache,
            provider_options=opts,
            extra=mc.extra,
        )

    def model(self, ref: str) -> Model:
        """Resolve a key in ``[models]`` or an inline ``provider:model`` spec."""
        if ref not in self._models:
            mc = self.config.models.get(ref) or ModelConfig(model=ref)
            if ref not in self.config.models and ":" not in ref:
                raise ConfigurationError(f"unknown model reference '{ref}'")
            self._models[ref] = self._make_model(mc)
        return self._models[ref]

    def tools(self) -> list[Tool]:
        return [create_tool(t.name, **t.options) for t in self.config.tools]

    def agents(self) -> list[Agent]:
        out = []
        for ac in self.config.agents:
            role = (
                domain_expert(ac.domain)
                if ac.role == "domain_expert" and ac.domain
                else get_role(ac.role)
            )
            kwargs: dict[str, Any] = {}
            if ac.max_tool_steps is not None:
                kwargs["max_tool_steps"] = ac.max_tool_steps
            out.append(
                Agent(
                    role,
                    self.model(ac.model) if ac.model else None,
                    name=ac.name,
                    instructions=ac.instructions,
                    tools=[create_tool(t) for t in ac.tools],
                    use_run_tools=ac.use_run_tools,
                    temperature=ac.temperature,
                    **kwargs,
                )
            )
        names = [a.name for a in out]
        if len(set(names)) != len(names):
            raise ConfigurationError(
                f"agent names must be unique; give agents explicit names: {names}"
            )
        return out

    def workflow(
        self,
        *,
        default_model: str | None = None,
        mode: str | None = None,
        profile: str | None = None,
    ) -> Workflow:
        cfg = self.config
        wf = cfg.workflow
        models: dict[str, Model] = {k: self.model(k) for k in cfg.models}
        default_model = default_model or (
            None if "default" in models else os.environ.get("ADVERSI_MODEL")
        )
        if default_model:
            models["default"] = self.model(default_model)
        if "default" not in models:
            raise ConfigurationError(
                "no default model: pass --model provider:model, set ADVERSI_MODEL, "
                'or add [models] default = "provider:model" to adversi.toml'
            )
        overrides = {
            k: getattr(wf, k)
            for k in (
                "analysts",
                "debate_rounds",
                "cross_examination_rounds",
                "max_challenges",
                "max_research_claims",
                "max_tool_steps",
                "jurors",
            )
        }
        b = cfg.budget
        budget = (
            Budget(b.max_total_tokens, b.max_cost_usd, b.max_model_calls)
            if any(v is not None for v in (b.max_total_tokens, b.max_cost_usd, b.max_model_calls))
            else None
        )
        workflow = build_workflow(
            mode or wf.mode,
            profile or wf.profile,
            models=models,
            agents=self.agents(),
            tools=self.tools(),
            steps=wf.steps if not mode else None,
            domain=wf.domain,
            budget=budget,
            policy=StatusPolicy(wf.require_external_evidence, wf.min_evidence_reliability),
            max_concurrency=wf.max_concurrency,
            profile_overrides=overrides,
            config_snapshot=cfg.model_dump(mode="json"),
        )
        workflow.include_trace = cfg.output.include_trace
        return workflow
