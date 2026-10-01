"""User-provided documents and lexical retrieval over them (BM25, no dependencies)."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from adversi.tools.base import Tool

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class Document(BaseModel):
    """A user-supplied document. Becomes a ``user_provided`` source at run start."""

    content: str
    title: str | None = None
    uri: str | None = None


@dataclass
class _Chunk:
    source_id: str
    title: str | None
    text: str
    tokens: list[str]


class DocumentIndex:
    """BM25 over fixed-size, overlapping chunks of registered sources."""

    def __init__(
        self, chunk_chars: int = 1200, overlap: int = 200, k1: float = 1.5, b: float = 0.75
    ) -> None:
        self.chunk_chars = chunk_chars
        self.overlap = overlap
        self.k1 = k1
        self.b = b
        self.chunks: list[_Chunk] = []
        self._df: Counter[str] = Counter()

    def add(self, source_id: str, text: str, title: str | None = None) -> None:
        step = max(1, self.chunk_chars - self.overlap)
        for start in range(0, max(1, len(text)), step):
            piece = text[start : start + self.chunk_chars]
            if not piece.strip():
                continue
            tokens = tokenize(piece)
            self.chunks.append(_Chunk(source_id, title, piece, tokens))
            self._df.update(set(tokens))
            if start + self.chunk_chars >= len(text):
                break

    def search(self, query: str, k: int = 5) -> list[tuple[float, _Chunk]]:
        if not self.chunks:
            return []
        n = len(self.chunks)
        avgdl = sum(len(c.tokens) for c in self.chunks) / n
        q = tokenize(query)
        scored = []
        for chunk in self.chunks:
            tf = Counter(chunk.tokens)
            score = 0.0
            for term in q:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                f = tf[term]
                score += (
                    idf
                    * f
                    * (self.k1 + 1)
                    / (f + self.k1 * (1 - self.b + self.b * len(chunk.tokens) / avgdl))
                )
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:k]


def search_documents_tool(index_provider: Callable[[], DocumentIndex], *, k: int = 5) -> Tool:
    """Retrieval over the run's user-provided documents. Results reference existing source ids."""

    def search_documents(query: str) -> str:
        hits = index_provider().search(query, k)
        if not hits:
            return "No matching passages."
        return "\n\n".join(
            f"[{chunk.source_id}] {chunk.title or ''} (score {score:.2f})\n{chunk.text}"
            for score, chunk in hits
        )

    return Tool(
        "search_documents",
        "Search the user-provided documents. Each passage is prefixed with its source id; "
        "cite it by that id and quote verbatim.",
        search_documents,
        timeout_s=10.0,
    )


def load_documents(paths: Sequence[str]) -> list[Document]:
    from pathlib import Path

    docs = []
    for p in paths:
        path = Path(p)
        docs.append(
            Document(
                content=path.read_text(encoding="utf-8", errors="replace"),
                title=path.name,
                uri=path.resolve().as_uri(),
            )
        )
    return docs
