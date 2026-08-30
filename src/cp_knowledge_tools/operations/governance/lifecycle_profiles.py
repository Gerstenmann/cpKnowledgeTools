"""Type-bound K2 Managed Artifact lifecycle profiles.

The profiles are an immutable technical projection of the active Managed
Artifact rule homes.  They deliberately contain no workflow or policy DSL.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from cp_knowledge_tools.mcp.cp_wiki.governance import (
    IDENTITY_FIELD_BY_DOCUMENT_TYPE,
)


class UnsupportedLifecycleProfileError(ValueError):
    """Raised when K2 has no complete lifecycle profile for a document type."""


@dataclass(frozen=True, slots=True)
class ManagedArtifactLifecycleProfile:
    """Small immutable capability and invariant description for one type."""

    document_type: str
    identity_field: str
    supported_operations: tuple[str, ...]
    revise_capable: bool
    initial_activation_capable: bool
    follow_up_activation_capable: bool
    completion_capable: bool
    source_states: tuple[str, ...]
    target_status: str
    target_evidence_class: str
    initial_versions: tuple[str, ...]
    development_path_rule: str
    active_path_rule: str
    history_archive_rule: str
    filename_rule: str
    source_artifact_semantics: str
    supersedes_semantics: str
    preserve_fields: tuple[str, ...]
    allowed_diff_fields: tuple[str, ...]
    validation_hooks: tuple[str, ...]
    postcondition_hooks: tuple[str, ...]
    rule_homes: tuple[str, ...]
    single_file_only: bool = False


_COMMON_RULE_HOMES = (
    "CPKS-POL-GOV-AUTH",
    "CPKS-SPEC-ART",
    "CPKS-SPEC-OPS",
    "CPKS-DEC-016",
    "CPKS-DEC-019",
    "CPKS-DEC-021",
    "GOV-P01",
)
_COMMON_PRESERVE = (
    "validated_against",
    "implements_decisions",
    "source_artifact",
)
_ACTIVATABLE_OPERATIONS = ("artifact.revise", "artifact.activate")


def _profile(
    document_type: str,
    *,
    development_path_rule: str,
    active_path_rule: str,
    history_archive_rule: str,
    initial_versions: tuple[str, ...] = ("0.1",),
    rule_homes: tuple[str, ...] = (),
    single_file_only: bool = False,
) -> ManagedArtifactLifecycleProfile:
    return ManagedArtifactLifecycleProfile(
        document_type=document_type,
        identity_field=IDENTITY_FIELD_BY_DOCUMENT_TYPE[document_type],
        supported_operations=_ACTIVATABLE_OPERATIONS,
        revise_capable=True,
        initial_activation_capable=True,
        follow_up_activation_capable=True,
        completion_capable=False,
        source_states=("draft", "proposed"),
        target_status="active",
        target_evidence_class="active_constraint",
        initial_versions=initial_versions,
        development_path_rule=development_path_rule,
        active_path_rule=active_path_rule,
        history_archive_rule=history_archive_rule,
        filename_rule="managed_artifact_id_version_title",
        source_artifact_semantics=(
            "required_for_revision_and_follow_up; absent_for_initial"
        ),
        supersedes_semantics=(
            "absent_before_activation; exact_predecessor_for_follow_up"
        ),
        preserve_fields=_COMMON_PRESERVE,
        allowed_diff_fields=(
            "status",
            "evidence_class",
            "canonical_path",
            "supersedes",
            "approved_by",
            "approved_at",
            "effective_from",
        ),
        validation_hooks=("identity", "version", "path", "references"),
        postcondition_hooks=(
            "reread",
            "unique_line",
            "canonical_path",
            "activation_target_body",
            "references_resolve",
        ),
        rule_homes=(*_COMMON_RULE_HOMES, *rule_homes),
        single_file_only=single_file_only,
    )


_PROFILES = {
    "specification": _profile(
        "specification",
        development_path_rule="responsible_development_context",
        active_path_rule="type_specific_non_development_canonical_path",
        history_archive_rule="local_archive_not_history",
    ),
    "decision_record": _profile(
        "decision_record",
        development_path_rule="cpks_draft_decisions",
        active_path_rule="cpks_decisions",
        history_archive_rule="cpks_decisions_history",
        initial_versions=("0.1", "1.0"),
    ),
    "policy": _profile(
        "policy",
        development_path_rule="cpks_governance_development",
        active_path_rule="cpks_governance_policies",
        history_archive_rule="cpks_governance_archive_policies",
    ),
    "framework": _profile(
        "framework",
        development_path_rule="cpks_governance_development",
        active_path_rule="cpks_governance_root",
        history_archive_rule="cpks_governance_archive_frameworks",
    ),
    "process": _profile(
        "process",
        development_path_rule="process_domain_development",
        active_path_rule="process_domain",
        history_archive_rule="process_domain_archive",
        rule_homes=("CPKS-SPEC-PROC", "CPKS-FWK-AIW"),
        single_file_only=True,
    ),
    "work_package": ManagedArtifactLifecycleProfile(
        document_type="work_package",
        identity_field=IDENTITY_FIELD_BY_DOCUMENT_TYPE["work_package"],
        supported_operations=("artifact.transition",),
        revise_capable=False,
        initial_activation_capable=False,
        follow_up_activation_capable=False,
        completion_capable=True,
        source_states=("active",),
        target_status="completed",
        target_evidence_class="historical_evidence",
        initial_versions=("0.1",),
        development_path_rule="component_work_packages_active",
        active_path_rule="component_work_packages_active",
        history_archive_rule="component_work_packages_local_archive",
        filename_rule="managed_artifact_id_version_title",
        source_artifact_semantics="preserve_existing_value",
        supersedes_semantics="preserve_existing_value",
        preserve_fields=(
            "work_package_id",
            "version",
            "owner",
            "authority_basis",
            "authority_scope",
            "scope_summary",
            "runtime_authority_contracts",
            "affected_artifacts",
            "target_artifacts",
        ),
        allowed_diff_fields=(
            "status",
            "evidence_class",
            "canonical_path",
            "revised",
        ),
        validation_hooks=("identity", "preserve", "completion_evidence", "path"),
        postcondition_hooks=(
            "reread",
            "completed_exactly_once",
            "no_active_version",
            "preserve",
        ),
        rule_homes=(*_COMMON_RULE_HOMES, "CPKS-SPEC-WP"),
    ),
}


_PROCESS_DOMAIN_DIRECTORIES = {
    "governance": "Governance",
    "knowledge_management": "Knowledge Management",
    "development": "Development",
    "operations": "Operations",
    "ai_working": "Agent Integration",
}


def get_lifecycle_profile(document_type: str) -> ManagedArtifactLifecycleProfile:
    try:
        return _PROFILES[document_type]
    except KeyError as exc:
        raise UnsupportedLifecycleProfileError(
            f"unsupported managed artifact document_type: {document_type}"
        ) from exc


def supported_document_types(operation_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            document_type
            for document_type, profile in _PROFILES.items()
            if operation_id in profile.supported_operations
        )
    )


def expected_filename(
    stable_id: str, version: str, title: str, *, active: bool
) -> str:
    marker = stable_id if active else f"{stable_id}@{version}"
    return f"{marker} {title}.md"


def _safe_relative(relative_path: str) -> PurePosixPath | None:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        return None
    return path


def is_process_package_path(relative_path: str) -> bool:
    path = _safe_relative(relative_path)
    return bool(path and len(path.parts) > 1 and path.parent.name == path.stem)


def development_path_allowed(
    profile: ManagedArtifactLifecycleProfile,
    relative_path: str,
    frontmatter: dict[str, Any],
) -> bool:
    path = _safe_relative(relative_path)
    if path is None or path.parts[0] != "Development":
        return False
    if {"Archive", "History", "Reviews"}.intersection(path.parts):
        return False
    if profile.document_type == "decision_record":
        return path.parts[:4] == (
            "Development",
            "cpKnowledgeSystem",
            "Governance",
            "Draft Decisions",
        )
    if profile.document_type == "process":
        domain = frontmatter.get("process_domain")
        directory = _PROCESS_DOMAIN_DIRECTORIES.get(domain)
        if directory is None:
            return False
        if domain == "governance":
            return path.parts[:4] == (
                "Development",
                "cpKnowledgeSystem",
                "Governance",
                "Draft Processes",
            )
        canonical_parent = (
            PurePosixPath("Development")
            / "cpKnowledgeSystem"
            / "Processes"
            / directory
        )
        return path.parent == canonical_parent or (
            path.parent.parent == canonical_parent
            and is_process_package_path(relative_path)
        )
    if profile.document_type in {"policy", "framework"}:
        return path.parts[:3] == (
            "Development",
            "cpKnowledgeSystem",
            "Governance",
        )
    if profile.document_type == "specification":
        return "Work Packages" not in path.parts
    return False


def active_path_allowed(
    profile: ManagedArtifactLifecycleProfile,
    relative_path: str,
    frontmatter: dict[str, Any],
) -> bool:
    path = _safe_relative(relative_path)
    stable_id = frontmatter.get(profile.identity_field)
    version = frontmatter.get("version")
    title = frontmatter.get("title")
    if path is None or not all(
        isinstance(v, str) and v for v in (stable_id, version, title)
    ):
        return False
    if path.name != expected_filename(stable_id, version, title, active=True):
        return False
    if path.parts[0] == "Development" or {"Archive", "History"}.intersection(
        path.parts
    ):
        return False
    if profile.document_type == "decision_record":
        return path.parent.as_posix() == (
            "Systems/cpKnowledgeSystem/Governance/Decisions"
        )
    if profile.document_type == "policy":
        return path.parent.as_posix() == (
            "Systems/cpKnowledgeSystem/Governance/Policies"
        )
    if profile.document_type == "framework":
        return path.parent.as_posix() == "Systems/cpKnowledgeSystem/Governance"
    if profile.document_type == "process":
        domain = frontmatter.get("process_domain")
        directory = _PROCESS_DOMAIN_DIRECTORIES.get(domain)
        return (
            directory is not None
            and path.parent.as_posix() == f"Processes/{directory}"
            and not is_process_package_path(relative_path)
        )
    if profile.document_type == "specification":
        return path.parts[0] == "Systems"
    if profile.document_type == "work_package":
        return (
            len(path.parts) >= 4
            and path.parts[0] == "Development"
            and path.parts[2] == "Work Packages"
            and not {"Archive", "History"}.intersection(path.parts)
        )
    return False


def history_path_allowed(
    profile: ManagedArtifactLifecycleProfile,
    relative_path: str,
    frontmatter: dict[str, Any],
    *,
    active_path: str | None = None,
) -> bool:
    path = _safe_relative(relative_path)
    stable_id = frontmatter.get(profile.identity_field)
    version = frontmatter.get("version")
    title = frontmatter.get("title")
    if path is None or not all(
        isinstance(v, str) and v for v in (stable_id, version, title)
    ):
        return False
    if path.name != expected_filename(stable_id, version, title, active=False):
        return False
    if profile.document_type == "decision_record":
        return path.parent.as_posix() == (
            "Systems/cpKnowledgeSystem/Governance/Decisions/History"
        )
    if profile.document_type == "policy":
        return path.parent.as_posix() == (
            "Systems/cpKnowledgeSystem/Governance/Archive/Policies"
        )
    if profile.document_type == "framework":
        return path.parent.as_posix() == (
            "Systems/cpKnowledgeSystem/Governance/Archive/Frameworks"
        )
    if profile.document_type == "process":
        domain = frontmatter.get("process_domain")
        directory = _PROCESS_DOMAIN_DIRECTORIES.get(domain)
        return (
            directory is not None
            and path.parent.as_posix() == f"Processes/{directory}/Archive"
        )
    if profile.document_type == "work_package":
        if active_path is None:
            return False
        active = _safe_relative(active_path)
        return bool(active and path.parent == active.parent / "Archive")
    if profile.document_type == "specification":
        return "Archive" in path.parts and "History" not in path.parts
    return False
