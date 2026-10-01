"""Registry of sources and evidence for one run.

Sources can only be created by the system (tool outputs, user documents). Agents can
only *cite* sources by id; every citation is verified before it becomes Evidence.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from adversi.claims.text import normalize
from adversi.evidence.verification import verify_excerpt
from adversi.observability.events import EventBus, EventType
from adversi.protocol.evidence import (
    Evidence,
    EvidenceRelation,
    Provenance,
    RejectedCitation,
    Source,
    SourceType,
)

MAX_SOURCE_CHARS = 200_000


class EvidenceStore:
    def __init__(self, events: EventBus | None = None) -> None:
        self._sources: dict[str, Source] = {}
        self._by_hash: dict[tuple[str | None, str], str] = {}
        self._evidence: dict[str, Evidence] = {}
        self.rejected: list[RejectedCitation] = []
        self._events = events

    # -- sources -------------------------------------------------------------------

    def add_source(
        self,
        content: str,
        *,
        source_type: SourceType,
        uri: str | None = None,
        title: str | None = None,
        tool_name: str | None = None,
        tool_arguments: dict[str, Any] | None = None,
        produced_by: str = "system",
    ) -> Source:
        if source_type == SourceType.MODEL_KNOWLEDGE:
            raise ValueError("model knowledge is not a source; cite it with source_id=None")
        digest = hashlib.sha256(content.encode()).hexdigest()
        existing = self._by_hash.get((uri, digest))
        if existing:
            return self._sources[existing]
        truncated = len(content) > MAX_SOURCE_CHARS
        source = Source(
            id=f"S{len(self._sources) + 1}",
            content=content[:MAX_SOURCE_CHARS],
            truncated=truncated,
            provenance=Provenance(
                source_type=source_type,
                uri=uri,
                title=title,
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                retrieved_at=datetime.now(UTC),
                content_sha256=digest,
                produced_by=produced_by,
            ),
        )
        self._sources[source.id] = source
        self._by_hash[(uri, digest)] = source.id
        if self._events:
            self._events.emit(
                EventType.SOURCE_CREATED,
                agent=produced_by if produced_by != "system" else None,
                source_id=source.id,
                source_type=source_type.value,
                uri=uri,
                title=title,
            )
        return source

    def source(self, source_id: str) -> Source:
        return self._sources[source_id]

    def sources(self) -> list[Source]:
        return list(self._sources.values())

    # -- evidence ------------------------------------------------------------------

    def get(self, evidence_id: str) -> Evidence:
        return self._evidence[evidence_id]

    def __contains__(self, evidence_id: object) -> bool:
        return evidence_id in self._evidence

    def all(self) -> list[Evidence]:
        return list(self._evidence.values())

    def for_claim(self, claim_id: str) -> list[Evidence]:
        return [
            e
            for e in self._evidence.values()
            if claim_id in e.supports or claim_id in e.contradicts
        ]

    def cite(
        self,
        *,
        source_id: str | None,
        excerpt: str,
        agent: str,
        step: str,
        supports: Iterable[str] = (),
        contradicts: Iterable[str] = (),
        note: str | None = None,
    ) -> Evidence | None:
        """Turn an agent citation into Evidence, or record why it was rejected."""
        excerpt = excerpt.strip()
        if source_id is None:
            provenance = Provenance(source_type=SourceType.MODEL_KNOWLEDGE, produced_by=agent)
            verified = False
        else:
            source = self._sources.get(source_id)
            if source is None:
                self._reject(agent, step, source_id, excerpt, f"unknown source id {source_id}")
                return None
            ok, reason = verify_excerpt(excerpt, source.content)
            if not ok:
                self._reject(agent, step, source_id, excerpt, reason or "verification failed")
                return None
            provenance = source.provenance
            verified = True

        key = normalize(excerpt)
        for existing in self._evidence.values():
            if existing.source_id == source_id and normalize(existing.excerpt) == key:
                self._link_all(existing, supports, contradicts)
                return existing

        evidence = Evidence(
            id=f"E{len(self._evidence) + 1}",
            source_id=source_id,
            excerpt=excerpt,
            provenance=provenance,
            cited_by=agent,
            note=note,
            excerpt_verified=verified,
        )
        self._link_all(evidence, supports, contradicts)
        self._evidence[evidence.id] = evidence
        if self._events:
            self._events.emit(
                EventType.EVIDENCE_CREATED,
                step=step,
                agent=agent,
                evidence_id=evidence.id,
                source_id=source_id,
                external=evidence.is_external,
                supports=evidence.supports,
                contradicts=evidence.contradicts,
            )
        return evidence

    def link(self, evidence_id: str, claim_id: str, relation: EvidenceRelation | None) -> None:
        """Set the relation of one evidence item to one claim (None removes it)."""
        e = self._evidence[evidence_id]
        e.supports = [c for c in e.supports if c != claim_id]
        e.contradicts = [c for c in e.contradicts if c != claim_id]
        if relation == EvidenceRelation.SUPPORTS:
            e.supports.append(claim_id)
        elif relation == EvidenceRelation.CONTRADICTS:
            e.contradicts.append(claim_id)

    def remap_claims(self, mapping: dict[str, str]) -> None:
        for e in self._evidence.values():
            e.supports = list(dict.fromkeys(mapping.get(c, c) for c in e.supports))
            e.contradicts = list(dict.fromkeys(mapping.get(c, c) for c in e.contradicts))

    @staticmethod
    def _link_all(e: Evidence, supports: Iterable[str], contradicts: Iterable[str]) -> None:
        for c in supports:
            if c not in e.supports:
                e.supports.append(c)
        for c in contradicts:
            if c not in e.contradicts:
                e.contradicts.append(c)

    def _reject(
        self, agent: str, step: str, source_id: str | None, excerpt: str, reason: str
    ) -> None:
        self.rejected.append(
            RejectedCitation(
                agent=agent, step=step, source_id=source_id, excerpt=excerpt[:500], reason=reason
            )
        )
        if self._events:
            self._events.emit(
                EventType.EVIDENCE_REJECTED,
                step=step,
                agent=agent,
                source_id=source_id,
                reason=reason,
            )
