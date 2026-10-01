"""Extracting and validating structured (Pydantic) output from model text."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from adversi.errors import StructuredOutputError

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Any:
    """Parse the first JSON object in ``text``, tolerating code fences and surrounding prose."""
    text = text.strip()
    candidates = [text]
    candidates.extend(m.group(1).strip() for m in _FENCE.finditer(text))
    start = text.find("{")
    if start != -1:
        candidates.append(_balanced_object(text, start))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise StructuredOutputError("no JSON object found in model output", raw=text)


def _balanced_object(text: str, start: int) -> str:
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


def parse_structured(text: str, schema: type[T]) -> T:
    data = extract_json(text)
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"output did not match {schema.__name__}: {exc}", raw=text
        ) from exc


def schema_for(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema()
