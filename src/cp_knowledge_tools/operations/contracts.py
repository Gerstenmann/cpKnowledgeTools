"""Versioned immutable contracts for the CPKS Operation Kernel."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from cp_knowledge_tools.mcp.cp_wiki.governance import STABLE_ID_PATTERN
from cp_knowledge_tools.platform.hashing import canonical_json_hash

CONTRACT_VERSION = "0.1"


def utc_now() -> str:
    """Return a complete timezone-aware ISO-8601 technical event timestamp."""

    return dt.datetime.now(dt.UTC).isoformat()


class OperationClass(StrEnum):
    QUERY = "QUERY"
    VALIDATE = "VALIDATE"
    PLAN = "PLAN"
    DERIVE = "DERIVE"
    MUTATE_LOCAL = "MUTATE_LOCAL"
    MUTATE_COUPLED = "MUTATE_COUPLED"
    EXTERNAL_EFFECT = "EXTERNAL_EFFECT"


class AuthorityDisposition(StrEnum):
    AUTHORIZED = "authorized"
    BLOCKED = "blocked"
    OWNER_DECISION_REQUIRED = "owner_decision_required"
    REVIEW_REQUIRED = "review_required"
    CONFLICT = "conflict"
    UNSUPPORTED = "unsupported"


class AuthorityClass(StrEnum):
    WORK_PACKAGE = "work_package"
    DECISION_RECORD = "decision_record"
    PROCESS = "process"
    OWNER_APPROVAL = "owner_approval"


class TargetKind(StrEnum):
    CP_WIKI = "cp-wiki"
    REPOSITORY = "repository"
    RUNTIME = "runtime"
    REMOTE_VCS = "remote-vcs"
    EXTERNAL_SYSTEM = "external-system"
    OTHER = "other"


class EnvironmentKind(StrEnum):
    LOCAL_VAULT = "local_vault"
    LOCAL_REPOSITORY = "local_repository"
    REMOTE_VCS = "remote_vcs"
    RUNTIME = "runtime"
    EXTERNAL_SYSTEM = "external-system"
    OTHER = "other"


class ResultDisposition(StrEnum):
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    CONFLICT = "conflict"
    UNSUPPORTED = "unsupported"
    OWNER_DECISION_REQUIRED = "owner_decision_required"
    REVIEW_REQUIRED = "review_required"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    FAILED_BEFORE_MUTATION = "failed_before_mutation"
    VALIDATION_FAILED_BEFORE_COMMIT = "validation_failed_before_commit"
    COMPENSATED_FAILURE = "compensated_failure"
    FATAL_PARTIAL_STATE = "fatal_partial_state"
    RECOVERY_REQUIRED = "recovery_required"


class MutationKind(StrEnum):
    CREATE = "CREATE"
    REPLACE = "REPLACE"
    MOVE = "MOVE"
    DELETE = "DELETE"


class RunState(StrEnum):
    REQUESTED = "REQUESTED"
    CONTEXT_RESOLVED = "CONTEXT_RESOLVED"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    PLANNED = "PLANNED"
    PREVIEWED = "PREVIEWED"
    AWAITING_AUTHORITY = "AWAITING_AUTHORITY"
    AUTHORIZED = "AUTHORIZED"
    STAGING = "STAGING"
    APPLYING = "APPLYING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    PARTIAL_STATE_DETECTED = "PARTIAL_STATE_DETECTED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED_FAILURE = "COMPENSATED_FAILURE"
    FATAL_PARTIAL_STATE = "FATAL_PARTIAL_STATE"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation_id: str
    operation_version: str
    operation_class: OperationClass
    supported_modes: tuple[str, ...]
    target_classes: tuple[str, ...]
    required_inputs: tuple[str, ...]
    supported_scope: dict[str, Any]
    unsupported_scope: tuple[str, ...]
    surface_mappings: dict[str, str]
    handler_ref: str
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class OperationRequest:
    operation_name: str
    operation_version: str
    targets: tuple[str, ...]
    requested_mode: str
    requester_ref: str | None = None
    authority_ref: str | None = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_current_state: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION

    @property
    def fingerprint(self) -> str:
        return canonical_json_hash(
            {
                "operation_name": self.operation_name,
                "operation_version": self.operation_version,
                "targets": list(self.targets),
                "requested_mode": self.requested_mode,
                "requester_ref": self.requester_ref,
                "authority_ref": self.authority_ref,
                "parameters": self.parameters,
                "expected_current_state": self.expected_current_state,
            }
        )


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _string(value: Any, field_name: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean")
    return value


def _strings(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list")
    result = tuple(_string(item, field_name) for item in value)
    if any(item in {"*", "all", "any", "system-wide"} for item in result):
        raise ValueError(f"{field_name} must not contain wildcard scope")
    return result


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityReference:
    ref: str
    version: str | None
    authority_class: AuthorityClass
    issuer: str


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityTarget:
    stable_id: str
    version: str | None
    artifact_class: str
    target_kind: TargetKind


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityScope:
    document_types: tuple[str, ...]
    mutation_scope: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityEnvironment:
    kind: EnvironmentKind
    identity: str


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityEffects:
    mutate: bool
    activate: bool
    remote_effects: bool


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityValidity:
    effective_from: str
    expires_at: str | None


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityApproval:
    required: bool
    approved_by: str | None
    approved_at: str | None
    evidence_ref: str | None


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityContract:
    """Immutable semantic representation of ``cpks.runtime_authority@0.1``."""

    authority: RuntimeAuthorityReference
    operations: tuple[str, ...]
    targets: tuple[RuntimeAuthorityTarget, ...]
    scope: RuntimeAuthorityScope
    environment: RuntimeAuthorityEnvironment
    effects: RuntimeAuthorityEffects
    validity: RuntimeAuthorityValidity
    approval: RuntimeAuthorityApproval
    contract: str = "cpks.runtime_authority"
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RuntimeAuthorityContract:
        root = _mapping(value, "runtime authority contract")
        if root.get("contract") != "cpks.runtime_authority":
            raise ValueError("unsupported runtime authority contract")
        if root.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("unsupported runtime authority contract version")

        authority = _mapping(root.get("authority"), "authority")
        target_values = root.get("targets")
        if not isinstance(target_values, (list, tuple)):
            raise ValueError("targets must be a list")
        targets: list[RuntimeAuthorityTarget] = []
        for index, raw_target in enumerate(target_values):
            target = _mapping(raw_target, f"targets[{index}]")
            stable_id = _string(target.get("stable_id"), f"targets[{index}].stable_id")
            if stable_id in {"*", "all", "any", "system-wide"} or not (
                isinstance(stable_id, str) and STABLE_ID_PATTERN.fullmatch(stable_id)
            ):
                raise ValueError("authority targets must be concrete stable IDs")
            targets.append(
                RuntimeAuthorityTarget(
                    stable_id=stable_id,
                    version=_string(
                        target.get("version"),
                        f"targets[{index}].version",
                        optional=True,
                    ),
                    artifact_class=_string(
                        target.get("artifact_class"),
                        f"targets[{index}].artifact_class",
                    ),
                    target_kind=TargetKind(
                        _string(
                            target.get("target_kind"),
                            f"targets[{index}].target_kind",
                        )
                    ),
                )
            )

        scope = _mapping(root.get("scope"), "scope")
        environment = _mapping(root.get("environment"), "environment")
        effects = _mapping(root.get("effects"), "effects")
        validity = _mapping(root.get("validity"), "validity")
        approval = _mapping(root.get("approval"), "approval")
        return cls(
            authority=RuntimeAuthorityReference(
                ref=_string(authority.get("ref"), "authority.ref"),
                version=_string(
                    authority.get("version"), "authority.version", optional=True
                ),
                authority_class=AuthorityClass(
                    _string(authority.get("class"), "authority.class")
                ),
                issuer=_string(authority.get("issuer"), "authority.issuer"),
            ),
            operations=_strings(root.get("operations"), "operations"),
            targets=tuple(targets),
            scope=RuntimeAuthorityScope(
                document_types=_strings(
                    scope.get("document_types"), "scope.document_types"
                ),
                mutation_scope=_strings(
                    scope.get("mutation_scope"), "scope.mutation_scope"
                ),
            ),
            environment=RuntimeAuthorityEnvironment(
                kind=EnvironmentKind(
                    _string(environment.get("kind"), "environment.kind")
                ),
                identity=_string(environment.get("identity"), "environment.identity"),
            ),
            effects=RuntimeAuthorityEffects(
                mutate=_boolean(effects.get("mutate"), "effects.mutate"),
                activate=_boolean(effects.get("activate"), "effects.activate"),
                remote_effects=_boolean(
                    effects.get("remote_effects"), "effects.remote_effects"
                ),
            ),
            validity=RuntimeAuthorityValidity(
                effective_from=_string(
                    validity.get("effective_from"), "validity.effective_from"
                ),
                expires_at=_string(
                    validity.get("expires_at"),
                    "validity.expires_at",
                    optional=True,
                ),
            ),
            approval=RuntimeAuthorityApproval(
                required=_boolean(approval.get("required"), "approval.required"),
                approved_by=_string(
                    approval.get("approved_by"), "approval.approved_by", optional=True
                ),
                approved_at=_string(
                    approval.get("approved_at"), "approval.approved_at", optional=True
                ),
                evidence_ref=_string(
                    approval.get("evidence_ref"),
                    "approval.evidence_ref",
                    optional=True,
                ),
            ),
        )

    @property
    def contract_id(self) -> str:
        return f"{self.contract}@{self.contract_version}"

    @property
    def fingerprint(self) -> str:
        return canonical_json_hash(self.as_mapping())

    def as_mapping(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "contract_version": self.contract_version,
            "authority": {
                "ref": self.authority.ref,
                "version": self.authority.version,
                "class": self.authority.authority_class.value,
                "issuer": self.authority.issuer,
            },
            "operations": list(self.operations),
            "targets": [
                {
                    "stable_id": target.stable_id,
                    "version": target.version,
                    "artifact_class": target.artifact_class,
                    "target_kind": target.target_kind.value,
                }
                for target in self.targets
            ],
            "scope": {
                "document_types": list(self.scope.document_types),
                "mutation_scope": list(self.scope.mutation_scope),
            },
            "environment": {
                "kind": self.environment.kind.value,
                "identity": self.environment.identity,
            },
            "effects": {
                "mutate": self.effects.mutate,
                "activate": self.effects.activate,
                "remote_effects": self.effects.remote_effects,
            },
            "validity": {
                "effective_from": self.validity.effective_from,
                "expires_at": self.validity.expires_at,
            },
            "approval": {
                "required": self.approval.required,
                "approved_by": self.approval.approved_by,
                "approved_at": self.approval.approved_at,
                "evidence_ref": self.approval.evidence_ref,
            },
        }


@dataclass(frozen=True, slots=True)
class OperationContext:
    operation_name: str
    operation_version: str
    target_system: str
    vault_root: str | None
    repo_root: str | None
    run_root: str | None
    verified_roots: dict[str, str]
    target_environment: dict[str, str]
    targets: tuple[str, ...]
    actual_current_state: dict[str, Any]
    active_rule_homes: dict[str, str]
    rule_home_integrity: dict[str, bool]
    authority_basis: tuple[str, ...]
    authority_scope: tuple[str, ...]
    runtime_authority: dict[str, Any]
    preserve: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    lifecycle_profile: str | None
    validation_profile: str | None
    mutation_class: str
    remote_boundaries: tuple[str, ...]
    implementation_versions: dict[str, str]
    expected_source_fingerprints: dict[str, str | None]
    correlation_id: str
    run_id: str
    document_type: str | None = None
    identity_field: str | None = None
    stable_id: str | None = None
    target_version: str | None = None
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    disposition: AuthorityDisposition
    authority_ref: str | None
    targets: tuple[str, ...]
    authority_version: str | None = None
    authority_class: AuthorityClass | None = None
    issuer: str | None = None
    runtime_contract: RuntimeAuthorityContract | None = None
    source_path: str | None = None
    source_fingerprint: str | None = None
    checks: tuple[dict[str, Any], ...] = ()
    reasons: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def evaluate(
        cls,
        authority_ref: str | None,
        authority_scope: tuple[str, ...],
        targets: tuple[str, ...],
    ) -> AuthorityDecision:
        del authority_scope
        return cls(
            disposition=AuthorityDisposition.BLOCKED,
            authority_ref=authority_ref,
            targets=targets,
            reasons=(
                "caller-supplied authority scope is non-authoritative; "
                "runtime authority must be independently resolved",
            ),
        )

    @property
    def authorized(self) -> bool:
        return self.disposition is AuthorityDisposition.AUTHORIZED


@dataclass(frozen=True, slots=True)
class ImpactAssessment:
    candidates: dict[str, str]
    baseline_impact: str
    full_scan_performed: bool = False
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class PreflightReport:
    disposition: ResultDisposition
    stable_id: str
    current_state: dict[str, Any]
    rule_context: dict[str, str]
    authority_decision: AuthorityDecision
    target_version: str | None
    path_allowed: bool
    lifecycle_allowed: bool
    expected_source_fingerprints: dict[str, str | None]
    outgoing_relations: dict[str, tuple[str, ...]]
    reverse_dependencies: tuple[str, ...]
    impact_candidates: dict[str, str]
    baseline_impact: str
    required_validation: tuple[str, ...]
    supported_scope: dict[str, Any]
    unsupported_reasons: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class Postcondition:
    code: str
    description: str
    expected: Any = None
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class PostconditionReport:
    passed: bool
    results: tuple[dict[str, Any], ...]
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class OperationPlan:
    plan_id: str
    request_fingerprint: str
    inputs: dict[str, Any]
    expected_source_fingerprints: dict[str, str | None]
    targets: tuple[str, ...]
    actions: tuple[str, ...]
    dependencies: tuple[str, ...]
    expected_new_states: dict[str, Any]
    precommit_validations: tuple[str, ...]
    postconditions: tuple[Postcondition, ...]
    compensation_actions: tuple[str, ...]
    derived_actions: tuple[str, ...]
    authority_gates: tuple[str, ...]
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class MutationAction:
    kind: MutationKind
    path: str
    destination: str | None = None
    content: str | bytes | None = None
    expected_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class MutationPlan:
    plan_id: str
    request_fingerprint: str
    actions: tuple[MutationAction, ...]
    expected_source_fingerprints: dict[str, str | None]
    postconditions: tuple[Postcondition, ...] = ()
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class RecoveryRecord:
    recovery_id: str
    run_id: str
    mutation_state: str
    changed_paths: tuple[str, ...]
    required_actions: tuple[str, ...]
    created_at: str
    compensation_error: str | None = None
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class OperationResult:
    operation_name: str
    operation_version: str
    disposition: ResultDisposition
    run_id: str
    correlation_id: str
    message: str
    outputs: dict[str, Any] = field(default_factory=dict)
    actual_mutations: tuple[str, ...] = ()
    validation_results: tuple[dict[str, Any], ...] = ()
    postcondition_report: PostconditionReport | None = None
    compensation_status: str = "none"
    recovery_record: RecoveryRecord | None = None
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class TechnicalRunEvidence:
    run_id: str
    correlation_id: str
    operation_name: str
    operation_version: str
    scope: dict[str, Any]
    authority_context: dict[str, Any]
    versions: dict[str, str]
    inputs: dict[str, Any]
    fingerprints: dict[str, str | None]
    plan_ref: str | None
    preview_ref: str | None
    actual_mutations: tuple[str, ...]
    validation_results: tuple[dict[str, Any], ...]
    postconditions: tuple[dict[str, Any], ...]
    outputs: dict[str, Any]
    disposition: ResultDisposition
    compensation_status: str
    recovery_status: str
    event_timestamps: dict[str, str]
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def create(
        cls,
        *,
        started_at: str,
        completed_at: str,
        **values: Any,
    ) -> TechnicalRunEvidence:
        values["event_timestamps"] = {
            "started_at": started_at,
            "completed_at": completed_at,
        }
        return cls(**values)


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    schema: str
    schema_version: str
    incident_id: str
    captured_at: str
    capture: dict[str, Any]
    context: dict[str, Any]
    exec: dict[str, Any]
    failure: dict[str, Any]
    mutation: dict[str, Any]
    analysis: dict[str, Any]
    correction: dict[str, Any]
    relations: dict[str, Any]
    status: str

    @classmethod
    def create(
        cls,
        *,
        capture_mode: str,
        failure_phase: str,
        mutation_state: str,
        details: dict[str, Any] | None = None,
        relations: dict[str, Any] | None = None,
    ) -> IncidentRecord:
        now = dt.datetime.now(dt.UTC)
        suffix = uuid.uuid4().hex[:6]
        incident_id = f"EXF-{now:%Y%m%d-%H%M%S}-{suffix}"
        details = dict(details or {})
        terminal_output = details.pop("terminal_output", None)
        return cls(
            schema="cpks.exec_failure",
            schema_version="0.1",
            incident_id=incident_id,
            captured_at=now.isoformat(),
            capture={
                "mode": capture_mode,
                "source": "codex_execution",
                "completeness": "best_effort",
            },
            context={},
            exec={},
            failure={
                "phase": failure_phase,
                "category": "unknown",
                "terminal_output": terminal_output,
                **details,
            },
            mutation={
                "state": mutation_state,
                "changed_paths": [],
                "rollback_required": None,
                "rollback_completed": None,
            },
            analysis={
                "confidence": "unknown",
                "immediate_cause": None,
                "design_cause": None,
                "control_gap": None,
            },
            correction={
                "next_exec_revision": None,
                "change_summary": None,
                "preventive_control": None,
                "regression_test_added": None,
            },
            relations=relations or {"recurrence_of": [], "caused_by_fix_of": None},
            status="observed",
        )
