#!/usr/bin/env python3
"""Upgrade the cp-wiki managed-artifact validator from revision 3.1 to 3.2.

This migration is intentionally repository-local and fail-closed:
- it requires the expected 3.1 source file and exact source anchors;
- it writes the 3.2 validator to a temporary file first;
- it parses the generated Python with ast;
- it executes the generated validator's embedded --self-test;
- only after both checks pass does it install v3.2 and remove v3.1.

Run from the cpKnowledgeTools Python environment, for example:
    python apply_validator_v3_2_upgrade.py --repo /Users/cp/Developer/cpKnowledgeTools

Use --check to construct, parse and self-test v3.2 without changing repository files.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

OLD_REL = Path("scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_draft_v3_1.py")
NEW_REL = Path("scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return source.replace(old, new, 1)


def replace_between(source: str, start: str, end: str, replacement: str, label: str) -> str:
    start_idx = source.find(start)
    if start_idx < 0:
        raise RuntimeError(f"{label}: start anchor not found")
    end_idx = source.find(end, start_idx)
    if end_idx < 0:
        raise RuntimeError(f"{label}: end anchor not found")
    return source[:start_idx] + replacement.rstrip() + "\n\n" + source[end_idx:]


def upgrade(source: str) -> str:
    source = replace_once(
        source,
        "Read-only managed-artifact validator for cp-wiki — revision 3.1.",
        "Read-only managed-artifact validator for cp-wiki — revision 3.2.",
        "docstring revision",
    )
    source = replace_once(source, "- CPKS-SPEC-ART@0.2 (draft)", "- CPKS-SPEC-ART@0.3 (active)", "ART basis")
    source = replace_once(source, "- CPKS-SPEC-PROC@0.3 (draft)", "- CPKS-SPEC-PROC@0.3 (active)", "PROC basis")
    source = replace_once(source, "- CPKS-BL@0.43", "- CPKS-DEC-021@0.2\n- CPKS-DEC-026@1.0", "version/evidence decisions")
    source = replace_once(
        source,
        "Revision 3.1 includes all revision 3 capabilities and adds:",
        "Revision 3.2 retains the existing validator capabilities and adds ART 0.3 support:",
        "revision capability heading",
    )
    source = replace_once(
        source,
        "- filename-normalization unit tests.\n",
        "- filename-normalization unit tests;\n"
        "- complete ``evidence_class`` syntax and status-compatibility validation;\n"
        "- prospective evidence-class requirement checks for current governance/architecture and new current artifacts;\n"
        "- semantic review diagnostics where evidence role cannot be established mechanically;\n"
        "- ART 0.3 initial-version and monotonic version-sequence checks where lifecycle evidence is sufficient;\n"
        "- expanded current architecture, template and component lifecycle scan coverage.\n",
        "capability list",
    )
    source = source.replace("validate_cpwiki_managed_artifacts_draft_v3_1.py", "validate_cpwiki_managed_artifacts_v3_2.py")
    source = source.replace("cpwiki-validator-v3-1-", "cpwiki-validator-v3-2-")

    source = replace_once(
        source,
        'VALIDATION_BASIS = ["CPKS-SPEC-ART@0.2", "CPKS-SPEC-PROC@0.3"]',
        '''VALIDATOR_REVISION = "3.2"\nVALIDATION_BASIS = ["CPKS-SPEC-ART@0.3", "CPKS-SPEC-PROC@0.3"]\nEVIDENCE_CLASS_EFFECTIVE_DATE = dt.date(2026, 7, 30)\nVERSION_RULE_EFFECTIVE_DATE = dt.date(2026, 7, 27)''',
        "validation constants",
    )

    evidence_constants_anchor = '''TYPE_SPECIFIC_STATUSES: dict[str, set[str]] = {
    "baseline": COMMON_STATUSES | {"withdrawn"},
    "decision_record": COMMON_STATUSES | {"withdrawn"},
    "policy": COMMON_STATUSES | {"withdrawn"},
    "framework": COMMON_STATUSES | {"withdrawn"},
    "specification": COMMON_STATUSES | {"withdrawn"},
    "process": COMMON_STATUSES | {"withdrawn"},
    "work_package": COMMON_STATUSES | {"withdrawn", "completed", "cancelled"},
    "template": COMMON_STATUSES | {"withdrawn"},
    "manual": COMMON_STATUSES | {"withdrawn"},
}
'''
    evidence_constants = evidence_constants_anchor + '''
EVIDENCE_CLASSES = {
    "active_constraint",
    "verified_current_state",
    "historical_evidence",
    "design_candidate",
    "committed_target",
    "implementation_observation",
    "obsolete_or_conflicting",
}
EVIDENCE_CLASS_STATUS_GROUPS = {
    "active_constraint": {"active"},
    "verified_current_state": {"current_development", "active"},
    "historical_evidence": {"current_development", "closed_or_historical"},
    "design_candidate": {"current_development", "closed_or_historical"},
    "committed_target": {"current_development"},
    "implementation_observation": {"current_development", "active", "closed_or_historical"},
    "obsolete_or_conflicting": {"current_development", "closed_or_historical"},
}
EVIDENCE_REQUIRED_CURRENT_ZONES = {
    "active_governance",
    "active_processes",
    "active_architecture",
    "active_component_architecture",
    "active_templates",
}
'''
    source = replace_once(source, evidence_constants_anchor, evidence_constants, "evidence constants")

    source = replace_once(
        source,
        '''    @property
    def status(self) -> str | None:
        return scalar_text(self.frontmatter.get("status"))
''',
        '''    @property
    def status(self) -> str | None:
        return scalar_text(self.frontmatter.get("status"))

    @property
    def evidence_class(self) -> str | None:
        return scalar_text(self.frontmatter.get("evidence_class"))
''',
        "Document.evidence_class",
    )

    scan_zone = '''def scan_zone(relative: str) -> str:
    if relative.startswith("Systems/cpKnowledgeSystem/Governance/"):
        if "/Archive/" in relative or "/Decisions/History/" in relative:
            return "governance_history"
        return "active_governance"
    if relative.startswith("Systems/cpKnowledgeSystem/Architecture/"):
        if "/Archive/" in relative or "/History/" in relative:
            return "architecture_history"
        return "active_architecture"
    if relative.startswith("Systems/cpKnowledgeTools/Architecture/"):
        if "/Archive/" in relative or "/History/" in relative:
            return "component_architecture_history"
        return "active_component_architecture"
    if relative.startswith("Templates/"):
        if "/Archive/" in relative or "/History/" in relative:
            return "template_history"
        return "active_templates"
    if relative.startswith("Processes/"):
        if "/Archive/" in relative or "/History/" in relative:
            return "process_history"
        return "active_processes"
    if relative.startswith("Development/cpKnowledgeSystem/Work Packages/"):
        return "work_package_development"
    if relative.startswith("Development/cpKnowledgeSystem/Governance/"):
        return "governance_development"
    if relative.startswith("Development/cpKnowledgeSystem/Specifications/"):
        return "governance_development"
    if relative.startswith("Development/cpKnowledgeSystem/Architecture/"):
        return "architecture_development"
    if relative.startswith("Development/cp-wiki Vault/Specifications/"):
        return "referenced_specification_development"
    if relative.startswith("Development/cpKnowledgeTools/"):
        return "component_development"
    if relative.startswith("Development/") and "/Draft Processes/" in relative:
        return "process_development"
    return "unclassified"
'''
    source = replace_between(source, "def scan_zone(relative: str) -> str:\n", "def is_closed_path", scan_zone, "scan_zone")

    source = replace_once(
        source,
        '    return "CPKS-SPEC-ART@0.2" in candidates',
        '    return "CPKS-SPEC-ART@0.3" in candidates',
        "current support rule basis",
    )

    profile_function = '''def assign_validation_profile(doc: Document) -> str:
    history_zones = {
        "governance_history",
        "process_history",
        "architecture_history",
        "component_architecture_history",
        "template_history",
    }
    development_zones = {
        "governance_development",
        "process_development",
        "referenced_specification_development",
        "architecture_development",
        "component_development",
        "work_package_development",
    }
    active_zones = {
        "active_governance",
        "active_processes",
        "active_architecture",
        "active_component_architecture",
        "active_templates",
    }

    if doc.parse_error:
        if doc.scan_zone in history_zones:
            return "historical_managed"
        if doc.scan_zone in development_zones:
            return (
                "closed_development_managed"
                if is_closed_path(doc.relative_path)
                else "current_development_managed"
            )
        return "unmanaged"

    if doc.scope_class == "unmanaged":
        return "unmanaged"

    if doc.scope_class == "support":
        return "current_support" if support_is_current(doc) else "legacy_support"

    if doc.scan_zone in history_zones:
        return "historical_managed"
    if doc.scan_zone in active_zones:
        return "current_managed"
    if doc.scan_zone == "work_package_development" and doc.document_type == "work_package":
        # CPKS-SPEC-WP@0.1 §7.2: an active Work Package remains in its
        # Development context and uses the unversioned active filename.
        if doc.status == "active":
            return "current_managed"
        if doc.status in CLOSED_DEVELOPMENT_STATUSES or is_closed_path(doc.relative_path):
            return "closed_development_managed"
        return "current_development_managed"
    if doc.scan_zone in development_zones:
        if doc.status in CLOSED_DEVELOPMENT_STATUSES or is_closed_path(doc.relative_path):
            return "closed_development_managed"
        return "current_development_managed"
    return "unmanaged"
'''
    source = replace_between(source, "def assign_validation_profile(doc: Document) -> str:\n", "def iter_candidate_paths", profile_function, "assign_validation_profile")

    iter_function = '''def iter_candidate_paths(vault: Path) -> Iterable[Path]:
    roots = [
        vault / "Systems/cpKnowledgeSystem/Governance",
        vault / "Systems/cpKnowledgeSystem/Architecture",
        vault / "Systems/cpKnowledgeTools/Architecture",
        vault / "Templates",
        vault / "Development/cpKnowledgeSystem/Governance",
        vault / "Development/cpKnowledgeSystem/Specifications",
        vault / "Development/cpKnowledgeSystem/Architecture",
        vault / "Development/cpKnowledgeSystem/Work Packages",
        vault / "Development/cp-wiki Vault/Specifications",
        vault / "Development/cpKnowledgeTools",
        vault / "Processes",
    ]
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path
'''
    source = replace_between(source, "def iter_candidate_paths(vault: Path) -> Iterable[Path]:\n", "def load_document", iter_function, "iter_candidate_paths")

    evidence_functions = r'''def status_group(status: str | None) -> str | None:
    if status in {"draft", "proposed"}:
        return "current_development"
    if status == "active":
        return "active"
    if status in {"superseded", "deprecated", "archived", "withdrawn", "rejected", "completed", "cancelled"}:
        return "closed_or_historical"
    return None


def frontmatter_date(doc: Document, field: str) -> dt.date | None:
    value = scalar_text(doc.frontmatter.get(field))
    if not value or not DATE_RE.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def evidence_class_requirement(doc: Document) -> tuple[bool, str | None, bool]:
    """Return (required, reason, semantic_review_if_missing).

    ART 0.3 is prospective. A deterministic validator can prove the field is
    required for configured current governance/architecture documents and for
    artifacts created after the evidence-class rule took effect. A later
    ``revised`` date alone cannot prove a material revision, so it produces a
    semantic-review warning rather than a false error.
    """
    if doc.validation_profile not in FULL_CURRENT_PROFILES:
        return False, None, False
    if doc.scan_zone in EVIDENCE_REQUIRED_CURRENT_ZONES:
        return True, "current governance/architecture artifact in the configured active scan", False
    created = frontmatter_date(doc, "created")
    if created and created > EVIDENCE_CLASS_EFFECTIVE_DATE:
        return True, "current managed artifact created after the evidence-class rule took effect", False
    source_artifact = scalar_text(doc.frontmatter.get("source_artifact"))
    revised = frontmatter_date(doc, "revised")
    if source_artifact and revised and revised > EVIDENCE_CLASS_EFFECTIVE_DATE:
        return True, "new concrete current version after the evidence-class rule took effect", False
    if revised and revised > EVIDENCE_CLASS_EFFECTIVE_DATE:
        return False, None, True
    return False, None, False


def validate_evidence_class(doc: Document, findings: list[Finding]) -> None:
    raw = doc.frontmatter.get("evidence_class")
    required, reason, review_missing = evidence_class_requirement(doc)
    if raw is None or raw == "":
        if required:
            add(
                findings,
                doc,
                "error",
                "missing_evidence_class",
                "Current managed artifact requires evidence_class under CPKS-SPEC-ART@0.3.",
                field="evidence_class",
                expected=reason,
            )
        elif review_missing:
            add(
                findings,
                doc,
                "warning",
                "evidence_class_semantic_review_required",
                "The artifact was revised after the evidence-class rule took effect, but revision metadata alone cannot prove that the change was material.",
                field="evidence_class",
                expected="review whether CPKS-SPEC-ART@0.3 §11.7 requires evidence_class",
            )
        return

    if not isinstance(raw, str) or raw not in EVIDENCE_CLASSES:
        add(
            findings,
            doc,
            "error",
            "invalid_evidence_class",
            "evidence_class must be exactly one controlled scalar string value.",
            field="evidence_class",
            actual=raw,
            expected=sorted(EVIDENCE_CLASSES),
        )
        return

    group = status_group(doc.status)
    allowed_groups = EVIDENCE_CLASS_STATUS_GROUPS[raw]
    if group is not None and group not in allowed_groups:
        add(
            findings,
            doc,
            "error",
            "evidence_class_status_mismatch",
            "evidence_class is not compatible with the artifact lifecycle status.",
            field="evidence_class",
            actual={"evidence_class": raw, "status": doc.status},
            expected=sorted(allowed_groups),
        )
        return

    # Semantic hints are deliberately narrow. The validator must not infer the
    # document's primary role from path/status alone.
    if raw == "committed_target":
        binding_fields = ("authority_basis", "related_decisions", "depends_on", "references")
        if not any(not is_empty(doc.frontmatter.get(field)) for field in binding_fields):
            add(
                findings,
                doc,
                "warning",
                "evidence_class_semantic_review_required",
                "committed_target requires a traceable active binding source; none is mechanically visible in the standard binding/reference fields.",
                field="evidence_class",
                actual=raw,
                expected="active Decision, Work Package, Owner instruction or other traceable authority",
            )
    elif raw == "verified_current_state" and doc.document_type != "baseline":
        add(
            findings,
            doc,
            "warning",
            "evidence_class_semantic_review_required",
            "verified_current_state is syntactically valid, but current-state verification scope cannot be established mechanically for this document type.",
            field="evidence_class",
            actual=raw,
        )
    elif raw in {"implementation_observation", "obsolete_or_conflicting"}:
        add(
            findings,
            doc,
            "warning",
            "evidence_class_semantic_review_required",
            "The selected evidence_class is status-compatible but its primary semantic role requires human/content review.",
            field="evidence_class",
            actual=raw,
        )
'''
    source = replace_once(source, "def validate_canonical_path_and_filename(\n", evidence_functions + "\n\ndef validate_canonical_path_and_filename(\n", "evidence validation functions")

    source = replace_once(
        source,
        '''    validate_status(doc, findings, full=full)
    validate_date_fields(doc, findings, required=full)
''',
        '''    validate_status(doc, findings, full=full)
    validate_evidence_class(doc, findings)
    validate_date_fields(doc, findings, required=full)
''',
        "invoke evidence validation",
    )

    version_functions = r'''def concrete_creation_date(doc: Document) -> dt.date | None:
    return frontmatter_date(doc, "created")


def version_rule_context_date(doc: Document) -> dt.date | None:
    return frontmatter_date(doc, "revised") or frontmatter_date(doc, "created")


def validate_version_sequences(
    documents: list[Document],
    findings: list[Finding],
    aliases: AliasIndex,
) -> None:
    """Validate ART 0.3 / DEC-021 rules where lifecycle evidence is sufficient.

    Static inventory can validate initial versions for artifact lines created
    after the rule took effect and chronological monotonicity when concrete
    creation dates differ. Lifecycle-only ``revised`` changes are not treated
    as version-creation chronology. It intentionally does not invent diagnostics that
    require a content diff or an activation transaction record.
    """
    grouped: dict[str, list[Document]] = defaultdict(list)
    for doc in documents:
        if doc.scope_class != "managed" or doc.parse_error or not doc.artifact_id:
            continue
        if not doc.version or not VERSION_RE.fullmatch(doc.version):
            continue
        grouped[aliases.canonical(doc.artifact_id)].append(doc)

    for identity, docs in grouped.items():
        if not docs:
            continue
        line_created = [date for date in (frontmatter_date(doc, "created") for doc in docs) if date]
        first_numeric = min(docs, key=lambda item: version_key(item.version))
        if line_created and min(line_created) >= VERSION_RULE_EFFECTIVE_DATE:
            if first_numeric.document_type == "decision_record":
                if first_numeric.version not in {"0.1", "1.0"}:
                    add(
                        findings,
                        first_numeric,
                        "error",
                        "invalid_initial_decision_version",
                        "A new Decision Record line must start with version 0.1 or 1.0.",
                        field="version",
                        actual=first_numeric.version,
                        expected=["0.1", "1.0"],
                    )
            elif first_numeric.version != "0.1":
                add(
                    findings,
                    first_numeric,
                    "error",
                    "invalid_initial_artifact_version",
                    "A new non-Decision Managed Artifact line must start with version 0.1.",
                    field="version",
                    actual=first_numeric.version,
                    expected="0.1",
                )

        dated = [(date, doc) for doc in docs if (date := concrete_creation_date(doc))]
        by_date: dict[dt.date, list[Document]] = defaultdict(list)
        for date, doc in dated:
            by_date[date].append(doc)
        previous_max: tuple[int, ...] | None = None
        previous_date: dt.date | None = None
        for date in sorted(by_date):
            date_docs = by_date[date]
            if date >= VERSION_RULE_EFFECTIVE_DATE and previous_max is not None:
                for doc in date_docs:
                    if version_key(doc.version) <= previous_max:
                        add(
                            findings,
                            doc,
                            "error",
                            "non_monotonic_artifact_version_sequence",
                            "A later-created concrete version is not numerically higher than all earlier-created concrete versions.",
                            field="version",
                            actual={"version": doc.version, "revision_date": date.isoformat()},
                            expected={"greater_than": ".".join(str(part) for part in previous_max), "earlier_date": previous_date.isoformat() if previous_date else None},
                        )
            date_max = max((version_key(doc.version) for doc in date_docs), default=(-1,))
            if previous_max is None or date_max > previous_max:
                previous_max = date_max
                previous_date = date

        for doc in docs:
            context_date = version_rule_context_date(doc)
            if context_date and context_date < VERSION_RULE_EFFECTIVE_DATE:
                continue
            refs: list[tuple[str, str]] = []
            source_ref = scalar_text(doc.frontmatter.get("source_artifact"))
            if source_ref:
                refs.append(("source_artifact", source_ref))
            refs.extend(("supersedes", value) for value in as_list(doc.frontmatter.get("supersedes")) if isinstance(value, str))
            for field, ref in refs:
                canonical, ref_version, _ = split_reference(ref, aliases)
                if canonical != identity or not ref_version or not VERSION_RE.fullmatch(ref_version):
                    continue
                if version_key(doc.version) <= version_key(ref_version):
                    add(
                        findings,
                        doc,
                        "error",
                        "non_monotonic_artifact_version_sequence",
                        "A concrete successor/reference relation does not increase the artifact version numerically.",
                        field=field,
                        actual={"artifact_version": doc.version, "reference": ref},
                        expected=f"> {ref_version}",
                    )
'''
    source = replace_once(source, "def validate_global(\n", version_functions + "\n\ndef validate_global(\n", "version sequence functions")
    source = replace_once(
        source,
        '''    exact, active = build_resolution_indexes(documents, aliases)
''',
        '''    validate_version_sequences(documents, findings, aliases)

    exact, active = build_resolution_indexes(documents, aliases)
''',
        "invoke version sequence validation",
    )

    # Report and filenames.
    source = source.replace("Managed Artifact Validation Report — Revision 3.1", "Managed Artifact Validation Report — Revision 3.2")
    source = replace_once(
        source,
        '        f"- Validation basis: `{VALIDATION_BASIS[0]}` and `{VALIDATION_BASIS[1]}` (both draft)",',
        '        f"- Validation basis: `{VALIDATION_BASIS[0]}` and `{VALIDATION_BASIS[1]}` (active)",',
        "report validation basis",
    )
    source = source.replace("managed-artifact-validation-v3-1", "managed-artifact-validation-v3-2")
    source = source.replace("validation-report-v3-1.json", "validation-report-v3-2.json")
    source = source.replace("validation-report-v3-1.md", "validation-report-v3-2.md")

    source = replace_once(
        source,
        '''    type_counts = Counter(doc.document_type or "no_document_type" for doc in documents)
''',
        '''    type_counts = Counter(doc.document_type or "no_document_type" for doc in documents)
    current_managed_docs = [doc for doc in documents if doc.scope_class == "managed" and doc.validation_profile in FULL_CURRENT_PROFILES]
    evidence_counts = Counter(doc.evidence_class or "missing" for doc in current_managed_docs)
    required_evidence_missing = sum(1 for item in findings if item.code == "missing_evidence_class")
''',
        "report evidence counters",
    )
    source = replace_once(
        source,
        '''        f"- Alias mappings available: **{len(aliases.aliases)}**",
''',
        '''        f"- Alias mappings available: **{len(aliases.aliases)}**",
        f"- Current managed artifacts with evidence_class: **{sum(count for key, count in evidence_counts.items() if key != 'missing')}**",
        f"- Current managed artifacts without evidence_class: **{evidence_counts['missing']}**",
        f"- Required evidence_class missing errors: **{required_evidence_missing}**",
''',
        "report evidence lines",
    )
    source = replace_once(
        source,
        '''        "validation_basis": VALIDATION_BASIS,
''',
        '''        "validator_revision": VALIDATOR_REVISION,
        "validation_basis": VALIDATION_BASIS,
        "evidence_class_coverage": {
            "current_managed_total": len([doc for doc in documents if doc.scope_class == "managed" and doc.validation_profile in FULL_CURRENT_PROFILES]),
            "by_class": dict(Counter(doc.evidence_class or "missing" for doc in documents if doc.scope_class == "managed" and doc.validation_profile in FULL_CURRENT_PROFILES)),
            "required_missing_errors": sum(1 for item in findings if item.code == "missing_evidence_class"),
        },
''',
        "json evidence coverage",
    )

    # Self-test fixtures use ART 0.3 and auto-generate an appropriate syntactic
    # evidence class unless a caller edits/removes it for a negative fixture.
    managed_note_function = r'''def managed_note(
    *,
    document_type: str,
    id_field: str,
    artifact_id: str,
    title: str,
    version: str,
    status: str,
    canonical_path: str,
    extra: str = "",
    body: str = "# Fixture\n",
) -> str:
    approval = ""
    if status == "active":
        approval = (
            "approved_by: Owner\napproved_at: 2026-07-26\neffective_from: 2026-07-26\n"
        )
    if status == "active":
        evidence_class = "active_constraint"
    elif status in {"draft", "proposed"}:
        evidence_class = "design_candidate"
    else:
        evidence_class = "historical_evidence"
    return f"""---
