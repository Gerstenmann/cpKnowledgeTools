"""Deterministic read-only resolution of active cp-wiki Managed Artifacts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import yaml

from .errors import VaultError
from .models import MarkdownDocument
from .vault import Vault

STABLE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
MAX_BUNDLE_SIZE = 20

IDENTITY_FIELD_BY_DOCUMENT_TYPE: dict[str, str] = {
    "baseline": "baseline_id",
    "decision_record": "decision_id",
    "policy": "policy_id",
    "framework": "framework_id",
    "specification": "specification_id",
    "process": "process_id",
    "work_package": "work_package_id",
    "template": "template_id",
    "manual": "manual_id",
}


class GovernanceResolutionError(VaultError):
    """Base error for governance-resolution failures."""


class ActiveArtifactNotFoundError(GovernanceResolutionError):
    """Raised when no active Managed Artifact can be resolved."""


class MultipleActiveArtifactsError(GovernanceResolutionError):
    """Raised when a stable ID resolves to more than one active artifact."""


class ArtifactIntegrityError(GovernanceResolutionError):
    """Raised when an active artifact is found but its line is not integral."""


@dataclass(frozen=True, slots=True)
class ResolutionIssue:
    """One deterministic integrity issue discovered during resolution."""

    code: str
    path: str
    message: str
    actual: Any | None = None
    expected: Any | None = None


@dataclass(frozen=True, slots=True)
class ActiveArtifactResolution:
    """Resolved active Managed Artifact metadata."""

    requested_id: str
    stable_id: str
    resolved_via: str
    document_type: str
    identity_field: str
    title: str | None
    version: str
    status: str
    evidence_class: str | None
    relative_path: str
    canonical_path: str | None
    integrity_ok: bool
    integrity_issues: list[ResolutionIssue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ArtifactRecord:
    document: MarkdownDocument
    document_type: str
    identity_field: str
    stable_id: str
    former_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ScanFailure:
    path: str
    raw_prefix: str
    error: str


@dataclass(slots=True)
class _GovernanceIndex:
    by_stable_id: dict[str, list[_ArtifactRecord]] = field(default_factory=dict)
    by_former_id: dict[str, list[_ArtifactRecord]] = field(default_factory=dict)
    scan_failures: list[_ScanFailure] = field(default_factory=list)


def _validate_requested_id(stable_id: str) -> str:
    normalized = stable_id.strip()
    if not normalized:
        raise GovernanceResolutionError("stable_id must not be empty.")
    if not STABLE_ID_PATTERN.fullmatch(normalized):
        raise GovernanceResolutionError(
            f"Invalid stable artifact ID syntax: {stable_id!r}"
        )
    return normalized


def _record_from_document(document: MarkdownDocument) -> _ArtifactRecord | None:
    document_type = document.frontmatter.get("document_type")
    if not isinstance(document_type, str):
        return None

    identity_field = IDENTITY_FIELD_BY_DOCUMENT_TYPE.get(document_type)
    if identity_field is None:
        return None

    stable_id = document.frontmatter.get(identity_field)
    if not isinstance(stable_id, str) or not stable_id.strip():
        return None

    former_value = document.frontmatter.get("former_ids", [])
    former_ids = (
        tuple(
            item.strip()
            for item in former_value
            if isinstance(item, str) and item.strip()
        )
        if isinstance(former_value, list)
        else ()
    )

    return _ArtifactRecord(
        document=document,
        document_type=document_type,
        identity_field=identity_field,
        stable_id=stable_id.strip(),
        former_ids=former_ids,
    )


def _build_index(vault: Vault) -> _GovernanceIndex:
    index = _GovernanceIndex()

    for file_info in vault.list_markdown_files():
        try:
            document = vault.read_document(file_info.relative_path)
        except (ValueError, yaml.YAMLError) as exc:
            raw_prefix = vault.read_markdown(file_info.relative_path)[:16_384]
            index.scan_failures.append(
                _ScanFailure(
                    path=file_info.relative_path,
                    raw_prefix=raw_prefix,
                    error=str(exc),
                )
            )
            continue

        record = _record_from_document(document)
        if record is None:
            continue

        index.by_stable_id.setdefault(record.stable_id, []).append(record)
        for former_id in record.former_ids:
            index.by_former_id.setdefault(former_id, []).append(record)

    return index


def _candidate_records(
    index: _GovernanceIndex,
    requested_id: str,
) -> list[tuple[_ArtifactRecord, str]]:
    candidates: dict[str, tuple[_ArtifactRecord, str]] = {}

    for record in index.by_stable_id.get(requested_id, []):
        candidates[record.document.relative_path] = (record, "stable_id")

    for record in index.by_former_id.get(requested_id, []):
        candidates.setdefault(record.document.relative_path, (record, "former_id"))

    return list(candidates.values())


def _is_current_work_package_path(relative_path: str) -> bool:
    """Return whether a path is the active zone for a scoped Work Package."""

    parts = relative_path.split("/")
    return (
        len(parts) >= 4
        and parts[0] == "Development"
        and parts[2] == "Work Packages"
        and not {"Archive", "History"}.intersection(parts)
    )


def _integrity_issues(
    index: _GovernanceIndex,
    requested_id: str,
    active: _ArtifactRecord,
) -> list[ResolutionIssue]:
    issues: list[ResolutionIssue] = []
    document = active.document
    version = document.frontmatter.get("version")
    canonical_path = document.frontmatter.get("canonical_path")

    for failure in index.scan_failures:
        if requested_id in failure.raw_prefix or active.stable_id in failure.raw_prefix:
            issues.append(
                ResolutionIssue(
                    code="candidate_frontmatter_unreadable",
                    path=failure.path,
                    message=(
                        "A Markdown file mentioning this artifact line could not "
                        "be parsed safely."
                    ),
                    actual=failure.error,
                )
            )

    if not isinstance(canonical_path, str) or unicodedata.normalize(
        "NFC", canonical_path
    ) != unicodedata.normalize("NFC", document.relative_path):
        issues.append(
            ResolutionIssue(
                code="canonical_path_mismatch",
                path=document.relative_path,
                message=(
                    "Active artifact canonical_path does not match its actual path."
                ),
                actual=canonical_path,
                expected=document.relative_path,
            )
        )

    path_parts = document.relative_path.split("/")
    is_current_work_package = (
        active.document_type == "work_package"
        and _is_current_work_package_path(document.relative_path)
    )
    if (
        (
            document.relative_path.startswith("Development/")
            and not is_current_work_package
        )
        or "Archive" in path_parts
        or "History" in path_parts
    ):
        issues.append(
            ResolutionIssue(
                code="active_artifact_in_inactive_zone",
                path=document.relative_path,
                message="Active artifact is in a Development/Archive/History zone.",
            )
        )

    if isinstance(version, str):
        for record in index.by_stable_id.get(active.stable_id, []):
            other = record.document
            if other.relative_path == document.relative_path:
                continue
            if other.frontmatter.get("version") != version:
                continue

            issues.append(
                ResolutionIssue(
                    code="duplicate_stable_id_and_version",
                    path=other.relative_path,
                    message=(
                        f"Artifact line {active.stable_id} has another canonical "
                        f"file for version {version}."
                    ),
                    actual=other.frontmatter.get("status"),
                    expected="exactly one canonical file per stable ID and version",
                )
            )

    return issues


def _resolve_from_index(
    index: _GovernanceIndex,
    requested_id: str,
) -> ActiveArtifactResolution:
    candidates = _candidate_records(index, requested_id)
    active_candidates = [
        item
        for item in candidates
        if item[0].document.frontmatter.get("status") == "active"
    ]

    if not active_candidates:
        raise ActiveArtifactNotFoundError(
            f"No active Managed Artifact resolves from {requested_id}."
        )

    if len(active_candidates) > 1:
        paths = ", ".join(
            item[0].document.relative_path for item in active_candidates
        )
        raise MultipleActiveArtifactsError(
            f"Multiple active Managed Artifacts resolve from {requested_id}: {paths}"
        )

    active, resolved_via = active_candidates[0]
    document = active.document
    version = document.frontmatter.get("version")
    evidence_class = document.frontmatter.get("evidence_class")
    canonical_path = document.frontmatter.get("canonical_path")

    if not isinstance(version, str) or not version.strip():
        raise GovernanceResolutionError(
            f"Resolved artifact has invalid version: {document.relative_path}"
        )

    issues = _integrity_issues(index, requested_id, active)

    return ActiveArtifactResolution(
        requested_id=requested_id,
        stable_id=active.stable_id,
        resolved_via=resolved_via,
        document_type=active.document_type,
        identity_field=active.identity_field,
        title=document.title,
        version=version,
        status="active",
        evidence_class=evidence_class if isinstance(evidence_class, str) else None,
        relative_path=document.relative_path,
        canonical_path=canonical_path if isinstance(canonical_path, str) else None,
        integrity_ok=not issues,
        integrity_issues=issues,
    )


def resolve_active_artifact(
    vault: Vault,
    stable_id: str,
) -> ActiveArtifactResolution:
    """Resolve a stable/current or former ID to exactly one active artifact."""

    requested_id = _validate_requested_id(stable_id)
    return _resolve_from_index(_build_index(vault), requested_id)


def inspect_artifact_line(vault: Vault, stable_id: str) -> tuple[dict[str, Any], ...]:
    """Return non-authoritative lifecycle diagnostics from the canonical index.

    This intentionally reuses the same index and identity resolution as the active
    resolver.  It is used only to distinguish a missing line from an existing but
    inactive line after active resolution has already failed.
    """

    requested_id = _validate_requested_id(stable_id)
    index = _build_index(vault)
    return tuple(
        {
            "stable_id": record.stable_id,
            "document_type": record.document_type,
            "version": record.document.frontmatter.get("version"),
            "status": record.document.frontmatter.get("status"),
            "relative_path": record.document.relative_path,
            "resolved_via": resolved_via,
        }
        for record, resolved_via in sorted(
            _candidate_records(index, requested_id),
            key=lambda item: item[0].document.relative_path,
        )
    )


def read_active_artifact(
    vault: Vault,
    stable_id: str,
) -> tuple[ActiveArtifactResolution, MarkdownDocument]:
    """Resolve and read an active artifact, failing closed on integrity issues."""

    requested_id = _validate_requested_id(stable_id)
    index = _build_index(vault)
    resolution = _resolve_from_index(index, requested_id)

    if not resolution.integrity_ok:
        codes = ", ".join(issue.code for issue in resolution.integrity_issues)
        raise ArtifactIntegrityError(
            f"Active artifact {resolution.stable_id}@{resolution.version} has "
            f"integrity issues: {codes}"
        )

    return resolution, vault.read_document(resolution.relative_path)


def resolve_governance_bundle(
    vault: Vault,
    stable_ids: list[str],
) -> list[ActiveArtifactResolution]:
    """Resolve a small ordered bundle of stable IDs against one live-Vault scan."""

    if not stable_ids:
        raise GovernanceResolutionError("stable_ids must contain at least one ID.")
    if len(stable_ids) > MAX_BUNDLE_SIZE:
        raise GovernanceResolutionError(
            f"stable_ids must contain at most {MAX_BUNDLE_SIZE} IDs."
        )

    requested_ids = [
        _validate_requested_id(stable_id)
        for stable_id in dict.fromkeys(stable_ids)
    ]
    index = _build_index(vault)
    return [_resolve_from_index(index, stable_id) for stable_id in requested_ids]
