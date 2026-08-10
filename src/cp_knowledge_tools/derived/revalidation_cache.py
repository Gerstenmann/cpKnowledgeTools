"""Cache revalidation results by deterministic input signature."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def canonical_signature(value: Any) -> str:
    """Return a deterministic, lossless JSON signature for exact equality checks."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class CacheEntry:
    signature: str
    result: dict[str, Any]


class RevalidationCache:
    """Small rebuildable cache; stale signatures are never treated as revalidation."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._entries: dict[str, CacheEntry] = {}
        if path is not None and path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            for key, item in raw.get("entries", {}).items():
                self._entries[key] = CacheEntry(
                    signature=item["signature"], result=item["result"]
                )

    def get(self, cache_key: str, inputs: Any) -> dict[str, Any] | None:
        entry = self._entries.get(cache_key)
        signature = canonical_signature(inputs)
        if entry is None or entry.signature != signature:
            return None
        return dict(entry.result)

    def put(self, cache_key: str, inputs: Any, result: dict[str, Any]) -> None:
        self._entries[cache_key] = CacheEntry(
            signature=canonical_signature(inputs),
            result=dict(result),
        )
        self.flush()

    def invalidate(self, cache_key: str) -> None:
        self._entries.pop(cache_key, None)
        self.flush()

    def flush(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "cpks-revalidation-cache-v1",
            "entries": {
                key: {"signature": entry.signature, "result": entry.result}
                for key, entry in sorted(self._entries.items())
            },
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
