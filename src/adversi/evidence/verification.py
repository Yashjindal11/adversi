"""Grounding checks for cited excerpts."""

from __future__ import annotations

import re

MIN_EXCERPT_CHARS = 12
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|\u2026|\[\.\.\.\])\s*")
_NON_WORD = re.compile(r"[^0-9a-z]+")


def _canon(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def verify_excerpt(excerpt: str, source_text: str) -> tuple[bool, str | None]:
    """Check that ``excerpt`` occurs in ``source_text``.

    Matching ignores case, punctuation and whitespace differences, and allows
    ellipses: each segment between ``...`` must occur, in order. Returns
    ``(ok, reason_if_not)``.
    """
    segments = [s for s in _ELLIPSIS.split(excerpt.strip()) if s.strip()]
    if not segments:
        return False, "empty excerpt"
    if sum(len(s) for s in segments) < MIN_EXCERPT_CHARS:
        return False, f"excerpt shorter than {MIN_EXCERPT_CHARS} characters cannot be verified"
    haystack = _canon(source_text)
    position = 0
    for segment in segments:
        needle = _canon(segment)
        if not needle:
            continue
        found = haystack.find(needle, position)
        if found == -1:
            return False, "excerpt not found in source text"
        position = found + len(needle)
    return True, None
