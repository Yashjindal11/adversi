"""Configuration file schema (``adversi.toml`` / ``adversi.yaml``).

Credentials are never read from config files: providers reference environment
variable *names* (``api_key_env``) only.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from adversi.models.pricing import Price


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class ProviderConfig(_Strict):
    """Options for a provider; overrides the registry defaults."""

    type: str | None = Field(
        default=None, description="Registered provider to instantiate; defaults to the key name."
    )
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_s: float | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    capabilities: dict[str, bool] | None = None


class ModelConfig(_Strict):
    model: str = Field(description="'provider:model', e.g. 'openai:gpt-4o-mini'")
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    seed: int | None = None
    timeout_s: float = 120.0
    max_retries: int = 3
    max_concurrency: int | None = 8
    requests_per_minute: float | None = None
    price: Price | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(_Strict):
    role: str
    name: str | None = None
    model: str | None = Field(
        default=None, description="Key in [models] or a 'provider:model' spec."
    )
    instructions: str | None = None
    domain: str | None = Field(default=None, description="For role=domain_expert.")
    tools: list[str] = Field(default_factory=list)
    use_run_tools: bool | None = None
    max_tool_steps: int | None = None
    temperature: float | None = None


class WorkflowConfig(_Strict):
    mode: str = "research"
    profile: Literal["fast", "balanced", "deep"] = "balanced"
    steps: list[str] | None = Field(default=None, description="Explicit step list; overrides mode.")
    domain: str | None = None
    analysts: int | None = None
    debate_rounds: int | None = None
    cross_examination_rounds: int | None = None
    max_challenges: int | None = None
    max_research_claims: int | None = None
    max_tool_steps: int | None = None
    jurors: int | None = None
    max_concurrency: int = 8
    require_external_evidence: bool = True
    min_evidence_reliability: float = 0.3


class ToolConfig(_Strict):
    name: str
    options: dict[str, Any] = Field(default_factory=dict)


class CacheConfig(_Strict):
    enabled: bool = False
    path: str = ".adversi/cache.sqlite"


class BudgetConfig(_Strict):
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None
    max_model_calls: int | None = None


class OutputConfig(_Strict):
    format: Literal["json", "markdown", "html"] = "markdown"
    directory: str | None = None
    include_trace: bool = True


class AdverSIConfig(_Strict):
    version: Literal[1] = 1
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    agents: list[AgentConfig] = Field(default_factory=list)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    tools: list[ToolConfig] = Field(default_factory=list)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @field_validator("models", mode="before")
    @classmethod
    def _models_shorthand(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: {"model": v} if isinstance(v, str) else v for k, v in value.items()}
        return value

    @field_validator("tools", mode="before")
    @classmethod
    def _tools_shorthand(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [{"name": v} if isinstance(v, str) else v for v in value]
        return value
