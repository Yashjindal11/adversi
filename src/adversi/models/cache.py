"""Response caches keyed on the full request (model, messages, params, tools, schema)."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

from adversi.providers.base import ModelRequest, ModelResponse


def request_key(provider: str, request: ModelRequest) -> str:
    body = request.model_dump_json(exclude={"metadata"})
    return hashlib.sha256(f"{provider}\x00{body}".encode()).hexdigest()


@runtime_checkable
class ResponseCache(Protocol):
    def get(self, key: str) -> ModelResponse | None: ...

    def set(self, key: str, response: ModelResponse) -> None: ...


class MemoryCache:
    def __init__(self, max_entries: int = 10_000) -> None:
        self._data: dict[str, str] = {}
        self.max_entries = max_entries

    def get(self, key: str) -> ModelResponse | None:
        raw = self._data.get(key)
        return ModelResponse.model_validate_json(raw) if raw else None

    def set(self, key: str, response: ModelResponse) -> None:
        if len(self._data) >= self.max_entries:
            self._data.pop(next(iter(self._data)))
        self._data[key] = response.model_dump_json()


class SQLiteCache:
    """Persistent cache in a single SQLite file. Safe for one process with many tasks."""

    def __init__(self, path: str | Path = ".adversi/cache.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, body TEXT)")
        self._conn.commit()

    def get(self, key: str) -> ModelResponse | None:
        with self._lock:
            row = self._conn.execute("SELECT body FROM responses WHERE key = ?", (key,)).fetchone()
        return ModelResponse.model_validate_json(row[0]) if row else None

    def set(self, key: str, response: ModelResponse) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO responses (key, body) VALUES (?, ?)",
                (key, response.model_dump_json()),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()
