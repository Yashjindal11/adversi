"""AdverSI: an open-source framework for adversarial, evidence-aware multi-agent reasoning.

Independent reasoning. Adversarial critique. Evidence. Synthesis.
"""

from adversi._version import RESULT_SCHEMA_VERSION, __version__
from adversi.agents import Agent, Role, domain_expert, register_role
from adversi.api import AdverSI
from adversi.claims import StatusPolicy
from adversi.errors import (
    AdverSIError,
    BudgetExceededError,
    ConfigurationError,
    ProviderError,
    StructuredOutputError,
    ToolError,
)
from adversi.models import MemoryCache, Model, Price, SQLiteCache
from adversi.observability import Budget, Event, EventType, JSONLSink
from adversi.protocol import (
    AdverSIResult,
    Claim,
    ClaimStatus,
    ClaimType,
    Evidence,
    Perspective,
    SourceType,
)
from adversi.providers import ModelProvider, register_provider
from adversi.tools import Document, Tool, ToolOutput, tool
from adversi.workflows import Step, Workflow, build_workflow, steps

__all__ = [
    "RESULT_SCHEMA_VERSION",
    "AdverSI",
    "AdverSIError",
    "AdverSIResult",
    "Agent",
    "Budget",
    "BudgetExceededError",
    "Claim",
    "ClaimStatus",
    "ClaimType",
    "ConfigurationError",
    "Document",
    "Event",
    "EventType",
    "Evidence",
    "JSONLSink",
    "MemoryCache",
    "Model",
    "ModelProvider",
    "Perspective",
    "Price",
    "ProviderError",
    "Role",
    "SQLiteCache",
    "SourceType",
    "StatusPolicy",
    "Step",
    "StructuredOutputError",
    "Tool",
    "ToolError",
    "ToolOutput",
    "Workflow",
    "__version__",
    "build_workflow",
    "domain_expert",
    "register_provider",
    "register_role",
    "steps",
    "tool",
]
