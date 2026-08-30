"""Construction of immutable operation-context evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import (
    AuthorityDecision,
    EnvironmentKind,
    OperationContext,
    OperationRequest,
    TargetKind,
)

_TARGET_CLASSIFICATIONS = frozenset({"test", "live", "other"})


@dataclass(frozen=True, slots=True)
class VerifiedExecutionTarget:
    root: Path
    target_kind: TargetKind
    environment_kind: EnvironmentKind
    environment_identity: str
    classification: str


def verify_execution_target(
    root: Path,
    *,
    target_kind: TargetKind,
    environment_kind: EnvironmentKind,
    classification: str,
) -> VerifiedExecutionTarget:
    """Verify a mutation root without deriving authority from its path."""

    if classification not in _TARGET_CLASSIFICATIONS:
        raise ValueError("target classification must be test, live, or other")
    if root.is_symlink():
        raise ValueError("mutation root must not be a symlink")
    resolved = root.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"mutation root does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"mutation root is not a directory: {resolved}")
    return VerifiedExecutionTarget(
        root=resolved,
        target_kind=target_kind,
        environment_kind=environment_kind,
        environment_identity=resolved.as_uri(),
        classification=classification,
    )


def build_operation_context(
    request: OperationRequest,
    *,
    target_system: str,
    vault_root: Path | None,
    repo_root: Path | None,
    run_root: Path | None,
    actual_current_state: dict[str, Any],
    active_rule_homes: dict[str, str],
    rule_home_integrity: dict[str, bool],
    authority_decision: AuthorityDecision,
    execution_target: VerifiedExecutionTarget,
    expected_source_fingerprints: dict[str, str | None],
    mutation_class: str,
    document_type: str | None = None,
    identity_field: str | None = None,
    lifecycle_profile: str | None = None,
    stable_id: str | None = None,
    target_version: str | None = None,
) -> OperationContext:
    enriched_current_state = dict(actual_current_state)
    if document_type is not None:
        enriched_current_state["document_type"] = document_type
    if identity_field is not None:
        enriched_current_state["identity_field"] = identity_field
    return OperationContext(
        operation_name=request.operation_name,
        operation_version=request.operation_version,
        target_system=target_system,
        vault_root=str(vault_root.resolve()) if vault_root else None,
        repo_root=str(repo_root.resolve()) if repo_root else None,
        run_root=str(run_root.resolve()) if run_root else None,
        verified_roots={"mutation_root": str(execution_target.root)},
        target_environment={
            "target_kind": execution_target.target_kind.value,
            "kind": execution_target.environment_kind.value,
            "identity": execution_target.environment_identity,
            "classification": execution_target.classification,
        },
        targets=request.targets,
        actual_current_state=enriched_current_state,
        active_rule_homes=active_rule_homes,
        rule_home_integrity=rule_home_integrity,
        authority_basis=(
            (
                f"{authority_decision.authority_ref}"
                f"@{authority_decision.authority_version}"
            ),
        )
        if authority_decision.authority_ref and authority_decision.authority_version
        else (),
        authority_scope=(
            authority_decision.runtime_contract.scope.mutation_scope
            if authority_decision.runtime_contract is not None
            else ()
        ),
        runtime_authority=(
            authority_decision.runtime_contract.as_mapping()
            if authority_decision.runtime_contract is not None
            else {
                "disposition": authority_decision.disposition.value,
                "reasons": list(authority_decision.reasons),
            }
        ),
        preserve=(
            "canonical source authority",
            "body content unless owner-prepared",
            "versioned evidence fields",
        ),
        out_of_scope=(
            "live-vault agent write",
            "remote effect",
            "baseline lifecycle",
            "coupled multi-artifact lifecycle",
        ),
        lifecycle_profile=lifecycle_profile,
        validation_profile="active_governance",
        mutation_class=mutation_class,
        remote_boundaries=("no_push", "no_merge", "no_release", "no_deploy"),
        implementation_versions={"contract": "0.1"},
        expected_source_fingerprints=expected_source_fingerprints,
        correlation_id=request.correlation_id,
        run_id=f"run-{uuid.uuid4().hex}",
        document_type=document_type,
        identity_field=identity_field,
        stable_id=stable_id,
        target_version=target_version,
    )
