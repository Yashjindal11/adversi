"""Evaluation datasets and scorers.

Scorers that use a model to grade are labelled ``model_graded``; their numbers
inherit that model's biases and must be reported as such.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from adversi.models.model import Model
from adversi.models.structured import parse_structured
from adversi.protocol.result import AdverSIResult
from adversi.providers.base import Message


class EvalItem(BaseModel):
    id: str
    question: str
    answer: str | None = None
    accepted_answers: list[str] = Field(default_factory=list)
    context: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def references(self) -> list[str]:
        return [a for a in [self.answer, *self.accepted_answers] if a]


def load_dataset(path: str | Path) -> list[EvalItem]:
    """JSONL with one object per line: id, question, answer, accepted_answers?, context?, metadata?"""
    items = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            data = json.loads(line)
            data.setdefault("id", str(n))
            items.append(EvalItem.model_validate(data))
    return items


class Score(BaseModel):
    correct: bool | None
    value: float | None = None
    details: str = ""
    model_graded: bool = False


class Scorer(Protocol):
    name: str

    async def score(self, item: EvalItem, result: AdverSIResult) -> Score: ...


_NORM = re.compile(r"[^0-9a-z]+")


def _norm(text: str) -> str:
    return " ".join(_NORM.sub(" ", text.lower()).split())


class ExactMatch:
    name = "exact_match"

    async def score(self, item: EvalItem, result: AdverSIResult) -> Score:
        if not item.references or not result.answer:
            return Score(correct=None, details="missing reference or answer")
        ok = _norm(result.answer) in {_norm(r) for r in item.references}
        return Score(correct=ok, value=float(ok))


class ContainsAnswer:
    """Correct if a normalized reference appears as a whole-word span in the answer.

    Yes/no references are special-cased: only the answer's first word counts, so
    "Yes, although there is no evidence that..." is not scored as "no".
    """

    name = "contains"
    _POLAR = frozenset({"yes", "no"})

    async def score(self, item: EvalItem, result: AdverSIResult) -> Score:
        if not item.references or not result.answer:
            return Score(correct=None, details="missing reference or answer")
        normalized = _norm(result.answer)
        refs = [_norm(r) for r in item.references]
        if all(r in self._POLAR for r in refs):
            first = normalized.split(" ", 1)[0] if normalized else ""
            ok = first in refs
            return Score(correct=ok, value=float(ok), details="polar: first word compared")
        answer = f" {normalized} "
        ok = any(f" {r} " in answer for r in refs)
        return Score(correct=ok, value=float(ok))


class _Grade(BaseModel):
    correct: bool
    rationale: str = ""


class LLMGrader:
    """Model-graded correctness against reference answers."""

    name = "llm_grader"

    def __init__(self, model: Model | str) -> None:
        self.model = model if isinstance(model, Model) else Model(model)

    async def score(self, item: EvalItem, result: AdverSIResult) -> Score:
        if not item.references or not result.answer:
            return Score(correct=None, details="missing reference or answer", model_graded=True)
        prompt = (
            "Decide whether the candidate answer is correct given the reference answer(s). "
            'Judge substance, not wording. Respond with JSON {"correct": bool, "rationale": str}.\n\n'
            f"Question: {item.question}\nReference(s): {json.dumps(item.references)}\n"
            f"Candidate: {result.answer}"
        )
        response = await self.model.complete(
            [Message.user(prompt)], response_schema=_Grade.model_json_schema(), schema_name="Grade"
        )
        grade = parse_structured(response.content, _Grade)
        return Score(
            correct=grade.correct,
            value=float(grade.correct),
            details=grade.rationale,
            model_graded=True,
        )


SCORERS: dict[str, type[ExactMatch] | type[ContainsAnswer]] = {
    "exact_match": ExactMatch,
    "contains": ContainsAnswer,
}


def make_scorer(name: str, *, grader_model: str | None = None) -> Scorer:
    if name == "llm_grader":
        if not grader_model:
            raise ValueError("llm_grader requires a grader model")
        return LLMGrader(grader_model)
    try:
        return SCORERS[name]()
    except KeyError:
        raise ValueError(
            f"unknown scorer '{name}'. Known: {', '.join([*SCORERS, 'llm_grader'])}"
        ) from None


def references_for(items: Sequence[EvalItem]) -> dict[str, EvalItem]:
    return {i.id: i for i in items}
