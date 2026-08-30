"""Read-only standard-operation capability projection for cp-tools MCP."""

from __future__ import annotations

from typing import Any

from cp_knowledge_tools.operations.registry import build_standard_registry
from cp_knowledge_tools.operations.results import to_primitive


def resolve_standard_operation(
    operation_id: str,
    operation_version: str = "0.1",
) -> dict[str, Any]:
    """Resolve capability metadata without executing an operation."""

    registered = build_standard_registry().resolve(operation_id, operation_version)
    payload = to_primitive(registered.spec)
    payload["read_only"] = True
    return payload
