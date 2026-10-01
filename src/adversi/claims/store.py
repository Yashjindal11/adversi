"""Registry of claims and assumptions for one run."""

from __future__ import annotations

from collections.abc import Iterable

from adversi.claims.text import normalize, similarity
from adversi.observability.events import EventBus, EventType
from adversi.protocol.claims import Assumption, Attribution, Claim, ClaimBasis, ClaimType


class ClaimStore:
    def __init__(self, events: EventBus | None = None) -> None:
        self._claims: dict[str, Claim] = {}
        self._by_norm: dict[str, str] = {}
        self._assumptions: dict[str, Assumption] = {}
        self._assumption_by_norm: dict[str, str] = {}
        self._events = events

    def __contains__(self, claim_id: object) -> bool:
        return claim_id in self._claims

    def __len__(self) -> int:
        return len(self._claims)

    def get(self, claim_id: str) -> Claim:
        return self._claims[claim_id]

    def all(self) -> list[Claim]:
        return list(self._claims.values())

    def assumptions(self) -> list[Assumption]:
        return list(self._assumptions.values())

    def add(
        self,
        statement: str,
        *,
        attribution: Attribution,
        claim_type: ClaimType = ClaimType.OTHER,
        basis: ClaimBasis = ClaimBasis.ASSERTION,
        derived_from: Iterable[str] = (),
    ) -> Claim:
        """Register a claim, or add an attribution if an identical claim already exists."""
        norm = normalize(statement)
        existing_id = self._by_norm.get(norm)
        if existing_id:
            claim = self._claims[existing_id]
            claim.attributions.append(attribution)
            return claim
        claim = Claim(
            id=f"C{len(self._claims) + 1}",
            statement=statement.strip(),
            claim_type=claim_type,
            basis=basis,
            attributions=[attribution],
            derived_from=[d for d in derived_from if d in self._claims],
        )
        self._claims[claim.id] = claim
        self._by_norm[norm] = claim.id
        if self._events:
            self._events.emit(
                EventType.CLAIM_CREATED,
                step=attribution.step,
                agent=attribution.agent,
                claim_id=claim.id,
                statement=claim.statement,
                claim_type=claim.claim_type.value,
            )
        return claim

    def add_assumption(
        self,
        statement: str,
        *,
        identified_by: str,
        claim_ids: Iterable[str] = (),
        critical: bool = False,
    ) -> Assumption:
        valid = [c for c in claim_ids if c in self._claims]
        norm = normalize(statement)
        existing = self._assumption_by_norm.get(norm)
        if existing:
            a = self._assumptions[existing]
            a.claim_ids = sorted(set(a.claim_ids) | set(valid), key=_id_key)
            a.critical = a.critical or critical
        else:
            a = Assumption(
                id=f"A{len(self._assumptions) + 1}",
                statement=statement.strip(),
                critical=critical,
                claim_ids=valid,
                identified_by=identified_by,
            )
            self._assumptions[a.id] = a
            self._assumption_by_norm[norm] = a.id
            if self._events:
                self._events.emit(
                    EventType.ASSUMPTION_CREATED,
                    agent=identified_by,
                    assumption_id=a.id,
                    statement=a.statement,
                )
        for cid in valid:
            claim = self._claims[cid]
            if a.id not in claim.assumption_ids:
                claim.assumption_ids.append(a.id)
        return a

    def consolidate(self, threshold: float = 0.85) -> dict[str, str]:
        """Merge near-duplicate claims. Returns ``{merged_id: kept_id}``."""
        mapping: dict[str, str] = {}
        ids = list(self._claims)
        for i, keep_id in enumerate(ids):
            if keep_id in mapping:
                continue
            keep = self._claims[keep_id]
            for other_id in ids[i + 1 :]:
                if other_id in mapping:
                    continue
                other = self._claims[other_id]
                if similarity(keep.statement, other.statement) >= threshold:
                    mapping[other_id] = keep_id
                    keep.attributions.extend(other.attributions)
                    keep.merged_from.append(other_id)
                    for aid in other.assumption_ids:
                        if aid not in keep.assumption_ids:
                            keep.assumption_ids.append(aid)
        for merged_id, kept_id in mapping.items():
            del self._claims[merged_id]
            for norm, cid in list(self._by_norm.items()):
                if cid == merged_id:
                    self._by_norm[norm] = kept_id
            if self._events:
                self._events.emit(EventType.CLAIM_MERGED, merged_id=merged_id, into=kept_id)
        for claim in self._claims.values():
            claim.derived_from = [
                mapping.get(d, d) for d in claim.derived_from if mapping.get(d, d) != claim.id
            ]
        for a in self._assumptions.values():
            a.claim_ids = sorted({mapping.get(c, c) for c in a.claim_ids}, key=_id_key)
        return mapping


def _id_key(identifier: str) -> tuple[str, int]:
    head = identifier.rstrip("0123456789")
    tail = identifier[len(head) :]
    return head, int(tail) if tail else 0
