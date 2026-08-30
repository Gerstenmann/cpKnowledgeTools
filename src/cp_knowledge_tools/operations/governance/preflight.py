"""Incremental governance preflight over existing resolver and derived cores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cp_knowledge_tools.derived.governance_state import build_governance_state
from cp_knowledge_tools.derived.impact import assess_baseline_impact, assess_impact
from cp_knowledge_tools.mcp.cp_wiki.governance import (
    ActiveArtifactNotFoundError,
    read_active_artifact,
)
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault
from cp_knowledge_tools.platform.hashing import sha256_text

from ..contracts import (
    AuthorityDecision,
    OperationRequest,
    OperationResult,
    PreflightReport,
    ResultDisposition,
)
from ..results import to_primitive
from .lifecycle_profiles import (
    UnsupportedLifecycleProfileError,
    get_lifecycle_profile,
)

_RELATIONS = (
    "governed_by",
    "depends_on",
    "aligned_with",
    "related_decisions",
    "implements_decisions",
    "validated_against",
    "supersedes",
    "references",
)


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def preflight_governance(
    *,
    vault_root: Path,
    stable_id: str,
    target_version: str | None,
    authority: AuthorityDecision,
    operation_id: str = "artifact.revise",
    document_type: str | None = None,
    path_allowed: bool = True,
) -> PreflightReport:
    vault = Vault(vault_root)
    try:
        resolution, document = read_active_artifact(vault, stable_id)
    except ActiveArtifactNotFoundError:
        if operation_id != "artifact.activate" or document_type is None:
            raise
        resolution = None
        document = None
    state = build_governance_state(vault_root)
    impact = assess_impact(state, stable_id, material_change=True)
    outgoing = (
        {
            field: tuple(
                value
                for value in document.frontmatter.get(field, [])
                if isinstance(value, str)
            )
            for field in _RELATIONS
            if isinstance(document.frontmatter.get(field), list)
        }
        if document is not None
        else {}
    )
    unsupported: list[str] = []
    lifecycle_allowed = True
    path_failure = not path_allowed
    resolved_document_type = (
        resolution.document_type if resolution is not None else document_type
    )
    try:
        profile = get_lifecycle_profile(str(resolved_document_type))
    except UnsupportedLifecycleProfileError as exc:
        unsupported.append(str(exc))
        lifecycle_allowed = False
        profile = None
    if profile is not None and operation_id not in profile.supported_operations:
        unsupported.append(
            f"{operation_id} is unsupported for {profile.document_type}"
        )
        lifecycle_allowed = False
    if (
        operation_id in {"artifact.revise", "artifact.transition"}
        and resolution is None
    ):
        unsupported.append(f"{operation_id} requires an active source line")
        lifecycle_allowed = False
    if path_failure:
        unsupported.append("requested lifecycle path violates the type profile")
        lifecycle_allowed = False
    if target_version is not None:
        try:
            if operation_id == "artifact.transition" and resolution is not None:
                version_allowed = _version_key(target_version) == _version_key(
                    resolution.version
                )
            elif resolution is not None:
                version_allowed = _version_key(target_version) > _version_key(
                    resolution.version
                )
            else:
                version_allowed = bool(
                    profile and target_version in profile.initial_versions
                )
            lifecycle_allowed = lifecycle_allowed and version_allowed
        except TypeError, ValueError:
            lifecycle_allowed = False
        if not lifecycle_allowed:
            unsupported.append("target version violates the lifecycle profile")
    if path_failure:
        disposition = ResultDisposition.BLOCKED
    elif unsupported:
        disposition = ResultDisposition.UNSUPPORTED
    elif not authority.authorized:
        disposition = ResultDisposition.BLOCKED
    else:
        disposition = ResultDisposition.SUCCEEDED
    return PreflightReport(
        disposition=disposition,
        stable_id=stable_id,
        current_state={
            "version": resolution.version if resolution is not None else None,
            "status": resolution.status if resolution is not None else "absent",
            "document_type": resolved_document_type,
            "path": resolution.relative_path if resolution is not None else None,
            "evidence_class": (
                resolution.evidence_class if resolution is not None else None
            ),
            "activation_mode": (
                "initial"
                if operation_id == "artifact.activate" and resolution is None
                else "follow_up"
                if operation_id == "artifact.activate"
                else None
            ),
        },
        rule_context={
            "CPKS-SPEC-ART": "active resolver required",
            "GOV-P01": "incremental impact",
            **(
                {
                    rule_home: "lifecycle profile rule home"
                    for rule_home in profile.rule_homes
                }
                if profile is not None
                else {}
            ),
        },
        authority_decision=authority,
        target_version=target_version,
        path_allowed=profile is not None and path_allowed,
        lifecycle_allowed=lifecycle_allowed,
        expected_source_fingerprints=(
            {
                resolution.relative_path: sha256_text(
                    vault.read_markdown(resolution.relative_path)
                )
            }
            if resolution is not None
            else {}
        ),
        outgoing_relations=outgoing,
        reverse_dependencies=tuple(sorted(impact)),
        impact_candidates={key: value.value for key, value in sorted(impact.items())},
        baseline_impact=assess_baseline_impact({"active_version"}).value,
        required_validation=(
            "identity",
            "lifecycle",
            "path",
            "references",
            "postconditions",
        ),
        supported_scope={
            "document_type": resolved_document_type,
            "identity_field": profile.identity_field if profile is not None else None,
            "lifecycle_profile": (
                profile.document_type if profile is not None else None
            ),
        },
        unsupported_reasons=tuple(unsupported),
    )


def preflight_operation(request: OperationRequest, **kwargs: Any) -> OperationResult:
    parameters = {**request.parameters, **kwargs}
    stable_id = str(parameters.get("stable_id") or request.targets[0])
    authority = parameters.get("_authority_decision")
    if not isinstance(authority, AuthorityDecision):
        authority = AuthorityDecision.evaluate(request.authority_ref, (), (stable_id,))
    report = preflight_governance(
        vault_root=Path(parameters["vault_root"]),
        stable_id=stable_id,
        target_version=parameters.get("target_version"),
        authority=authority,
        operation_id=str(parameters.get("operation_id", "artifact.revise")),
        document_type=(
            str(parameters["document_type"])
            if parameters.get("document_type")
            else None
        ),
    )
    return OperationResult(
        operation_name=request.operation_name,
        operation_version=request.operation_version,
        disposition=report.disposition,
        run_id=f"preflight-{request.fingerprint[:16]}",
        correlation_id=request.correlation_id,
        message="governance preflight completed",
        outputs={"preflight": to_primitive(report)},
    )
