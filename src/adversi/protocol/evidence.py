"""Sources and evidence, with provenance.

A :class:`Source` is raw material that entered the run from outside the agents:
user documents, tool outputs, fetched web pages. Only the system creates sources.

An :class:`Evidence` item is an excerpt *from* a source that an agent cited for or
against a claim. The excerpt is checked against the source text; citations that
cannot be found in their source are rejected rather than stored.

Model knowledge is representable (``SourceType.MODEL_KNOWLEDGE``) but it is never
counted as external or verified evidence.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from adversi.protocol.base import Record


class SourceType(StrEnum):
    USER_PROVIDED = "user_provided"
    DOCUMENT = "document"
    WEB = "web"
    WEB_SEARCH_SNIPPET = "web_search_snippet"
    TOOL = "tool"
    DATABASE = "database"
    CALCULATION = "calculation"
    DATASET = "dataset"
    EXPERIMENT = "experiment"
    MODEL_KNOWLEDGE = "model_knowledge"


class Provenance(Record):
    source_type: SourceType
    uri: str | None = None
    title: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    retrieved_at: datetime | None = None
    content_sha256: str | None = None
    produced_by: str = "system"


class Source(Record):
    id: str
    content: str
    provenance: Provenance
    truncated: bool = False


class EvidenceRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class Evidence(Record):
    id: str
    source_id: str | None
    excerpt: str
    provenance: Provenance
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    cited_by: str
    note: str | None = None
    excerpt_verified: bool = False
    reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    reliability_rationale: str | None = None

    @property
    def is_external(self) -> bool:
        """True when the excerpt was verified against a non-model source."""
        return self.excerpt_verified and self.provenance.source_type != SourceType.MODEL_KNOWLEDGE


class RejectedCitation(Record):
    """A citation an agent produced that could not be grounded. Kept for auditing."""

    agent: str
    step: str
    source_id: str | None
    excerpt: str
    reason: str
