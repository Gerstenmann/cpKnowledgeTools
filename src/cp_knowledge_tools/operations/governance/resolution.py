"""Read-only governance resolution using the existing canonical resolver."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from cp_knowledge_tools.mcp.cp_wiki.governance import read_active_artifact
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault
from cp_knowledge_tools.platform.hashing import sha256_text

from ..contracts import OperationRequest, OperationResult, ResultDisposition


def resolve_governance(vault: Vault, stable_id: str) -> dict[str, Any]:
    resolution, document = read_active_artifact(vault, stable_id)
    raw = vault.read_markdown(document.relative_path)
    payload = asdict(resolution)
    payload["integrity_issues"] = [
        asdict(issue) for issue in resolution.integrity_issues
    ]
    payload["current_state_fingerprint"] = sha256_text(raw)
    payload["relevant_rule_homes"] = tuple(
        value
        for value in document.frontmatter.get("governed_by", [])
        if isinstance(value, str)
    )
    return payload


def resolve_operation(request: OperationRequest, **kwargs: Any) -> OperationResult:
    parameters = {**request.parameters, **kwargs}
    payload = resolve_governance(
        Vault(Path(parameters["vault_root"])),
        str(parameters.get("stable_id") or request.targets[0]),
    )
    return OperationResult(
        operation_name=request.operation_name,
        operation_version=request.operation_version,
        disposition=ResultDisposition.SUCCEEDED,
        run_id=f"resolve-{payload['current_state_fingerprint'][:16]}",
        correlation_id=request.correlation_id,
        message="active governance artifact resolved and verified",
        outputs=payload,
    )
