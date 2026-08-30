"""Rebuildable derived-governance-state refresh using the existing core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cp_knowledge_tools.derived.governance_state import build_governance_state
from cp_knowledge_tools.platform.hashing import canonical_json_hash

from .contracts import OperationRequest, OperationResult, ResultDisposition, utc_now


def refresh_operation(request: OperationRequest, **kwargs: Any) -> OperationResult:
    parameters = {**request.parameters, **kwargs}
    vault_root = Path(parameters["vault_root"]).resolve()
    run_root = Path(parameters["run_root"]).resolve()
    state = build_governance_state(vault_root)
    state_payload = state.as_dict()
    active_versions = {
        stable_id: record.version for stable_id, record in sorted(state.active.items())
    }
    lifecycle_view = {
        f"{record.artifact_id}@{record.version}": {
            "status": record.status,
            "evidence_class": record.evidence_class,
            "path": record.path,
        }
        for record in sorted(
            state.all_records,
            key=lambda item: (item.artifact_id, item.version, item.path),
        )
    }
    impact_view = {
        stable_id: sorted({edge.consumer_id for edge in edges})
        for stable_id, edges in sorted(state.reverse_dependencies.items())
    }
    payload = {
        "schema": "cpks.derived_governance_state",
        "schema_version": "0.1",
        "non_normative": True,
        "input_fingerprint": canonical_json_hash(state_payload),
        "input_fingerprints": {
            "canonical_governance_state": canonical_json_hash(state_payload)
        },
        "rule_versions": active_versions,
        "tool_version": "0.1.0",
        "produced_at": utc_now(),
        "lifecycle_view": lifecycle_view,
        "impact_view": impact_view,
        **state_payload,
    }
    target = run_root / "derived" / "governance-state.json"
    mutations: tuple[str, ...] = ()
    if request.requested_mode == "apply":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        mutations = (str(target),)
    return OperationResult(
        operation_name=request.operation_name,
        operation_version=request.operation_version,
        disposition=ResultDisposition.SUCCEEDED,
        run_id=f"derived-{payload['input_fingerprint'][:16]}",
        correlation_id=request.correlation_id,
        message="derived governance state rebuilt from canonical inputs",
        outputs={
            "output_path": str(target),
            "written": request.requested_mode == "apply",
            "input_fingerprint": payload["input_fingerprint"],
            "active_count": len(state.active),
        },
        actual_mutations=mutations,
    )
