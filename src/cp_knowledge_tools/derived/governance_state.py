"""Build a rebuildable, non-normative governance current-state projection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ID_FIELDS = {
    "baseline": "baseline_id",
    "decision_record": "decision_id",
    "framework": "framework_id",
    "manual": "manual_id",
    "policy": "policy_id",
    "process": "process_id",
    "specification": "specification_id",
    "template": "template_id",
    "work_package": "work_package_id",
}
STABLE_RELATION_FIELDS = (
    "governed_by",
    "depends_on",
    "aligned_with",
    "related_decisions",
)
VERSIONED_EVIDENCE_FIELDS = ("implements_decisions", "validated_against", "supersedes")
MIXED_RELATION_FIELDS = ("references",)


class GovernanceStateError(RuntimeError):
    """Raised when canonical current state cannot be derived unambiguously."""


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    document_type: str
    version: str
    status: str
    evidence_class: str | None
    title: str
    path: str
    canonical_path: str | None
    former_ids: tuple[str, ...] = ()
    frontmatter: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class ReferenceEdge:
    consumer_id: str
    consumer_version: str
    relation: str
    target_ref: str
    target_id: str
    target_version: str | None


@dataclass(slots=True)
class DerivedGovernanceState:
    active: dict[str, ArtifactRecord]
    all_records: list[ArtifactRecord]
    reverse_dependencies: dict[str, list[ReferenceEdge]]
    aliases: dict[str, str]

    def active_record(self, artifact_id: str) -> ArtifactRecord | None:
        canonical = self.aliases.get(artifact_id, artifact_id)
        return self.active.get(canonical)

    def consumers_of(self, artifact_id: str) -> list[ReferenceEdge]:
        canonical = self.aliases.get(artifact_id, artifact_id)
        return list(self.reverse_dependencies.get(canonical, ()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "active": {
                key: {
                    "artifact_id": rec.artifact_id,
                    "document_type": rec.document_type,
                    "version": rec.version,
                    "status": rec.status,
                    "evidence_class": rec.evidence_class,
                    "title": rec.title,
                    "path": rec.path,
                    "canonical_path": rec.canonical_path,
                    "former_ids": list(rec.former_ids),
                }
                for key, rec in sorted(self.active.items())
            },
            "reverse_dependencies": {
                key: [
                    {
                        "consumer_id": edge.consumer_id,
                        "consumer_version": edge.consumer_version,
                        "relation": edge.relation,
                        "target_ref": edge.target_ref,
                        "target_id": edge.target_id,
                        "target_version": edge.target_version,
                    }
                    for edge in edges
                ]
                for key, edges in sorted(self.reverse_dependencies.items())
            },
            "aliases": dict(sorted(self.aliases.items())),
        }


def _split_frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return {}
    parsed = yaml.safe_load("\n".join(lines[1:end]))
    return parsed if isinstance(parsed, dict) else {}


def _iter_markdown(root: Path, scan_roots: Iterable[str] | None) -> Iterable[Path]:
    roots = tuple(scan_roots or ("Systems", "Processes", "Development", "Templates"))
    seen: set[Path] = set()
    for rel in roots:
        base = (root / rel).resolve()
        if not base.exists() or not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            resolved = path.resolve()
            if resolved in seen:
                continue
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                continue
            seen.add(resolved)
            yield resolved


def _versioned_ref(ref: str) -> tuple[str, str | None]:
    if "@" not in ref:
        return ref, None
    artifact_id, version = ref.rsplit("@", 1)
    return artifact_id, version


def _list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _record_from_path(root: Path, path: Path) -> ArtifactRecord | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None
    fm = _split_frontmatter(text)
    document_type = fm.get("document_type")
    id_field = ID_FIELDS.get(document_type)
    if id_field is None:
        return None
    artifact_id = fm.get(id_field)
    version = fm.get("version")
    status = fm.get("status")
    title = fm.get("title")
    if not all(
        isinstance(value, str) and value
        for value in (artifact_id, version, status, title)
    ):
        return None
    former = tuple(_list_values(fm.get("former_ids")))
    return ArtifactRecord(
        artifact_id=artifact_id,
        document_type=document_type,
        version=version,
        status=status,
        evidence_class=fm.get("evidence_class")
        if isinstance(fm.get("evidence_class"), str)
        else None,
        title=title,
        path=path.relative_to(root).as_posix(),
        canonical_path=fm.get("canonical_path")
        if isinstance(fm.get("canonical_path"), str)
        else None,
        former_ids=former,
        frontmatter=fm,
    )


def _edges(
    records: Iterable[ArtifactRecord], aliases: dict[str, str]
) -> dict[str, list[ReferenceEdge]]:
    reverse: dict[str, list[ReferenceEdge]] = {}
    for rec in records:
        fm = rec.frontmatter
        for field_name in (
            *STABLE_RELATION_FIELDS,
            *VERSIONED_EVIDENCE_FIELDS,
            *MIXED_RELATION_FIELDS,
        ):
            for ref in _list_values(fm.get(field_name)):
                target_id, target_version = _versioned_ref(ref)
                canonical_id = aliases.get(target_id, target_id)
                reverse.setdefault(canonical_id, []).append(
                    ReferenceEdge(
                        consumer_id=rec.artifact_id,
                        consumer_version=rec.version,
                        relation=field_name,
                        target_ref=ref,
                        target_id=canonical_id,
                        target_version=target_version,
                    )
                )
    for edges in reverse.values():
        edges.sort(
            key=lambda e: (e.consumer_id, e.consumer_version, e.relation, e.target_ref)
        )
    return reverse


def build_governance_state(
    root: Path, scan_roots: Iterable[str] | None = None
) -> DerivedGovernanceState:
    """Derive current governance state and reverse dependencies."""
    root = root.resolve()
    records = [
        rec
        for path in _iter_markdown(root, scan_roots)
        if (rec := _record_from_path(root, path)) is not None
    ]
    active: dict[str, ArtifactRecord] = {}
    aliases: dict[str, str] = {}
    for rec in records:
        for alias in rec.former_ids:
            existing = aliases.get(alias)
            if existing is not None and existing != rec.artifact_id:
                raise GovernanceStateError(
                    f"former_id {alias!r} claimed by multiple artifact lines"
                )
            aliases[alias] = rec.artifact_id
        if rec.status == "active":
            if rec.artifact_id in active:
                other = active[rec.artifact_id]
                raise GovernanceStateError(
                    "multiple active versions for "
                    f"{rec.artifact_id}: {other.version}, {rec.version}"
                )
            active[rec.artifact_id] = rec
    current_records = [
        rec for rec in records if rec.status in {"active", "draft", "proposed"}
    ]
    reverse = _edges(current_records, aliases)
    return DerivedGovernanceState(
        active=active,
        all_records=records,
        reverse_dependencies=reverse,
        aliases=aliases,
    )