document_type: {document_type}
{id_field}: {artifact_id}
title: {title}
version: \"{version}\"
status: {status}
evidence_class: {evidence_class}
owner: Owner
created: 2026-07-26
revised: 2026-07-26
{approval}{extra}canonical_path: {canonical_path}
---
{body}"""
'''
    source = replace_between(source, "def managed_note(\n", "def support_note", managed_note_function, "managed_note fixture helper")

    support_note_function = r'''def support_note(
    *,
    document_type: str,
    canonical_path: str,
    current: bool,
    extra: str,
) -> str:
    validated = "validated_against:\n  - CPKS-SPEC-ART@0.3\n" if current else ""
    return f"""---
document_type: {document_type}
preflight_id: TEST-PREFLIGHT
version: \"0.1\"
status: draft
{validated}{extra}canonical_path: {canonical_path}
---
# Fixture support
"""
'''
    source = replace_between(source, "def support_note(\n", "def run_filename_unit_tests", support_note_function, "support_note fixture helper")

    source = replace_once(
        source,
        '"CPKS-SPEC-ART@0.2 Managed Artifact Metadata and Validation Specification.md"',
        '"CPKS-SPEC-ART@0.3 Managed Artifact Metadata and Validation Specification.md"',
        "basis fixture path",
    )
    basis_version_anchor = '''                artifact_id="CPKS-SPEC-ART",
                title="Managed Artifact Metadata and Validation Specification",
                version="0.2",
                status="draft",
'''
    source = replace_once(
        source,
        basis_version_anchor,
        basis_version_anchor.replace('version="0.2"', 'version="0.3"'),
        "basis fixture version",
    )

    # Add positive compatibility/semantic-review coverage before negative guardrails.
    positive_insert = '''        # 8. Active baseline may remain verified_current_state after activation.\n        baseline_path = Path(\n            "Systems/cpKnowledgeSystem/Governance/System Control/TEST-BL Baseline.md"\n        )\n        baseline_content = managed_note(\n            document_type="baseline",\n            id_field="baseline_id",\n            artifact_id="TEST-BL",\n            title="Baseline",\n            version="0.1",\n            status="active",\n            canonical_path=baseline_path.as_posix(),\n        ).replace("evidence_class: active_constraint\\n", "evidence_class: verified_current_state\\n")\n        write_fixture(vault / baseline_path, baseline_content)\n\n        # 9. committed_target without a mechanically visible binding is valid\n        # syntactically but requires semantic review.\n        committed_path = Path(\n            "Development/cpKnowledgeSystem/Specifications/TEST-COMMIT@0.1 Committed.md"\n        )\n        committed_content = managed_note(\n            document_type="specification",\n            id_field="specification_id",\n            artifact_id="TEST-COMMIT",\n            title="Committed",\n            version="0.1",\n            status="draft",\n            canonical_path=committed_path.as_posix(),\n        ).replace("evidence_class: design_candidate\\n", "evidence_class: committed_target\\n")\n        write_fixture(vault / committed_path, committed_content)\n\n'''
    source = replace_once(
        source,
        "        documents, findings, aliases, acknowledgement_stats = validate_vault(vault)\n",
        positive_insert + "        documents, findings, aliases, acknowledgement_stats = validate_vault(vault)\n",
        "positive evidence fixtures",
    )
    source = replace_once(
        source,
        '''            "legacy_target_artifact_descriptor",
        ):
''',
        '''            "legacy_target_artifact_descriptor",
            "evidence_class_semantic_review_required",
        ):
''',
        "positive expected semantic diagnostic",
    )

    negative_insert = '''        # ART 0.3 evidence-class guardrails.\n        missing_evidence_path = Path(\n            "Systems/cpKnowledgeSystem/Governance/Policies/NEG-MISSING-EVIDENCE Policy.md"\n        )\n        missing_evidence = managed_note(\n            document_type="policy", id_field="policy_id", artifact_id="NEG-MISSING-EVIDENCE",\n            title="Policy", version="0.1", status="active", canonical_path=missing_evidence_path.as_posix(),\n        ).replace("evidence_class: active_constraint\\n", "")\n        write_fixture(negative / missing_evidence_path, missing_evidence)\n\n        invalid_evidence_path = Path(\n            "Systems/cpKnowledgeSystem/Governance/Policies/NEG-INVALID-EVIDENCE Policy.md"\n        )\n        invalid_evidence = managed_note(\n            document_type="policy", id_field="policy_id", artifact_id="NEG-INVALID-EVIDENCE",\n            title="Policy", version="0.1", status="active", canonical_path=invalid_evidence_path.as_posix(),\n        ).replace("evidence_class: active_constraint", "evidence_class: not_a_class")\n        write_fixture(negative / invalid_evidence_path, invalid_evidence)\n\n        mismatch_evidence_path = Path(\n            "Systems/cpKnowledgeSystem/Governance/Policies/NEG-MISMATCH-EVIDENCE Policy.md"\n        )\n        mismatch_evidence = managed_note(\n            document_type="policy", id_field="policy_id", artifact_id="NEG-MISMATCH-EVIDENCE",\n            title="Policy", version="0.1", status="active", canonical_path=mismatch_evidence_path.as_posix(),\n        ).replace("evidence_class: active_constraint", "evidence_class: design_candidate")\n        write_fixture(negative / mismatch_evidence_path, mismatch_evidence)\n\n        # Prospective initial-version rule for a new non-Decision line.\n        bad_initial_path = Path(\n            "Development/cpKnowledgeSystem/Specifications/NEG-INITIAL@0.2 Bad Initial.md"\n        )\n        bad_initial = managed_note(\n            document_type="specification", id_field="specification_id", artifact_id="NEG-INITIAL",\n            title="Bad Initial", version="0.2", status="draft", canonical_path=bad_initial_path.as_posix(),\n        ).replace("created: 2026-07-26", "created: 2026-08-01").replace("revised: 2026-07-26", "revised: 2026-08-01")\n        write_fixture(negative / bad_initial_path, bad_initial)\n\n        # Prospective initial-version rule for a new Decision line.\n        bad_decision_path = Path(\n            "Development/cpKnowledgeSystem/Governance/Draft Decisions/NEG-DEC@0.2 Bad Decision.md"\n        )\n        bad_decision = managed_note(\n            document_type="decision_record", id_field="decision_id", artifact_id="NEG-DEC",\n            title="Bad Decision", version="0.2", status="draft", canonical_path=bad_decision_path.as_posix(),\n        ).replace("created: 2026-07-26", "created: 2026-08-01").replace("revised: 2026-07-26", "revised: 2026-08-01")\n        write_fixture(negative / bad_decision_path, bad_decision)\n\n        # Chronological/numeric sequence conflict with a valid 0.1 initial version.\n        seq_01 = Path("Development/cpKnowledgeSystem/Specifications/Archive/NEG-SEQ@0.1 Sequence.md")\n        seq_03 = Path("Development/cpKnowledgeSystem/Specifications/NEG-SEQ@0.3 Sequence.md")\n        seq_02 = Path("Development/cpKnowledgeSystem/Specifications/Archive/NEG-SEQ@0.2 Sequence.md")\n        for path, version, status, created in (\n            (seq_01, "0.1", "withdrawn", "2026-08-01"),\n            (seq_03, "0.3", "draft", "2026-08-02"),\n            (seq_02, "0.2", "withdrawn", "2026-08-03"),\n        ):\n            content = managed_note(\n                document_type="specification", id_field="specification_id", artifact_id="NEG-SEQ",\n                title="Sequence", version=version, status=status, canonical_path=path.as_posix(),\n            ).replace("created: 2026-07-26", f"created: {created}").replace("revised: 2026-07-26", f"revised: {created}")\n            write_fixture(negative / path, content)\n\n'''
    source = replace_once(
        source,
        "        _, negative_findings, _, _ = validate_vault(negative)\n",
        negative_insert + "        _, negative_findings, _, _ = validate_vault(negative)\n",
        "negative ART 0.3 fixtures",
    )
    source = replace_once(
        source,
        '''            "validation_acknowledgement_not_allowed",
        ):
''',
        '''            "validation_acknowledgement_not_allowed",
            "missing_evidence_class",
            "invalid_evidence_class",
            "evidence_class_status_mismatch",
            "invalid_initial_artifact_version",
            "invalid_initial_decision_version",
            "non_monotonic_artifact_version_sequence",
        ):
''',
        "negative expected ART 0.3 diagnostics",
    )

    source = source.replace('print("Managed-artifact validator v3.1 self-test passed.")', 'print("Managed-artifact validator v3.2 self-test passed.")')
    source = source.replace('print("Managed-artifact validation v3.1 completed.")', 'print("Managed-artifact validation v3.2 completed.")')

    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/Users/cp/Developer/cpKnowledgeTools"))
    parser.add_argument("--check", action="store_true", help="Build, parse and self-test without changing repository files.")
    parser.add_argument("--force", action="store_true", help="Replace an existing v3.2 target after successful checks.")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    old_path = repo / OLD_REL
    new_path = repo / NEW_REL
    if not old_path.is_file():
        raise SystemExit(f"ERROR: expected source validator not found: {old_path}")
    if new_path.exists() and not args.force:
        raise SystemExit(f"ERROR: target already exists (use --force only after review): {new_path}")

    old_source = old_path.read_text(encoding="utf-8")
    new_source = upgrade(old_source)
    ast.parse(new_source, filename=str(NEW_REL))

    with tempfile.TemporaryDirectory(prefix="cpkt-validator-v3-2-upgrade-") as temp:
        temp_path = Path(temp) / NEW_REL.name
        temp_path.write_text(new_source, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(temp_path), "--self-test"],
            cwd=repo,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            sys.stderr.write(completed.stdout)
            sys.stderr.write(completed.stderr)
            raise SystemExit("ERROR: generated v3.2 validator failed embedded self-tests; repository was not changed.")
        print(completed.stdout.rstrip())

    if args.check:
        print("CHECK PASSED: v3.2 constructed, parsed and self-tested; repository unchanged.")
        return 0

    new_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_install = new_path.with_suffix(new_path.suffix + ".tmp")
    temporary_install.write_text(new_source, encoding="utf-8")
    shutil.copymode(old_path, temporary_install)
    temporary_install.replace(new_path)
    old_path.unlink()
    print(f"INSTALLED: {new_path}")
    print(f"REMOVED:   {old_path}")
    print("Next verification step: run v3.2 against the canonical cp-wiki vault with --strict-exit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
