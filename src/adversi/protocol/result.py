"""The top-level, stable result schema returned by every AdverSI run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from adversi._version import RESULT_SCHEMA_VERSION
from adversi.observability.events import Event
from adversi.protocol.base import Record
from adversi.protocol.claims import Assumption, Claim, ClaimStatus
from adversi.protocol.evidence import Evidence, RejectedCitation, Source
from adversi.protocol.outcome import (
    Interpretation,
    Judgment,
    RunMetadata,
    Synthesis,
    Uncertainty,
)
from adversi.protocol.reasoning import Challenge, CritiqueFinding, DebateTurn, Perspective


class AdverSIResult(Record):
    schema_version: str = RESULT_SCHEMA_VERSION
    question: str
    context: str | None = None
    interpretation: Interpretation | None = None
    perspectives: list[Perspective] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    rejected_citations: list[RejectedCitation] = Field(default_factory=list)
    debate: list[DebateTurn] = Field(default_factory=list)
    challenges: list[Challenge] = Field(default_factory=list)
    critique: list[CritiqueFinding] = Field(default_factory=list)
    judgment: Judgment | None = None
    synthesis: Synthesis | None = None
    uncertainty: Uncertainty = Field(default_factory=Uncertainty)
    unresolved_questions: list[str] = Field(default_factory=list)
    metadata: RunMetadata
    trace: list[Event] = Field(default_factory=list)

    @property
    def answer(self) -> str | None:
        return self.synthesis.answer if self.synthesis else None

    def claim(self, claim_id: str) -> Claim:
        for c in self.claims:
            if c.id == claim_id:
                return c
        raise KeyError(claim_id)

    def claims_with_status(self, *statuses: ClaimStatus) -> list[Claim]:
        return [c for c in self.claims if c.status in statuses]

    def to_dict(self, *, include_trace: bool = True) -> dict[str, Any]:
        exclude = None if include_trace else {"trace"}
        return self.model_dump(mode="json", exclude=exclude)

    def to_json(self, *, indent: int | None = 2, include_trace: bool = True) -> str:
        exclude = None if include_trace else {"trace"}
        return self.model_dump_json(indent=indent, exclude=exclude)

    def to_markdown(self) -> str:
        from adversi.render.markdown import render_markdown

        return render_markdown(self)

    def to_html(self) -> str:
        from adversi.render.html import render_html

        return render_html(self)

    def save(self, path: str | Path, fmt: str | None = None) -> Path:
        path = Path(path)
        fmt = fmt or {".md": "markdown", ".html": "html"}.get(path.suffix, "json")
        text = {"markdown": self.to_markdown, "html": self.to_html}.get(fmt, self.to_json)()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> AdverSIResult:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def __str__(self) -> str:
        return self.to_markdown()
