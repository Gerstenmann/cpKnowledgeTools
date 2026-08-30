"""Stable serialization helpers for operation contracts and results."""

from __future__ import annotations

import datetime as dt
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


def to_primitive(value: Any) -> Any:
    """Convert contracts to JSON-compatible primitives without hidden behavior."""

    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_primitive(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [to_primitive(item) for item in value]
    return value
