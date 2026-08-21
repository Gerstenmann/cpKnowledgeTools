from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from cp_knowledge_tools.platform.hashing import canonical_json_hash


def ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): canonical_value(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [canonical_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported lifecycle contract value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def local_ref(prefix: str, value: Any, *, length: int = 24) -> str:
    return f"{prefix}-{canonical_json_hash(canonical_value(value))[:length]}"


def content_hash(value: Any) -> str:
    return canonical_json_hash(canonical_value(value))
