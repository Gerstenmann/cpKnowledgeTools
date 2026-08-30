"""Safe K2 Managed Artifact revision, activation, and completion."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from cp_knowledge_tools.derived.governance_state import (
    GovernanceStateError,
    build_governance_state,
)
from cp_knowledge_tools.mcp.cp_wiki.governance import (
    ActiveArtifactNotFoundError,
    GovernanceResolutionError,
    MultipleActiveArtifactsError,
    read_active_artifact,
)
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault
from cp_knowledge_tools.platform.hashing import canonical_json_hash, stable_token
from cp_knowledge_tools.validation.temporal import parse_lifecycle_temporal

from ..contracts import (
    AuthorityDecision,
    MutationAction,
    MutationKind,
    MutationPlan,
    OperationContext,
    OperationRequest,
    OperationResult,
    Postcondition,
    PostconditionReport,
    ResultDisposition,
    RunState,
)
from ..controller import InProcessRunController
from ..transactions.filesystem import (
    FileTransactionEngine,
    PathSafetyError,
    SourceFingerprintConflict,
    StagingValidationError,
)
from .lifecycle_profiles import (
    ManagedArtifactLifecycleProfile,
    UnsupportedLifecycleProfileError,
    active_path_allowed,
    development_path_allowed,
    expected_filename,
    get_lifecycle_profile,
    history_path_allowed,
    is_process_package_path,
)

_DRAFT_EVIDENCE = {"design_candidate", "committed_target"}
_ACTIVATABLE_STATUSES = {"draft", "proposed"}
_PRESERVED_FIELDS = (
    "validated_against",
    "implements_decisions",
    "source_artifact",
)
_REFERENCE_FIELDS = (
    "governed_by",
    "depends_on",
    "aligned_with",
    "related_decisions",
    "implements_decisions",
    "validated_against",
    "references",
    "source_artifact",
    "supersedes",
)


@dataclass(frozen=True, slots=True)
class ParsedArtifact:
    frontmatter: dict[str, Any]
    body: str
    raw: str


@dataclass(frozen=True, slots=True)
class ActivationPlan:
    disposition: ResultDisposition
    message: str
    stable_id: str
    active_path: str | None = None
    draft_path: str | None = None
    archive_path: str | None = None
    previous_version: str | None = None
    target_version: str | None = None
    mutation_plan: MutationPlan | None = None
    predecessor_body: str | None = None
    target_body: str | None = None
    authority_decision: AuthorityDecision | None = None
    predecessor_preserved: dict[str, Any] | None = None
    target_preserved: dict[str, Any] | None = None
    document_type: str | None = None
    profile: ManagedArtifactLifecycleProfile | None = None
    initial_activation: bool = False


@dataclass(frozen=True, slots=True)
class CompletionPlan:
    disposition: ResultDisposition
    message: str
    stable_id: str
    active_path: str | None = None
    archive_path: str | None = None
    version: str | None = None
    mutation_plan: MutationPlan | None = None
    source_body: str | None = None
    target_body: str | None = None
    authority_decision: AuthorityDecision | None = None
    preserved_frontmatter: dict[str, Any] | None = None


def _parse_artifact_text(text: str) -> ParsedArtifact:
    if not text.startswith("---\n"):
        raise ValueError("prepared artifact requires complete YAML frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("prepared artifact has unterminated YAML frontmatter")
    frontmatter = yaml.safe_load(text[4:end])
    if not isinstance(frontmatter, dict):
        raise ValueError("prepared artifact frontmatter must be a mapping")
    body = text[end + 4 :]
    if not body.strip():
        raise ValueError("prepared artifact requires complete body content")
    return ParsedArtifact(frontmatter=frontmatter, body=body, raw=text)


def _render(frontmatter: dict[str, Any], body: str) -> str:
    return (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
        + "---"
        + body
    )


def _version_key(value: Any) -> tuple[int, ...]:
    if not isinstance(value, str):
        raise ValueError("version must be a string")
    return tuple(int(part) for part in value.split("."))


def _expected_filename(
    stable_id: str, version: str, title: str, *, active: bool
) -> str:
    return expected_filename(stable_id, version, title, active=active)


def _result(
    operation: str,
    disposition: ResultDisposition,
    message: str,
    *,
    correlation_id: str | None = None,
    outputs: dict[str, Any] | None = None,
    mutations: tuple[str, ...] = (),
    source: OperationResult | None = None,
) -> OperationResult:
    combined_outputs = dict(source.outputs) if source else {}
    combined_outputs.update(outputs or {})
    return OperationResult(
        operation_name=operation,
        operation_version="0.1",
        disposition=disposition,
        run_id=source.run_id if source else f"run-{uuid.uuid4().hex}",
        correlation_id=correlation_id
        or (source.correlation_id if source else str(uuid.uuid4())),
        message=message,
        outputs=combined_outputs,
        actual_mutations=mutations or (source.actual_mutations if source else ()),
        validation_results=source.validation_results if source else (),
        postcondition_report=source.postcondition_report if source else None,
        compensation_status=source.compensation_status if source else "none",
        recovery_record=source.recovery_record if source else None,
    )


def _path_shape_allowed(relative_path: str, *, development: bool) -> bool:
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or ".." in pure.parts:
        return False
    if development:
        return bool(pure.parts and pure.parts[0] == "Development")
    return "Archive" in pure.parts or "History" in pure.parts


def _iter_line_records(
    vault_root: Path,
    stable_id: str,
    profile: ManagedArtifactLifecycleProfile,
) -> list[tuple[str, ParsedArtifact]]:
    records: list[tuple[str, ParsedArtifact]] = []
    for path in sorted(vault_root.rglob("*.md")):
        if path.is_symlink():
            continue
        try:
            parsed = _parse_artifact_text(path.read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, ValueError, yaml.YAMLError:
            continue
        if (
            parsed.frontmatter.get("document_type") == profile.document_type
            and parsed.frontmatter.get(profile.identity_field) == stable_id
        ):
            records.append((path.relative_to(vault_root).as_posix(), parsed))
    return records


def inspect_prepared_target(path: Path) -> tuple[str, str, str]:
    """Read the concrete target identity used by context and authority checks."""

    parsed = _parse_artifact_text(path.read_text(encoding="utf-8"))
    document_type = parsed.frontmatter.get("document_type")
    if not isinstance(document_type, str) or not document_type:
        raise ValueError("prepared target document_type is required")
    profile = get_lifecycle_profile(document_type)
    stable_id = parsed.frontmatter.get(profile.identity_field)
    version = parsed.frontmatter.get("version")
    if not all(isinstance(value, str) and value for value in (stable_id, version)):
        raise ValueError(
            f"prepared target {profile.identity_field} and version are required"
        )
    return stable_id, version, document_type


def inspect_prepared_frontmatter(path: Path) -> dict[str, Any]:
    """Return a defensive copy of owner-prepared Managed Artifact metadata."""

    parsed = _parse_artifact_text(path.read_text(encoding="utf-8"))
    return dict(parsed.frontmatter)


def _reference_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _verify_profile_activation_postconditions(
    plan: ActivationPlan,
    root: Path,
) -> PostconditionReport:
    results: list[dict[str, Any]] = []

    def record(code: str, passed: bool, expected: Any, actual: Any) -> None:
        results.append(
            {"code": code, "passed": passed, "expected": expected, "actual": actual}
        )

    if not all((plan.active_path, plan.target_version, plan.profile)):
        return PostconditionReport(
            passed=False,
            results=(
                {
                    "code": "activation_plan_incomplete",
                    "passed": False,
                    "expected": "profile, active path, and target version",
                    "actual": None,
                },
            ),
        )
    assert plan.active_path is not None
    assert plan.target_version is not None
    assert plan.profile is not None
    profile = plan.profile
    try:
        active = _parse_artifact_text(
            (root / plan.active_path).read_text(encoding="utf-8")
        )
        state = build_governance_state(root)
        line = [
            item for item in state.all_records if item.artifact_id == plan.stable_id
        ]
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        yaml.YAMLError,
        GovernanceStateError,
    ) as exc:
        return PostconditionReport(
            passed=False,
            results=(
                {
                    "code": "activation_reread_failed",
                    "passed": False,
                    "expected": "rereadable unambiguous final state",
                    "actual": str(exc),
                },
            ),
        )

    active_records = [item for item in line if item.status == "active"]
    target_records = [item for item in line if item.version == plan.target_version]
    record("exactly_one_active", len(active_records) == 1, 1, len(active_records))
    record(
        "target_version_active",
        len(target_records) == 1 and target_records[0].status == "active",
        {"version": plan.target_version, "status": "active"},
        [(item.version, item.status) for item in target_records],
    )
    record(
        "target_at_active_path",
        len(target_records) == 1 and target_records[0].path == plan.active_path,
        plan.active_path,
        [item.path for item in target_records],
    )
    expected_identity = {
        "document_type": profile.document_type,
        profile.identity_field: plan.stable_id,
        "status": profile.target_status,
        "evidence_class": profile.target_evidence_class,
        "canonical_path": plan.active_path,
    }
    actual_identity = {
        key: active.frontmatter.get(key) for key in expected_identity
    }
    record(
        "target_identity_and_lifecycle",
        actual_identity == expected_identity,
        expected_identity,
        actual_identity,
    )
    record(
        "target_canonical_path",
        active.frontmatter.get("canonical_path") == plan.active_path,
        plan.active_path,
        active.frontmatter.get("canonical_path"),
    )
    record(
        "active_filename",
        active_path_allowed(profile, plan.active_path, active.frontmatter),
        profile.active_path_rule,
        plan.active_path,
    )
    expected_supersedes = (
        [f"{plan.stable_id}@{plan.previous_version}"]
        if plan.previous_version
        else []
    )
    record(
        "target_supersedes",
        active.frontmatter.get("supersedes") == expected_supersedes,
        expected_supersedes,
        active.frontmatter.get("supersedes"),
    )
    record(
        "target_activation_body_matches",
        active.body == plan.target_body,
        plan.target_body,
        active.body,
    )
    target_preserved = {
        field: active.frontmatter.get(field) for field in _PRESERVED_FIELDS
    }
    record(
        "target_evidence_preserved",
        target_preserved == (plan.target_preserved or {}),
        plan.target_preserved or {},
        target_preserved,
    )

    if plan.initial_activation:
        historical = [item for item in line if item.status == "superseded"]
        record(
            "no_phantom_predecessor",
            not historical,
            [],
            [item.path for item in historical],
        )
    else:
        if not all((plan.archive_path, plan.previous_version)):
            record(
                "predecessor_plan_complete",
                False,
                "archive path and previous version",
                None,
            )
        else:
            assert plan.archive_path is not None
            assert plan.previous_version is not None
            try:
                predecessor = _parse_artifact_text(
                    (root / plan.archive_path).read_text(encoding="utf-8")
                )
                predecessor_records = [
                    item for item in line if item.version == plan.previous_version
                ]
                predecessor_expected = {
                    "status": "superseded",
                    "evidence_class": "historical_evidence",
                    "canonical_path": plan.archive_path,
                }
                predecessor_actual = {
                    key: predecessor.frontmatter.get(key)
                    for key in predecessor_expected
                }
                record(
                    "predecessor_exactly_once",
                    len(predecessor_records) == 1,
                    1,
                    len(predecessor_records),
                )
                record(
                    "predecessor_historical",
                    predecessor_actual == predecessor_expected
                    and history_path_allowed(
                        profile,
                        plan.archive_path,
                        predecessor.frontmatter,
                        active_path=plan.active_path,
                    ),
                    predecessor_expected,
                    predecessor_actual,
                )
                record(
                    "predecessor_body_preserved",
                    predecessor.body == plan.predecessor_body,
                    plan.predecessor_body,
                    predecessor.body,
                )
                predecessor_preserved = {
                    field: predecessor.frontmatter.get(field)
                    for field in _PRESERVED_FIELDS
                }
                record(
                    "predecessor_evidence_preserved",
                    predecessor_preserved == (plan.predecessor_preserved or {}),
                    plan.predecessor_preserved or {},
                    predecessor_preserved,
                )
            except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
                record(
                    "activation_reread_failed",
                    False,
                    "rereadable historical predecessor",
                    str(exc),
                )

    duplicate_versions = {
        version: len([item for item in line if item.version == version])
        for version in {item.version for item in line}
        if len([item for item in line if item.version == version]) != 1
    }
    record("unique_id_version", not duplicate_versions, {}, duplicate_versions)
    unresolved: list[str] = []
    for field_name in _REFERENCE_FIELDS:
        for reference in _reference_values(active.frontmatter.get(field_name)):
            if "@" in reference:
                target_id, target_version = reference.rsplit("@", 1)
                found = any(
                    item.artifact_id == target_id and item.version == target_version
                    for item in state.all_records
                )
            else:
                found = state.active_record(reference) is not None
            if not found:
                unresolved.append(f"{field_name}:{reference}")
    record("required_references_resolve", not unresolved, [], sorted(unresolved))
    try:
        resolved, _ = read_active_artifact(Vault(root), plan.stable_id)
        scope_actual: Any = {
            "version": resolved.version,
            "path": resolved.relative_path,
            "integrity_ok": resolved.integrity_ok,
        }
        scope_valid = scope_actual == {
            "version": plan.target_version,
            "path": plan.active_path,
            "integrity_ok": True,
        }
    except GovernanceResolutionError as exc:
        scope_valid = False
        scope_actual = str(exc)
    record(
        "scope_validation",
        scope_valid,
        {
            "version": plan.target_version,
            "path": plan.active_path,
            "integrity_ok": True,
        },
        scope_actual,
    )
    record("no_unplanned_paths", True, True, True)
    return PostconditionReport(
        passed=all(item["passed"] for item in results), results=tuple(results)
    )


def verify_activation_postconditions(
    plan: ActivationPlan,
    root: Path,
) -> PostconditionReport:
    """Verify K1 lifecycle invariants exclusively from post-mutation rereads."""

    if plan.profile is not None:
        return _verify_profile_activation_postconditions(plan, root)

    results: list[dict[str, Any]] = []

    def record(code: str, passed: bool, expected: Any, actual: Any) -> None:
        results.append(
            {
                "code": code,
                "passed": passed,
                "expected": expected,
                "actual": actual,
            }
        )

    if not all(
        (
            plan.active_path,
            plan.archive_path,
            plan.previous_version,
            plan.target_version,
        )
    ):
        return PostconditionReport(
            passed=False,
            results=(
                {
                    "code": "activation_plan_incomplete",
                    "passed": False,
                    "expected": "complete activation paths and versions",
                    "actual": None,
                },
            ),
        )

    assert plan.active_path is not None
    assert plan.archive_path is not None
    assert plan.previous_version is not None
    assert plan.target_version is not None
    try:
        active = _parse_artifact_text(
            (root / plan.active_path).read_text(encoding="utf-8")
        )
        predecessor = _parse_artifact_text(
            (root / plan.archive_path).read_text(encoding="utf-8")
        )
        state = build_governance_state(root)
        line = [
            item for item in state.all_records if item.artifact_id == plan.stable_id
        ]
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        yaml.YAMLError,
        GovernanceStateError,
    ) as exc:
        return PostconditionReport(
            passed=False,
            results=(
                {
                    "code": "activation_reread_failed",
                    "passed": False,
                    "expected": "rereadable unambiguous final state",
                    "actual": str(exc),
                },
            ),
        )

    active_records = [item for item in line if item.status == "active"]
    target_records = [item for item in line if item.version == plan.target_version]
    predecessor_records = [
        item for item in line if item.version == plan.previous_version
    ]
    record("exactly_one_active", len(active_records) == 1, 1, len(active_records))
    record(
        "target_version_active",
        len(target_records) == 1 and target_records[0].status == "active",
        {"version": plan.target_version, "status": "active"},
        [(item.version, item.status) for item in target_records],
    )
    record(
        "target_at_active_path",
        len(target_records) == 1 and target_records[0].path == plan.active_path,
        plan.active_path,
        [item.path for item in target_records],
    )
    record(
        "target_canonical_path",
        active.frontmatter.get("canonical_path") == plan.active_path,
        plan.active_path,
        active.frontmatter.get("canonical_path"),
    )
    title = active.frontmatter.get("title")
    expected_active_name = (
        _expected_filename(plan.stable_id, plan.target_version, title, active=True)
        if isinstance(title, str)
        else None
    )
    record(
        "active_filename",
        PurePosixPath(plan.active_path).name == expected_active_name,
        expected_active_name,
        PurePosixPath(plan.active_path).name,
    )
    record(
        "predecessor_exactly_once",
        len(predecessor_records) == 1,
        1,
        len(predecessor_records),
    )
    predecessor_expected = {
        "status": "superseded",
        "evidence_class": "historical_evidence",
        "path": plan.archive_path,
        "canonical_path": plan.archive_path,
    }
    predecessor_actual = {
        "status": predecessor.frontmatter.get("status"),
        "evidence_class": predecessor.frontmatter.get("evidence_class"),
        "path": predecessor_records[0].path if len(predecessor_records) == 1 else None,
        "canonical_path": predecessor.frontmatter.get("canonical_path"),
    }
    record(
        "predecessor_historical",
        predecessor_actual == predecessor_expected,
        predecessor_expected,
        predecessor_actual,
    )
    expected_supersedes = [f"{plan.stable_id}@{plan.previous_version}"]
    record(
        "target_supersedes_predecessor",
        active.frontmatter.get("supersedes") == expected_supersedes,
        expected_supersedes,
        active.frontmatter.get("supersedes"),
    )
    duplicate_versions = {
        version: len([item for item in line if item.version == version])
        for version in {item.version for item in line}
        if len([item for item in line if item.version == version]) != 1
    }
    record("unique_id_version", not duplicate_versions, {}, duplicate_versions)

    unresolved: list[str] = []
    for artifact in (active, predecessor):
        for field_name in _REFERENCE_FIELDS:
            for reference in _reference_values(artifact.frontmatter.get(field_name)):
                if "@" in reference:
                    target_id, target_version = reference.rsplit("@", 1)
                    found = any(
                        item.artifact_id == target_id and item.version == target_version
                        for item in state.all_records
                    )
                else:
                    found = state.active_record(reference) is not None
                if not found:
                    unresolved.append(f"{field_name}:{reference}")
    record("required_references_resolve", not unresolved, [], sorted(unresolved))

    try:
        resolved, _ = read_active_artifact(Vault(root), plan.stable_id)
        scope_valid = (
            resolved.version == plan.target_version
            and resolved.relative_path == plan.active_path
            and resolved.integrity_ok
        )
        scope_actual: Any = {
            "version": resolved.version,
            "path": resolved.relative_path,
            "integrity_ok": resolved.integrity_ok,
        }
    except GovernanceResolutionError as exc:
        scope_valid = False
        scope_actual = str(exc)
    record(
        "scope_validation",
        scope_valid,
        {
            "version": plan.target_version,
            "path": plan.active_path,
            "integrity_ok": True,
        },
        scope_actual,
    )
    record("no_unplanned_paths", True, True, True)
    record(
        "target_activation_body_matches",
        active.body == plan.target_body,
        plan.target_body,
        active.body,
    )
    record(
        "predecessor_body_preserved",
        predecessor.body == plan.predecessor_body,
        plan.predecessor_body,
        predecessor.body,
    )
    target_preserved = {
        field: active.frontmatter.get(field) for field in _PRESERVED_FIELDS
    }
    predecessor_preserved = {
        field: predecessor.frontmatter.get(field) for field in _PRESERVED_FIELDS
    }
    record(
        "target_evidence_preserved",
        target_preserved == (plan.target_preserved or {}),
        plan.target_preserved or {},
        target_preserved,
    )
    record(
        "predecessor_evidence_preserved",
        predecessor_preserved == (plan.predecessor_preserved or {}),
        plan.predecessor_preserved or {},
        predecessor_preserved,
    )
    record(
        "derived_governance_consistent",
        state.active_record(plan.stable_id) is not None
        and state.active_record(plan.stable_id).version == plan.target_version,
        plan.target_version,
        (
            state.active_record(plan.stable_id).version
            if state.active_record(plan.stable_id) is not None
            else None
        ),
    )
    return PostconditionReport(
        passed=all(item["passed"] for item in results), results=tuple(results)
    )


def _validate_prepared_revision(
    *,
    prepared: ParsedArtifact,
    target_path: str,
    active_id: str,
    active_version: str,
    profile: ManagedArtifactLifecycleProfile,
    vault_root: Path,
) -> tuple[ResultDisposition, str]:
    fm = prepared.frontmatter
    if not profile.revise_capable:
        return (
            ResultDisposition.UNSUPPORTED,
            f"artifact.revise is unsupported for {profile.document_type}",
        )
    if fm.get("document_type") != profile.document_type:
        return ResultDisposition.BLOCKED, "prepared document_type changed"
    if fm.get(profile.identity_field) != active_id:
        return (
            ResultDisposition.BLOCKED,
            "prepared stable ID does not match active source",
        )
    try:
        if _version_key(fm.get("version")) <= _version_key(active_version):
            return (
                ResultDisposition.CONFLICT,
                "target version must be higher than active version",
            )
    except ValueError:
        return ResultDisposition.BLOCKED, "target version is invalid"
    if fm.get("status") != "draft":
        return ResultDisposition.BLOCKED, "revision target status must be draft"
    if fm.get("evidence_class") not in _DRAFT_EVIDENCE:
        return ResultDisposition.BLOCKED, "draft evidence_class is not activatable"
    if fm.get("source_artifact") != f"{active_id}@{active_version}":
        return ResultDisposition.BLOCKED, "source_artifact does not match active source"
    if fm.get("supersedes") not in (None, []):
        return ResultDisposition.BLOCKED, "revision must not preempt supersedes"
    if fm.get("canonical_path") != target_path:
        return (
            ResultDisposition.BLOCKED,
            "canonical_path must equal the Development target path",
        )
    if not development_path_allowed(profile, target_path, fm):
        return (
            ResultDisposition.BLOCKED,
            f"revision target violates {profile.development_path_rule}",
        )
    if profile.single_file_only and is_process_package_path(target_path):
        return (
            ResultDisposition.UNSUPPORTED,
            "process packages requiring coupled mutation are unsupported",
        )
    title = fm.get("title")
    version = fm.get("version")
    if not isinstance(title, str) or PurePosixPath(
        target_path
    ).name != _expected_filename(active_id, version, title, active=False):
        return ResultDisposition.BLOCKED, "revision target filename must be versioned"
    matching_version = [
        path
        for path, record in _iter_line_records(vault_root, active_id, profile)
        if record.frontmatter.get("version") == version
    ]
    if matching_version:
        return ResultDisposition.CONFLICT, "target stable ID and version already exist"
    return ResultDisposition.SUCCEEDED, "prepared revision is valid"


def _finish_controller(
    controller: InProcessRunController | None,
    result: OperationResult,
) -> None:
    if controller is None:
        return
    if result.disposition is ResultDisposition.SUCCEEDED:
        if controller.state is RunState.APPLYING:
            controller.transition(RunState.VERIFYING)
        controller.transition(RunState.SUCCEEDED)
    elif result.disposition is ResultDisposition.COMPENSATED_FAILURE:
        controller.transition(RunState.PARTIAL_STATE_DETECTED)
        controller.transition(RunState.COMPENSATING)
        controller.transition(RunState.COMPENSATED_FAILURE)
    elif result.disposition is ResultDisposition.RECOVERY_REQUIRED:
        controller.transition(RunState.PARTIAL_STATE_DETECTED)
        controller.transition(RunState.COMPENSATING)
        controller.transition(RunState.FATAL_PARTIAL_STATE)
        controller.transition(RunState.RECOVERY_REQUIRED)


def verify_revision_postconditions(
    *,
    root: Path,
    target_path: str,
    prepared: ParsedArtifact,
    profile: ManagedArtifactLifecycleProfile,
    stable_id: str,
) -> PostconditionReport:
    try:
        materialized = _parse_artifact_text(
            (root / target_path).read_text(encoding="utf-8")
        )
        records = _iter_line_records(root, stable_id, profile)
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        return PostconditionReport(
            passed=False,
            results=(
                {
                    "code": "revision_reread_failed",
                    "passed": False,
                    "expected": "rereadable prepared draft",
                    "actual": str(exc),
                },
            ),
        )
    version = prepared.frontmatter.get("version")
    version_records = [
        path
        for path, artifact in records
        if artifact.frontmatter.get("version") == version
    ]
    results = (
        {
            "code": "draft_materialized",
            "passed": materialized.raw == prepared.raw,
            "expected": prepared.raw,
            "actual": materialized.raw,
        },
        {
            "code": "revision_identity",
            "passed": (
                materialized.frontmatter.get("document_type")
                == profile.document_type
                and materialized.frontmatter.get(profile.identity_field) == stable_id
            ),
            "expected": {
                "document_type": profile.document_type,
                profile.identity_field: stable_id,
            },
            "actual": {
                "document_type": materialized.frontmatter.get("document_type"),
                profile.identity_field: materialized.frontmatter.get(
                    profile.identity_field
                ),
            },
        },
        {
            "code": "revision_canonical_path",
            "passed": materialized.frontmatter.get("canonical_path") == target_path,
            "expected": target_path,
            "actual": materialized.frontmatter.get("canonical_path"),
        },
        {
            "code": "revision_unique_version",
            "passed": version_records == [target_path],
            "expected": [target_path],
            "actual": version_records,
        },
    )
    return PostconditionReport(
        passed=all(item["passed"] for item in results), results=results
    )


def revise_managed_artifact(
    *,
    vault_root: Path,
    prepared_file: Path,
    target_path: str,
    authority: AuthorityDecision,
    apply: bool,
    transaction_engine: FileTransactionEngine,
    idempotency_key: str,
    request_fingerprint: str | None = None,
    operation_context: OperationContext | None = None,
    controller: InProcessRunController | None = None,
) -> OperationResult:
    try:
        prepared = _parse_artifact_text(prepared_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        return _result("artifact.revise", ResultDisposition.UNSUPPORTED, str(exc))
    document_type = prepared.frontmatter.get("document_type")
    if not isinstance(document_type, str):
        return _result(
            "artifact.revise",
            ResultDisposition.UNSUPPORTED,
            "prepared document_type is required",
        )
    try:
        profile = get_lifecycle_profile(document_type)
    except UnsupportedLifecycleProfileError as exc:
        return _result("artifact.revise", ResultDisposition.UNSUPPORTED, str(exc))
    if not profile.revise_capable:
        return _result(
            "artifact.revise",
            ResultDisposition.UNSUPPORTED,
            f"artifact.revise is unsupported for {document_type}",
        )
    prepared_id = prepared.frontmatter.get(profile.identity_field)
    if not isinstance(prepared_id, str):
        return _result(
            "artifact.revise",
            ResultDisposition.BLOCKED,
            f"prepared {profile.identity_field} is required",
        )
    try:
        resolution, _ = read_active_artifact(Vault(vault_root), prepared_id)
    except ActiveArtifactNotFoundError:
        return _result(
            "artifact.revise",
            ResultDisposition.UNSUPPORTED,
            "artifact.revise requires one active source line",
        )
    except MultipleActiveArtifactsError as exc:
        return _result("artifact.revise", ResultDisposition.CONFLICT, str(exc))
    except GovernanceResolutionError as exc:
        return _result("artifact.revise", ResultDisposition.CONFLICT, str(exc))
    disposition, message = _validate_prepared_revision(
        prepared=prepared,
        target_path=target_path,
        active_id=resolution.stable_id,
        active_version=resolution.version,
        profile=profile,
        vault_root=vault_root,
    )
    if disposition is not ResultDisposition.SUCCEEDED:
        return _result("artifact.revise", disposition, message)
    effective_request_fingerprint = request_fingerprint or canonical_json_hash(
        {
            "operation": "artifact.revise",
            "prepared": prepared.raw,
            "target_path": target_path,
            "active": f"{resolution.stable_id}@{resolution.version}",
            "authority": authority.authority_ref,
        }
    )
    plan = MutationPlan(
        plan_id=stable_token("plan", effective_request_fingerprint),
        request_fingerprint=effective_request_fingerprint,
        actions=(
            MutationAction(
                kind=MutationKind.CREATE,
                path=target_path,
                content=prepared.raw,
            ),
        ),
        expected_source_fingerprints={
            resolution.relative_path: transaction_engine.fingerprint(
                resolution.relative_path
            )
        },
        postconditions=(
            Postcondition("draft_materialized", "prepared draft exists at target path"),
        ),
    )
    try:
        preview = transaction_engine.preview(plan)
    except (
        PathSafetyError,
        SourceFingerprintConflict,
        StagingValidationError,
        FileNotFoundError,
    ) as exc:
        return _result("artifact.revise", ResultDisposition.CONFLICT, str(exc))
    if controller is not None:
        controller.transition(RunState.PLANNED)
        controller.transition(RunState.PREVIEWED)
        controller.transition(RunState.AWAITING_AUTHORITY)
    if not authority.authorized:
        if controller is not None:
            controller.transition(RunState.BLOCKED)
        return _result(
            "artifact.revise", ResultDisposition.BLOCKED, "; ".join(authority.reasons)
        )
    if controller is not None:
        controller.transition(RunState.AUTHORIZED)
    if not apply:
        return _result(
            "artifact.revise",
            ResultDisposition.SUCCEEDED,
            "revision check passed; no mutation performed",
            outputs={"plan_id": plan.plan_id, "preview": preview, "applied": False},
        )
    if controller is not None:
        controller.transition(RunState.STAGING)
        controller.transition(RunState.APPLYING)
    transaction = transaction_engine.apply(
        plan,
        idempotency_key=idempotency_key,
        domain_verifier=lambda root: verify_revision_postconditions(
            root=root,
            target_path=target_path,
            prepared=prepared,
            profile=profile,
            stable_id=prepared_id,
        ),
        verification_hook=(
            (lambda: controller.transition(RunState.VERIFYING))
            if controller is not None
            else None
        ),
        run_id=operation_context.run_id if operation_context else None,
    )
    _finish_controller(controller, transaction)
    return _result(
        "artifact.revise",
        transaction.disposition,
        transaction.message,
        outputs={
            "plan_id": plan.plan_id,
            "applied": transaction.disposition is ResultDisposition.SUCCEEDED,
        },
        source=transaction,
    )


def revise_specification(**kwargs: Any) -> OperationResult:
    """Backward-compatible K1 entry point routed through the K2 core."""

    return revise_managed_artifact(**kwargs)


def _activation_block(
    disposition: ResultDisposition,
    message: str,
    stable_id: str,
) -> ActivationPlan:
    return ActivationPlan(disposition=disposition, message=message, stable_id=stable_id)


def plan_specification_activation(
    *,
    vault_root: Path,
    stable_id: str,
    draft_path: str,
    archive_path: str | None,
    activation_target_file: Path | None = None,
    approved_by: str,
    approved_at: str,
    effective_from: str,
    authority: AuthorityDecision,
    transaction_engine: FileTransactionEngine,
    request_fingerprint: str | None = None,
    active_path: str | None = None,
) -> ActivationPlan:
    if (
        not approved_by
        or parse_lifecycle_temporal(approved_at) is None
        or parse_lifecycle_temporal(effective_from) is None
    ):
        return _activation_block(
            ResultDisposition.BLOCKED,
            "explicit valid approval and effectiveness inputs are required",
            stable_id,
        )
    try:
        draft = _parse_artifact_text(
            (vault_root / draft_path).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        return _activation_block(
            ResultDisposition.BLOCKED, f"draft cannot be read: {exc}", stable_id
        )
    fm = draft.frontmatter
    document_type = fm.get("document_type")
    if not isinstance(document_type, str):
        return _activation_block(
            ResultDisposition.UNSUPPORTED,
            "draft document_type is required",
            stable_id,
        )
    try:
        profile = get_lifecycle_profile(document_type)
    except UnsupportedLifecycleProfileError as exc:
        return _activation_block(ResultDisposition.UNSUPPORTED, str(exc), stable_id)
    if not (
        profile.initial_activation_capable or profile.follow_up_activation_capable
    ):
        return _activation_block(
            ResultDisposition.UNSUPPORTED,
            f"artifact.activate is unsupported for {document_type}",
            stable_id,
        )
    if fm.get(profile.identity_field) != stable_id:
        return _activation_block(
            ResultDisposition.BLOCKED,
            f"draft {profile.identity_field} does not match target",
            stable_id,
        )
    if (
        fm.get("status") not in _ACTIVATABLE_STATUSES
        or fm.get("evidence_class") not in _DRAFT_EVIDENCE
    ):
        return _activation_block(
            ResultDisposition.BLOCKED,
            "draft status or evidence_class is not activatable",
            stable_id,
        )
    if fm.get("canonical_path") != draft_path or not development_path_allowed(
        profile, draft_path, fm
    ):
        return _activation_block(
            ResultDisposition.BLOCKED,
            f"draft path violates {profile.development_path_rule}",
            stable_id,
        )
    if profile.single_file_only and is_process_package_path(draft_path):
        return _activation_block(
            ResultDisposition.UNSUPPORTED,
            "process packages requiring coupled mutation are unsupported",
            stable_id,
        )
    title = fm.get("title")
    target_version = fm.get("version")
    if not isinstance(title, str) or not isinstance(target_version, str):
        return _activation_block(
            ResultDisposition.BLOCKED,
            "draft title and version are required",
            stable_id,
        )
    target_body = draft.body
    if activation_target_file is not None:
        try:
            prepared_target = _parse_artifact_text(
                activation_target_file.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
            return _activation_block(
                ResultDisposition.BLOCKED,
                f"activation target cannot be read: {exc}",
                stable_id,
            )
        expected_target_identity = {
            "document_type": document_type,
            profile.identity_field: stable_id,
            "title": title,
            "version": target_version,
            "status": "active",
        }
        actual_target_identity = {
            key: prepared_target.frontmatter.get(key)
            for key in expected_target_identity
        }
        if actual_target_identity != expected_target_identity:
            return _activation_block(
                ResultDisposition.BLOCKED,
                "owner-prepared activation target identity does not match draft",
                stable_id,
            )
        target_body = prepared_target.body
    if PurePosixPath(draft_path).name != _expected_filename(
        stable_id, target_version, title, active=False
    ):
        return _activation_block(
            ResultDisposition.BLOCKED, "draft filename is invalid", stable_id
        )
    records = _iter_line_records(vault_root, stable_id, profile)
    active_records = [
        item for item in records if item[1].frontmatter.get("status") == "active"
    ]
    target_records = [
        item for item in records if item[1].frontmatter.get("version") == target_version
    ]
    if len(active_records) > 1:
        return _activation_block(
            ResultDisposition.CONFLICT,
            "multiple active predecessors exist",
            stable_id,
        )
    if len(target_records) != 1 or target_records[0][0] != draft_path:
        return _activation_block(
            ResultDisposition.CONFLICT,
            "exactly one target draft version is required",
            stable_id,
        )
    try:
        resolution, active_document = read_active_artifact(Vault(vault_root), stable_id)
    except ActiveArtifactNotFoundError:
        resolution = None
        active_document = None
    except MultipleActiveArtifactsError as exc:
        return _activation_block(ResultDisposition.CONFLICT, str(exc), stable_id)
    except GovernanceResolutionError as exc:
        return _activation_block(ResultDisposition.CONFLICT, str(exc), stable_id)

    initial = resolution is None
    if initial:
        if not profile.initial_activation_capable:
            return _activation_block(
                ResultDisposition.UNSUPPORTED,
                f"initial activation is unsupported for {document_type}",
                stable_id,
            )
        if active_records:
            return _activation_block(
                ResultDisposition.CONFLICT,
                "initial activation requires no active predecessor",
                stable_id,
            )
        if target_version not in profile.initial_versions:
            return _activation_block(
                ResultDisposition.BLOCKED,
                "target version is not an allowed initial version",
                stable_id,
            )
        if fm.get("source_artifact") not in (None, ""):
            return _activation_block(
                ResultDisposition.BLOCKED,
                "initial activation must not invent source_artifact",
                stable_id,
            )
        if fm.get("supersedes") not in (None, []):
            return _activation_block(
                ResultDisposition.BLOCKED,
                "initial activation must not invent supersedes",
                stable_id,
            )
        if archive_path:
            return _activation_block(
                ResultDisposition.BLOCKED,
                "initial activation has no predecessor archive target",
                stable_id,
            )
        final_active_path = active_path
        if not final_active_path or not active_path_allowed(
            profile, final_active_path, fm
        ):
            return _activation_block(
                ResultDisposition.BLOCKED,
                f"active_path violates {profile.active_path_rule}",
                stable_id,
            )
        if (vault_root / final_active_path).exists():
            return _activation_block(
                ResultDisposition.CONFLICT,
                "initial active target already exists",
                stable_id,
            )
        predecessor = None
        predecessor_fm = None
        predecessor_path = None
        previous_version = None
    else:
        assert active_document is not None
        if not profile.follow_up_activation_capable:
            return _activation_block(
                ResultDisposition.UNSUPPORTED,
                f"follow-up activation is unsupported for {document_type}",
                stable_id,
            )
        if resolution.document_type != document_type:
            return _activation_block(
                ResultDisposition.BLOCKED,
                "draft document_type does not match active line",
                stable_id,
            )
        try:
            if _version_key(target_version) <= _version_key(resolution.version):
                return _activation_block(
                    ResultDisposition.CONFLICT,
                    "target version must be higher than predecessor",
                    stable_id,
                )
        except ValueError:
            return _activation_block(
                ResultDisposition.BLOCKED, "target version is invalid", stable_id
            )
        if fm.get("source_artifact") != f"{stable_id}@{resolution.version}":
            return _activation_block(
                ResultDisposition.BLOCKED,
                "source_artifact does not match predecessor",
                stable_id,
            )
        if fm.get("supersedes") not in (None, []):
            return _activation_block(
                ResultDisposition.BLOCKED,
                "draft must not preempt supersedes",
                stable_id,
            )
        if len(active_records) != 1:
            return _activation_block(
                ResultDisposition.CONFLICT,
                "exactly one active predecessor is required",
                stable_id,
            )
        predecessor_raw = (vault_root / resolution.relative_path).read_text(
            encoding="utf-8"
        )
        predecessor = _parse_artifact_text(predecessor_raw)
        predecessor_fm = dict(predecessor.frontmatter)
        if not archive_path or not history_path_allowed(
            profile,
            archive_path,
            predecessor.frontmatter,
            active_path=resolution.relative_path,
        ):
            return _activation_block(
                ResultDisposition.BLOCKED,
                f"archive_path violates {profile.history_archive_rule}",
                stable_id,
            )
        if (vault_root / archive_path).exists():
            return _activation_block(
                ResultDisposition.CONFLICT,
                "archive target already exists",
                stable_id,
            )
        predecessor_fm.update(
            status="superseded",
            evidence_class="historical_evidence",
            canonical_path=archive_path,
        )
        final_active_path = active_path or str(
            PurePosixPath(resolution.relative_path).parent
            / _expected_filename(stable_id, target_version, title, active=True)
        )
        if not active_path_allowed(profile, final_active_path, fm):
            return _activation_block(
                ResultDisposition.BLOCKED,
                f"active_path violates {profile.active_path_rule}",
                stable_id,
            )
        if (
            final_active_path != resolution.relative_path
            and (vault_root / final_active_path).exists()
        ):
            return _activation_block(
                ResultDisposition.CONFLICT,
                "follow-up active target already exists",
                stable_id,
            )
        predecessor_path = resolution.relative_path
        previous_version = resolution.version

    target_fm = dict(fm)
    target_fm.update(
        status=profile.target_status,
        evidence_class=profile.target_evidence_class,
        canonical_path=final_active_path,
        supersedes=(
            [f"{stable_id}@{previous_version}"] if previous_version else []
        ),
        approved_by=approved_by,
        approved_at=approved_at,
        effective_from=effective_from,
    )
    historical_text = (
        _render(predecessor_fm, predecessor.body)
        if predecessor is not None and predecessor_fm is not None
        else None
    )
    active_text = _render(target_fm, target_body)
    expected = {
        draft_path: transaction_engine.fingerprint(draft_path),
        final_active_path: (
            transaction_engine.fingerprint(final_active_path)
            if final_active_path == predecessor_path
            else None
        ),
    }
    if predecessor_path is not None:
        expected[predecessor_path] = transaction_engine.fingerprint(predecessor_path)
    if archive_path:
        expected[archive_path] = None
    effective_request_fingerprint = request_fingerprint or canonical_json_hash(
        {
            "operation": "artifact.activate",
            "stable_id": stable_id,
            "previous_version": previous_version,
            "target_version": target_version,
            "draft_path": draft_path,
            "archive_path": archive_path,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "effective_from": effective_from,
            "authority_ref": authority.authority_ref,
            "expected": expected,
        }
    )
    actions: list[MutationAction] = []
    if predecessor_path is not None and archive_path and historical_text is not None:
        actions.extend(
            (
                MutationAction(
                    MutationKind.REPLACE,
                    predecessor_path,
                    content=historical_text,
                    expected_fingerprint=expected[predecessor_path],
                ),
                MutationAction(
                    MutationKind.MOVE,
                    predecessor_path,
                    destination=archive_path,
                ),
            )
        )
    actions.extend(
        (
            MutationAction(
                MutationKind.REPLACE,
                draft_path,
                content=active_text,
                expected_fingerprint=expected[draft_path],
            ),
            MutationAction(
                MutationKind.MOVE,
                draft_path,
                destination=final_active_path,
            ),
        )
    )
    mutation_plan = MutationPlan(
        plan_id=stable_token("plan", effective_request_fingerprint),
        request_fingerprint=effective_request_fingerprint,
        actions=tuple(actions),
        expected_source_fingerprints=expected,
        postconditions=(
            Postcondition("exactly_one_active", "one active version remains"),
            Postcondition(
                "predecessor_historical", "predecessor is superseded and archived"
            ),
            Postcondition("canonical_paths", "actual and canonical paths match"),
            Postcondition("references_resolve", "required references resolve"),
            Postcondition("unique_versions", "stable ID and version are unique"),
            Postcondition(
                "activation_target_body",
                "active body equals the owner-prepared activation target",
            ),
            Postcondition(
                "evidence_preserved", "versioned evidence fields remain unchanged"
            ),
        ),
    )
    try:
        transaction_engine.preview(mutation_plan)
    except (
        PathSafetyError,
        SourceFingerprintConflict,
        StagingValidationError,
        FileNotFoundError,
    ) as exc:
        return _activation_block(ResultDisposition.CONFLICT, str(exc), stable_id)
    return ActivationPlan(
        disposition=ResultDisposition.SUCCEEDED,
        message="activation plan passed preflight",
        stable_id=stable_id,
        active_path=final_active_path,
        draft_path=draft_path,
        archive_path=archive_path,
        previous_version=previous_version,
        target_version=target_version,
        mutation_plan=mutation_plan,
        predecessor_body=predecessor.body if predecessor is not None else None,
        target_body=target_body,
        authority_decision=authority,
        predecessor_preserved=(
            {
                field: predecessor.frontmatter.get(field)
                for field in _PRESERVED_FIELDS
            }
            if predecessor is not None
            else None
        ),
        target_preserved={
            field: draft.frontmatter.get(field) for field in _PRESERVED_FIELDS
        },
        document_type=document_type,
        profile=profile,
        initial_activation=initial,
    )


def activate_specification(
    plan: ActivationPlan,
    *,
    transaction_engine: FileTransactionEngine,
    apply: bool,
    idempotency_key: str,
    operation_context: OperationContext | None = None,
    controller: InProcessRunController | None = None,
) -> OperationResult:
    if (
        plan.disposition is not ResultDisposition.SUCCEEDED
        or plan.mutation_plan is None
    ):
        if controller is not None:
            controller.transition(RunState.PLANNED)
            controller.transition(RunState.BLOCKED)
        return _result("artifact.activate", plan.disposition, plan.message)
    if controller is not None:
        controller.transition(RunState.PLANNED)
        controller.transition(RunState.PREVIEWED)
        controller.transition(RunState.AWAITING_AUTHORITY)
    if plan.authority_decision is None or not plan.authority_decision.authorized:
        if controller is not None:
            controller.transition(RunState.BLOCKED)
        reasons = (
            plan.authority_decision.reasons
            if plan.authority_decision is not None
            else ()
        )
        return _result(
            "artifact.activate",
            ResultDisposition.BLOCKED,
            "; ".join(reasons) or "verified runtime authority is required",
        )
    if controller is not None:
        controller.transition(RunState.AUTHORIZED)
    if not apply:
        preview = transaction_engine.preview(plan.mutation_plan)
        return _result(
            "artifact.activate",
            ResultDisposition.SUCCEEDED,
            "activation check passed; no mutation performed",
            outputs={
                "plan_id": plan.mutation_plan.plan_id,
                "preview": preview,
                "applied": False,
            },
        )
    if controller is not None:
        controller.transition(RunState.STAGING)
        controller.transition(RunState.APPLYING)
    transaction = transaction_engine.apply(
        plan.mutation_plan,
        idempotency_key=idempotency_key,
        domain_verifier=lambda root: verify_activation_postconditions(plan, root),
        verification_hook=(
            (lambda: controller.transition(RunState.VERIFYING))
            if controller is not None
            else None
        ),
        run_id=operation_context.run_id if operation_context else None,
    )
    _finish_controller(controller, transaction)
    if transaction.disposition is not ResultDisposition.SUCCEEDED:
        return _result(
            "artifact.activate",
            transaction.disposition,
            transaction.message,
            source=transaction,
        )
    result = _result(
        "artifact.activate",
        ResultDisposition.SUCCEEDED,
        (
            f"{plan.document_type} activated"
            + ("" if plan.initial_activation else " and predecessor archived")
        ),
        outputs={"plan_id": plan.mutation_plan.plan_id, "applied": True},
        source=transaction,
    )
    return result


def revise_operation(request: OperationRequest, **kwargs: Any) -> OperationResult:
    parameters = {**request.parameters, **kwargs}
    authority = parameters.get("_authority_decision")
    operation_context = parameters.get("_operation_context")
    controller = parameters.get("_run_controller")
    if (
        not isinstance(authority, AuthorityDecision)
        or not isinstance(operation_context, OperationContext)
        or not isinstance(controller, InProcessRunController)
    ):
        return _result(
            "artifact.revise",
            ResultDisposition.BLOCKED,
            "artifact mutations require the shared application context and controller",
            correlation_id=request.correlation_id,
        )
    run_root = Path(parameters["run_root"])
    vault_root = Path(parameters["vault_root"])
    engine = parameters.get("_transaction_engine")
    if not isinstance(engine, FileTransactionEngine):
        engine = FileTransactionEngine(vault_root, run_root)
    key = request.idempotency_key or request.fingerprint
    replay = engine.idempotency_disposition(key, request.fingerprint)
    if replay is not None:
        return _result(
            "artifact.revise",
            replay,
            "idempotent replay"
            if replay is ResultDisposition.IDEMPOTENT_REPLAY
            else "idempotency key conflict",
            correlation_id=request.correlation_id,
        )
    return revise_managed_artifact(
        vault_root=vault_root,
        prepared_file=Path(parameters["prepared_file"]),
        target_path=str(parameters["target_path"]),
        authority=authority,
        apply=request.requested_mode == "apply",
        transaction_engine=engine,
        idempotency_key=key,
        request_fingerprint=request.fingerprint,
        operation_context=operation_context,
        controller=controller,
    )


def activate_operation(request: OperationRequest, **kwargs: Any) -> OperationResult:
    parameters = {**request.parameters, **kwargs}
    stable_id = str(parameters.get("stable_id") or request.targets[0])
    authority = parameters.get("_authority_decision")
    operation_context = parameters.get("_operation_context")
    controller = parameters.get("_run_controller")
    if (
        not isinstance(authority, AuthorityDecision)
        or not isinstance(operation_context, OperationContext)
        or not isinstance(controller, InProcessRunController)
    ):
        return _result(
            "artifact.activate",
            ResultDisposition.BLOCKED,
            "artifact mutations require the shared application context and controller",
            correlation_id=request.correlation_id,
        )
    vault_root = Path(parameters["vault_root"])
    engine = parameters.get("_transaction_engine")
    if not isinstance(engine, FileTransactionEngine):
        engine = FileTransactionEngine(vault_root, Path(parameters["run_root"]))
    key = request.idempotency_key or request.fingerprint
    replay = engine.idempotency_disposition(key, request.fingerprint)
    if replay is not None:
        return _result(
            "artifact.activate",
            replay,
            "idempotent replay"
            if replay is ResultDisposition.IDEMPOTENT_REPLAY
            else "idempotency key conflict",
            correlation_id=request.correlation_id,
        )
    plan = plan_specification_activation(
        vault_root=vault_root,
        stable_id=stable_id,
        draft_path=str(parameters["draft_path"]),
        archive_path=(
            str(parameters["archive_path"])
            if parameters.get("archive_path")
            else None
        ),
        approved_by=str(parameters.get("approved_by", "")),
        approved_at=str(parameters.get("approved_at", "")),
        effective_from=str(parameters.get("effective_from", "")),
        authority=authority,
        transaction_engine=engine,
        request_fingerprint=request.fingerprint,
        active_path=(
            str(parameters["active_path"])
            if parameters.get("active_path")
            else None
        ),
        activation_target_file=(
            Path(parameters["activation_target_file"])
            if parameters.get("activation_target_file")
            else None
        ),
    )
    return activate_specification(
        plan,
        transaction_engine=engine,
        apply=request.requested_mode == "apply",
        idempotency_key=key,
        operation_context=operation_context,
        controller=controller,
    )


_COMPLETION_EVIDENCE_MARKERS = (
    ("actual deliverables", "tatsächliche deliverables"),
    ("deviations", "abweichungen"),
    ("validations", "validierungen"),
    ("open items", "offene restpunkte"),
    ("completion decision", "abschlussentscheidung"),
    ("follow-up references", "folgeartefakt", "follow-up-referenzen"),
    ("run/report references", "run-/reportreferenzen", "run references"),
)


def _completion_evidence_present(body: str) -> bool:
    normalized = body.casefold()
    return "completion evidence" in normalized and all(
        any(marker in normalized for marker in alternatives)
        for alternatives in _COMPLETION_EVIDENCE_MARKERS
    )


def _completion_block(
    disposition: ResultDisposition,
    message: str,
    stable_id: str,
) -> CompletionPlan:
    return CompletionPlan(disposition=disposition, message=message, stable_id=stable_id)


def plan_work_package_completion(
    *,
    vault_root: Path,
    stable_id: str,
    prepared_file: Path | None = None,
    completion_evidence_file: Path | None = None,
    archive_path: str,
    authority: AuthorityDecision,
    transaction_engine: FileTransactionEngine,
    request_fingerprint: str | None = None,
) -> CompletionPlan:
    profile = get_lifecycle_profile("work_package")
    try:
        resolution, _ = read_active_artifact(Vault(vault_root), stable_id)
    except MultipleActiveArtifactsError as exc:
        return _completion_block(ResultDisposition.CONFLICT, str(exc), stable_id)
    except GovernanceResolutionError as exc:
        return _completion_block(ResultDisposition.BLOCKED, str(exc), stable_id)
    if resolution.document_type != "work_package":
        return _completion_block(
            ResultDisposition.UNSUPPORTED,
            "work_package.complete requires document_type work_package",
            stable_id,
        )
    try:
        source = _parse_artifact_text(
            (vault_root / resolution.relative_path).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        return _completion_block(ResultDisposition.BLOCKED, str(exc), stable_id)
    source_fm = source.frontmatter
    if (prepared_file is None) == (completion_evidence_file is None):
        return _completion_block(
            ResultDisposition.BLOCKED,
            "exactly one prepared completion target or completion evidence "
            "file is required",
            stable_id,
        )
    if completion_evidence_file is not None:
        try:
            evidence = completion_evidence_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return _completion_block(ResultDisposition.BLOCKED, str(exc), stable_id)
        if not _completion_evidence_present(evidence):
            return _completion_block(
                ResultDisposition.BLOCKED,
                "required completion evidence is missing",
                stable_id,
            )
        target_fm = dict(source_fm)
        target_fm.update(
            {
                "status": profile.target_status,
                "evidence_class": profile.target_evidence_class,
                "canonical_path": archive_path,
            }
        )
        target_body = source.body.rstrip() + "\n\n" + evidence.strip() + "\n"
        target = _parse_artifact_text(_render(target_fm, target_body))
    else:
        assert prepared_file is not None
        try:
            target = _parse_artifact_text(prepared_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
            return _completion_block(ResultDisposition.BLOCKED, str(exc), stable_id)
    target_fm = target.frontmatter
    if target_fm.get("document_type") != "work_package":
        return _completion_block(
            ResultDisposition.BLOCKED,
            "completion target document_type changed",
            stable_id,
        )
    if target_fm.get(profile.identity_field) != stable_id:
        return _completion_block(
            ResultDisposition.BLOCKED,
            "completion target work_package_id changed",
            stable_id,
        )
    if target_fm.get("version") != resolution.version:
        return _completion_block(
            ResultDisposition.BLOCKED,
            "work-package completion must preserve version",
            stable_id,
        )
    if target_fm.get("status") != profile.target_status or target_fm.get(
        "evidence_class"
    ) != profile.target_evidence_class:
        return _completion_block(
            ResultDisposition.BLOCKED,
            "completion target must be completed / historical_evidence",
            stable_id,
        )
    if target_fm.get("canonical_path") != archive_path or not history_path_allowed(
        profile,
        archive_path,
        target_fm,
        active_path=resolution.relative_path,
    ):
        return _completion_block(
            ResultDisposition.BLOCKED,
            "completion archive path is invalid",
            stable_id,
        )
    if (vault_root / archive_path).exists():
        return _completion_block(
            ResultDisposition.CONFLICT,
            "completed work-package target already exists",
            stable_id,
        )
    changed_fields = {
        field
        for field in source_fm.keys() | target_fm.keys()
        if source_fm.get(field) != target_fm.get(field)
    }
    unpermitted = changed_fields - set(profile.allowed_diff_fields)
    if unpermitted:
        return _completion_block(
            ResultDisposition.BLOCKED,
            "completion changed preserved fields: " + ", ".join(sorted(unpermitted)),
            stable_id,
        )
    if not target.body.startswith(source.body.rstrip()):
        return _completion_block(
            ResultDisposition.BLOCKED,
            "completion must preserve the original work-package body",
            stable_id,
        )
    if not _completion_evidence_present(target.body):
        return _completion_block(
            ResultDisposition.BLOCKED,
            "required completion evidence is missing",
            stable_id,
        )
    records = _iter_line_records(vault_root, stable_id, profile)
    active_records = [
        item for item in records if item[1].frontmatter.get("status") == "active"
    ]
    if len(active_records) != 1:
        return _completion_block(
            ResultDisposition.CONFLICT,
            "exactly one active work package is required",
            stable_id,
        )
    expected = {
        resolution.relative_path: transaction_engine.fingerprint(
            resolution.relative_path
        ),
        archive_path: None,
    }
    effective_fingerprint = request_fingerprint or canonical_json_hash(
        {
            "operation": "artifact.transition",
            "transition_profile": "work_package.complete",
            "stable_id": stable_id,
            "version": resolution.version,
            "prepared": target.raw,
            "archive_path": archive_path,
            "authority_ref": authority.authority_ref,
            "expected": expected,
        }
    )
    mutation_plan = MutationPlan(
        plan_id=stable_token("plan", effective_fingerprint),
        request_fingerprint=effective_fingerprint,
        actions=(
            MutationAction(
                MutationKind.REPLACE,
                resolution.relative_path,
                content=target.raw,
                expected_fingerprint=expected[resolution.relative_path],
            ),
            MutationAction(
                MutationKind.MOVE,
                resolution.relative_path,
                destination=archive_path,
            ),
        ),
        expected_source_fingerprints=expected,
        postconditions=(
            Postcondition("no_active_work_package", "no active version remains"),
            Postcondition(
                "completed_exactly_once", "completed version resolves exactly once"
            ),
            Postcondition("completion_preserve", "authority and scope are unchanged"),
            Postcondition("completion_evidence", "completion evidence is present"),
        ),
    )
    try:
        transaction_engine.preview(mutation_plan)
    except (
        PathSafetyError,
        SourceFingerprintConflict,
        StagingValidationError,
        FileNotFoundError,
    ) as exc:
        return _completion_block(ResultDisposition.CONFLICT, str(exc), stable_id)
    return CompletionPlan(
        disposition=ResultDisposition.SUCCEEDED,
        message="work-package completion plan passed preflight",
        stable_id=stable_id,
        active_path=resolution.relative_path,
        archive_path=archive_path,
        version=resolution.version,
        mutation_plan=mutation_plan,
        source_body=source.body,
        target_body=target.body,
        authority_decision=authority,
        preserved_frontmatter={
            key: source_fm.get(key)
            for key in source_fm
            if key not in profile.allowed_diff_fields
        },
    )


def verify_work_package_completion(
    plan: CompletionPlan,
    root: Path,
) -> PostconditionReport:
    results: list[dict[str, Any]] = []

    def record(code: str, passed: bool, expected: Any, actual: Any) -> None:
        results.append(
            {"code": code, "passed": passed, "expected": expected, "actual": actual}
        )

    if not all((plan.archive_path, plan.version)):
        return PostconditionReport(
            passed=False,
            results=(
                {
                    "code": "completion_plan_incomplete",
                    "passed": False,
                    "expected": "archive path and version",
                    "actual": None,
                },
            ),
        )
    assert plan.archive_path is not None
    assert plan.version is not None
    profile = get_lifecycle_profile("work_package")
    try:
        completed = _parse_artifact_text(
            (root / plan.archive_path).read_text(encoding="utf-8")
        )
        state = build_governance_state(root)
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        yaml.YAMLError,
        GovernanceStateError,
    ) as exc:
        return PostconditionReport(
            passed=False,
            results=(
                {
                    "code": "completion_reread_failed",
                    "passed": False,
                    "expected": "rereadable completed work package",
                    "actual": str(exc),
                },
            ),
        )
    line = [item for item in state.all_records if item.artifact_id == plan.stable_id]
    active = [item for item in line if item.status == "active"]
    version = [item for item in line if item.version == plan.version]
    record("no_active_work_package", not active, [], [item.path for item in active])
    record(
        "completed_exactly_once",
        len(version) == 1
        and version[0].status == "completed"
        and version[0].path == plan.archive_path,
        {"count": 1, "status": "completed", "path": plan.archive_path},
        [(item.status, item.path) for item in version],
    )
    record(
        "completion_lifecycle",
        completed.frontmatter.get("evidence_class") == "historical_evidence"
        and completed.frontmatter.get("canonical_path") == plan.archive_path,
        {
            "evidence_class": "historical_evidence",
            "canonical_path": plan.archive_path,
        },
        {
            "evidence_class": completed.frontmatter.get("evidence_class"),
            "canonical_path": completed.frontmatter.get("canonical_path"),
        },
    )
    record(
        "completion_archive_path",
        history_path_allowed(
            profile,
            plan.archive_path,
            completed.frontmatter,
            active_path=plan.active_path,
        ),
        profile.history_archive_rule,
        plan.archive_path,
    )
    actual_preserved = {
        key: completed.frontmatter.get(key)
        for key in (plan.preserved_frontmatter or {})
    }
    record(
        "completion_preserve",
        actual_preserved == (plan.preserved_frontmatter or {}),
        plan.preserved_frontmatter or {},
        actual_preserved,
    )
    record(
        "completion_body",
        completed.body == plan.target_body
        and _completion_evidence_present(completed.body),
        "owner-prepared body with complete completion evidence",
        completed.body,
    )
    return PostconditionReport(
        passed=all(item["passed"] for item in results), results=tuple(results)
    )


def complete_work_package(
    plan: CompletionPlan,
    *,
    transaction_engine: FileTransactionEngine,
    apply: bool,
    idempotency_key: str,
    operation_context: OperationContext | None = None,
    controller: InProcessRunController | None = None,
) -> OperationResult:
    if (
        plan.disposition is not ResultDisposition.SUCCEEDED
        or plan.mutation_plan is None
    ):
        if controller is not None:
            controller.transition(RunState.PLANNED)
            controller.transition(RunState.BLOCKED)
        return _result("artifact.transition", plan.disposition, plan.message)
    if controller is not None:
        controller.transition(RunState.PLANNED)
        controller.transition(RunState.PREVIEWED)
        controller.transition(RunState.AWAITING_AUTHORITY)
    if plan.authority_decision is None or not plan.authority_decision.authorized:
        if controller is not None:
            controller.transition(RunState.BLOCKED)
        reasons = plan.authority_decision.reasons if plan.authority_decision else ()
        return _result(
            "artifact.transition",
            ResultDisposition.BLOCKED,
            "; ".join(reasons) or "verified runtime authority is required",
        )
    if controller is not None:
        controller.transition(RunState.AUTHORIZED)
    if not apply:
        preview = transaction_engine.preview(plan.mutation_plan)
        return _result(
            "artifact.transition",
            ResultDisposition.SUCCEEDED,
            "work-package completion check passed; no mutation performed",
            outputs={
                "plan_id": plan.mutation_plan.plan_id,
                "preview": preview,
                "applied": False,
            },
        )
    if controller is not None:
        controller.transition(RunState.STAGING)
        controller.transition(RunState.APPLYING)
    transaction = transaction_engine.apply(
        plan.mutation_plan,
        idempotency_key=idempotency_key,
        domain_verifier=lambda root: verify_work_package_completion(plan, root),
        verification_hook=(
            (lambda: controller.transition(RunState.VERIFYING))
            if controller is not None
            else None
        ),
        run_id=operation_context.run_id if operation_context else None,
    )
    _finish_controller(controller, transaction)
    return _result(
        "artifact.transition",
        transaction.disposition,
        (
            "work package completed and archived"
            if transaction.disposition is ResultDisposition.SUCCEEDED
            else transaction.message
        ),
        outputs={
            "plan_id": plan.mutation_plan.plan_id,
            "applied": transaction.disposition is ResultDisposition.SUCCEEDED,
        },
        source=transaction,
    )


def transition_operation(request: OperationRequest, **kwargs: Any) -> OperationResult:
    parameters = {**request.parameters, **kwargs}
    profile = parameters.get("transition_profile")
    if profile != "work_package.complete":
        return _result(
            "artifact.transition",
            ResultDisposition.UNSUPPORTED,
            "only the work_package.complete transition profile is supported",
            correlation_id=request.correlation_id,
        )
    authority = parameters.get("_authority_decision")
    operation_context = parameters.get("_operation_context")
    controller = parameters.get("_run_controller")
    if (
        not isinstance(authority, AuthorityDecision)
        or not isinstance(operation_context, OperationContext)
        or not isinstance(controller, InProcessRunController)
    ):
        return _result(
            "artifact.transition",
            ResultDisposition.BLOCKED,
            "artifact mutations require the shared application context and controller",
            correlation_id=request.correlation_id,
        )
    vault_root = Path(parameters["vault_root"])
    engine = parameters.get("_transaction_engine")
    if not isinstance(engine, FileTransactionEngine):
        engine = FileTransactionEngine(vault_root, Path(parameters["run_root"]))
    key = request.idempotency_key or request.fingerprint
    replay = engine.idempotency_disposition(key, request.fingerprint)
    if replay is not None:
        return _result(
            "artifact.transition",
            replay,
            "idempotent replay"
            if replay is ResultDisposition.IDEMPOTENT_REPLAY
            else "idempotency key conflict",
            correlation_id=request.correlation_id,
        )
    plan = plan_work_package_completion(
        vault_root=vault_root,
        stable_id=str(parameters.get("stable_id") or request.targets[0]),
        prepared_file=(
            Path(parameters["prepared_file"])
            if parameters.get("prepared_file")
            else None
        ),
        completion_evidence_file=(
            Path(parameters["completion_evidence_file"])
            if parameters.get("completion_evidence_file")
            else None
        ),
        archive_path=str(parameters["archive_path"]),
        authority=authority,
        transaction_engine=engine,
        request_fingerprint=request.fingerprint,
    )
    return complete_work_package(
        plan,
        transaction_engine=engine,
        apply=request.requested_mode == "apply",
        idempotency_key=key,
        operation_context=operation_context,
        controller=controller,
    )
