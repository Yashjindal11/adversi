"""Text normalization and conservative near-duplicate detection for claims."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "to",
        "in",
        "on",
        "for",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "that",
        "this",
        "it",
        "its",
        "as",
        "at",
        "by",
        "with",
        "from",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "might",
        "than",
        "then",
        "there",
        "their",
        "they",
        "which",
        "who",
    ]
)
_NEGATIONS = frozenset({"not", "no", "never", "none", "cannot", "without", "neither", "nor"})


def normalize(text: str) -> str:
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    text = (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    return " ".join(text.split()).strip(" .")


def _tokens(text: str) -> list[str]:
    words = _WORD.findall(normalize(text))
    return ["not" if w.endswith("n't") else w for w in words]


def content_terms(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _STOP}


def _signature(text: str) -> tuple[frozenset[str], frozenset[str]]:
    toks = _tokens(text)
    return frozenset(t for t in toks if t in _NEGATIONS), frozenset(t for t in toks if t.isdigit())


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of content terms, forced to 0 if negation or numbers differ.

    Lexical similarity cannot detect paraphrase, but it is cheap, deterministic and
    errs toward *not* merging, which is the safe failure mode: two separately
    tracked duplicates are harmless; a wrongly merged pair hides a disagreement.
    """
    if _signature(a) != _signature(b):
        return 0.0
    ta, tb = content_terms(a), content_terms(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
