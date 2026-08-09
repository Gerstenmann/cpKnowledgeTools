#!/usr/bin/env python3
"""
Read-only managed-artifact validator for cp-wiki — revision 3.2.

Validation basis:
- CPKS-SPEC-ART@0.3 (active)
- CPKS-SPEC-PROC@0.3 (active)
- CPKS-POL-GOV-AUTH@1.0
- CPKS-DEC-021@0.2
- CPKS-DEC-026@1.0

Revision 3.2 retains the existing validator capabilities and adds ART 0.3 support:
- acknowledgement metadata for reviewed historical and legacy findings;
- suppression of explicitly accepted warning/info codes only;
- continued enforcement of YAML, identity, path, duplicate and lifecycle errors;
- corrected handling of empty ``supersedes: []`` on withdrawn artifacts;
- separate current, historical, current-Development, closed-Development,
  current-support, legacy-support and unmanaged validation profiles;
- distributed ``former_ids`` alias support;
- structured ``target_artifact`` descriptor support;
- embedded self-tests for profiles, acknowledgements and guardrails;
- filename-normalization unit tests;
- complete ``evidence_class`` syntax and status-compatibility validation;
- prospective evidence-class requirement checks for current governance/architecture and new current artifacts;
- semantic review diagnostics where evidence role cannot be established mechanically;
- ART 0.3 initial-version and monotonic version-sequence checks where lifecycle evidence is sufficient;
- expanded current architecture, template and component lifecycle scan coverage.

The validator never modifies the Vault. Reports are written outside the Vault.

Canonical repository location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/validation/
  validate_cpwiki_managed_artifacts_v3_2.py

Usage:
  .venv/bin/python scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py
  .venv/bin/python scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py --self-test
  .venv/bin/python scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py --strict-exit
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import datetime as dt
import json
from pathlib import Path
import shutil
import re
import sys
import tempfile
from typing import Any, Iterable
import unicodedata

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required in the cpKnowledgeTools environment. "
        "Install it in that environment with: .venv/bin/python -m pip install PyYAML"
    ) from exc


VALIDATOR_REVISION = "3.2"
VALIDATION_BASIS = ["CPKS-SPEC-ART@0.3", "CPKS-SPEC-PROC@0.3"]
EVIDENCE_CLASS_EFFECTIVE_DATE = dt.date(2026, 7, 30)
VERSION_RULE_EFFECTIVE_DATE = dt.date(2026, 7, 27)
DEFAULT_VAULT = Path("/Users/cp/Documents/cp-wiki")
DEFAULT_REPORT_ROOT = Path(
    "/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/validation"
)

MANAGED_TYPES: dict[str, str] = {
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

SUPPORT_TYPES = {
    "decision_proposal",
    "change_proposal",
    "preflight",
    "review",
    "handover",
    "process_support",
    "checklist",
    "example",
    "report",
    "analysis",
    "index",
    "placeholder",
}

COMMON_STATUSES = {
    "draft",
    "proposed",
    "active",
    "superseded",
    "deprecated",
    "archived",
}
CLOSED_DEVELOPMENT_STATUSES = {"withdrawn", "rejected", "completed", "cancelled"}
ALL_RECOGNIZED_STATUSES = COMMON_STATUSES | CLOSED_DEVELOPMENT_STATUSES

TYPE_SPECIFIC_STATUSES: dict[str, set[str]] = {
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

STABLE_FIELDS = {
    "governed_by",
    "depends_on",
    "aligned_with",
    "related_decisions",
    "affected_artifacts",
    "parent_process",
    "invokes_processes",
    "belongs_to_process",
}
ACTIVE_TARGET_STABLE_FIELDS = {
    "governed_by",
    "depends_on",
    "aligned_with",
    "related_decisions",
    "parent_process",
    "invokes_processes",
    "belongs_to_process",
}
VERSIONED_LIST_FIELDS = {"implements_decisions", "validated_against", "supersedes"}
VERSIONED_SCALAR_FIELDS = {"source_artifact"}
MIXED_FIELDS = {"references"}
IMPACT_RELEVANT_TYPES = {"decision_proposal", "preflight", "work_package"}
ACTIVE_NORMATIVE_TYPES = {
    "baseline",
    "decision_record",
    "policy",
    "framework",
    "specification",
    "process",
    "template",
    "manual",
}

# Owner-approved mappings. They are a transitional bootstrap while the same
# mappings are materialized on current canonical artifacts via former_ids.
APPROVED_ALIAS_MAPPINGS = {
    "CPKS-POL-GOVERNANCE-AUTHORING": "CPKS-POL-GOV-AUTH",
    "CPKS-FWK-AI-WORKING": "CPKS-FWK-AIW",
    "CPKS-BASELINE": "CPKS-BL",
    "CPWIKI-VAULT-SPEC": "CPW-SPEC-VLT",
    "CPKS-SPEC-PROCESS-DESCRIPTION": "CPKS-SPEC-PROC",
}

ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
PROCESS_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-P[0-9]{2,3}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
VERSIONED_REF_RE = re.compile(
    r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)@([0-9]+\.[0-9]+(?:\.[0-9]+)?)$"
)
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

PROCESS_SECTIONS = [
    "## 1. Zweck",
    "## 2. Geltungsbereich",
    "## 3. Auslöser",
    "## 4. Voraussetzungen und Inputs",
    "## 5. Rollen und Verantwortlichkeiten",
    "## 6. Prozessablauf",
    "## 7. Entscheidungs- und Stop-Bedingungen",
    "## 8. Fehler- und Ausnahmebehandlung",
    "## 9. Outputs und Nachweise",
    "## 10. Abschlusskriterien",
    "## 11. Zugehörige Prozesse und Artefakte",
]

FULL_CURRENT_PROFILES = {
    "current_managed",
    "current_development_managed",
}
INTEGRITY_PROFILES = {
    "historical_managed",
    "closed_development_managed",
}

ACKNOWLEDGEMENT_FIELD = "validation_acknowledgement"
ACKNOWLEDGEMENT_DISPOSITION = "accepted_historical"
ACKNOWLEDGEMENT_ALLOWED_PROFILES = {
    "historical_managed",
    "closed_development_managed",
    "legacy_support",
}
ACKNOWLEDGEMENT_ALLOWED_FIELDS = {
    "disposition",
    "reviewed_by",
    "reviewed_at",
    "source_report_generated_at",
    "accepted_codes",
    "rationale",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str
    field: str | None = None
    artifact_id: str | None = None
    version: str | None = None
    actual: Any = None
    expected: Any = None
    line: int | None = None


@dataclass(frozen=True)
class AcknowledgementStats:
    acknowledged_documents: int
    suppressed_findings: int
    suppressed_by_code: dict[str, int]


@dataclass
class Document:
    path: Path
    relative_path: str
    scan_zone: str
    text: str
    raw_frontmatter: str | None
    body: str
    frontmatter: dict[str, Any]
    has_frontmatter: bool
    parse_error: str | None
    validation_profile: str = "unmanaged"

    @property
    def document_type(self) -> str | None:
        return scalar_text(self.frontmatter.get("document_type"))

    @property
    def scope_class(self) -> str:
        if self.document_type in MANAGED_TYPES:
            return "managed"
        if self.document_type in SUPPORT_TYPES:
            return "support"
        return "unmanaged"

    @property
    def id_field(self) -> str | None:
        return MANAGED_TYPES.get(self.document_type or "")

    @property
    def artifact_id(self) -> str | None:
        if self.id_field:
            return scalar_text(self.frontmatter.get(self.id_field))
        for field in (
            "preflight_id",
            "decision_id",
            "work_package_id",
            "review_id",
            "change_id",
            "proposal_id",
        ):
            if field in self.frontmatter:
                return scalar_text(self.frontmatter[field])
        return None

    @property
    def version(self) -> str | None:
        return scalar_text(self.frontmatter.get("version"))

    @property
    def status(self) -> str | None:
        return scalar_text(self.frontmatter.get("status"))

    @property
    def evidence_class(self) -> str | None:
        return scalar_text(self.frontmatter.get("evidence_class"))

    @property
    def is_current_profile(self) -> bool:
        return self.validation_profile in FULL_CURRENT_PROFILES | {"current_support"}

    @property
    def is_integrity_profile(self) -> bool:
        return self.validation_profile in INTEGRITY_PROFILES | {"legacy_support"}


@dataclass
class AliasIndex:
    aliases: dict[str, str]
    sources: dict[str, str]
    declarations: dict[str, list[str]]

    def canonical(self, value: str) -> str:
        return self.aliases.get(value, value)


class FrontmatterError(RuntimeError):
    pass


class SelfTestFailure(RuntimeError):
    pass


def scalar_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return None
    return str(value)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise FrontmatterError("YAML frontmatter is not closed with '---'.")


def parse_yaml_frontmatter(raw: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = ""
        if mark is not None:
            location = f" at line {mark.line + 2}, column {mark.column + 1}"
        problem = getattr(exc, "problem", None) or str(exc)
        raise FrontmatterError(f"Invalid YAML{location}: {problem}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise FrontmatterError("YAML frontmatter must be a top-level mapping.")
    return parsed


def is_work_package_development_path(relative: str) -> bool:
    """Return whether a path belongs to a scoped Development Work Package tree."""

    parts = relative.split("/")
    return (
        len(parts) >= 4
        and parts[0] == "Development"
        and parts[2] == "Work Packages"
    )


def scan_zone(relative: str) -> str:
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
    if is_work_package_development_path(relative):
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

def is_closed_path(relative: str) -> bool:
    return any(token in relative for token in ("/Archive/", "/History/"))


def support_is_current(doc: Document) -> bool:
    candidates: list[str] = []
    for field in ("validated_against", "validation_basis", "rule_basis"):
        candidates.extend(
            item
            for item in as_list(doc.frontmatter.get(field))
            if isinstance(item, str)
        )
    return "CPKS-SPEC-ART@0.3" in candidates


def assign_validation_profile(doc: Document) -> str:
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
    if (
        doc.scan_zone == "work_package_development"
        and doc.document_type == "work_package"
    ):
        # CPKS-SPEC-WP@0.1 §7.2: an active Work Package remains in its
        # Development context and uses the unversioned active filename.
        if is_closed_path(doc.relative_path):
            return "closed_development_managed"
        if doc.status == "active":
            return "current_managed"
        if doc.status in CLOSED_DEVELOPMENT_STATUSES:
            return "closed_development_managed"
        return "current_development_managed"
    if doc.scan_zone in development_zones:
        if doc.status in CLOSED_DEVELOPMENT_STATUSES or is_closed_path(
            doc.relative_path
        ):
            return "closed_development_managed"
        return "current_development_managed"
    return "unmanaged"


def iter_candidate_paths(vault: Path) -> Iterable[Path]:
    development_root = vault / "Development"
    work_package_roots = (
        [
            context / "Work Packages"
            for context in development_root.iterdir()
            if context.is_dir() and (context / "Work Packages").is_dir()
        ]
        if development_root.is_dir()
        else []
    )
    roots = [
        vault / "Systems/cpKnowledgeSystem/Governance",
        vault / "Systems/cpKnowledgeSystem/Architecture",
        vault / "Systems/cpKnowledgeTools/Architecture",
        vault / "Templates",
        vault / "Development/cpKnowledgeSystem/Governance",
        vault / "Development/cpKnowledgeSystem/Specifications",
        vault / "Development/cpKnowledgeSystem/Architecture",
        vault / "Development/cp-wiki Vault/Specifications",
        vault / "Development/cpKnowledgeTools",
        vault / "Processes",
        *work_package_roots,
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

def load_document(vault: Path, path: Path) -> Document:
    relative = path.relative_to(vault).as_posix()
    text = path.read_text(encoding="utf-8")
    zone = scan_zone(relative)
    try:
        raw, body = split_frontmatter(text)
        if raw is None:
            doc = Document(
                path=path,
                relative_path=relative,
                scan_zone=zone,
                text=text,
                raw_frontmatter=None,
                body=body,
                frontmatter={},
                has_frontmatter=False,
                parse_error=None,
            )
        else:
            doc = Document(
                path=path,
                relative_path=relative,
                scan_zone=zone,
                text=text,
                raw_frontmatter=raw,
                body=body,
                frontmatter=parse_yaml_frontmatter(raw),
                has_frontmatter=True,
                parse_error=None,
            )
    except FrontmatterError as exc:
        doc = Document(
            path=path,
            relative_path=relative,
            scan_zone=zone,
            text=text,
            raw_frontmatter=None,
            body="",
            frontmatter={},
            has_frontmatter=True,
            parse_error=str(exc),
        )
    doc.validation_profile = assign_validation_profile(doc)
    return doc


def add(
    findings: list[Finding],
    doc: Document,
    severity: str,
    code: str,
    message: str,
    *,
    field: str | None = None,
    actual: Any = None,
    expected: Any = None,
    line: int | None = None,
) -> None:
    findings.append(
        Finding(
            severity=severity,
            code=code,
            message=message,
            path=doc.relative_path,
            field=field,
            artifact_id=doc.artifact_id,
            version=doc.version,
            actual=actual,
            expected=expected,
            line=line,
        )
    )


def validate_acknowledgement(
    doc: Document,
    findings: list[Finding],
) -> set[str]:
    raw = doc.frontmatter.get(ACKNOWLEDGEMENT_FIELD)
    if raw is None:
        return set()

    if doc.validation_profile not in ACKNOWLEDGEMENT_ALLOWED_PROFILES:
        add(
            findings,
            doc,
            "error",
            "validation_acknowledgement_not_allowed",
            "Historical finding acknowledgements are allowed only for historical, closed-Development or legacy-support profiles.",
            field=ACKNOWLEDGEMENT_FIELD,
            actual=doc.validation_profile,
            expected=sorted(ACKNOWLEDGEMENT_ALLOWED_PROFILES),
        )
        return set()

    if not isinstance(raw, dict):
        add(
            findings,
            doc,
            "error",
            "invalid_validation_acknowledgement",
            "validation_acknowledgement must be a YAML mapping.",
            field=ACKNOWLEDGEMENT_FIELD,
            actual=raw,
        )
        return set()

    valid = True
    unknown = sorted(set(raw) - ACKNOWLEDGEMENT_ALLOWED_FIELDS)
    if unknown:
        add(
            findings,
            doc,
            "warning",
            "unknown_validation_acknowledgement_field",
            "validation_acknowledgement contains unknown fields.",
            field=ACKNOWLEDGEMENT_FIELD,
            actual=unknown,
        )

    disposition = scalar_text(raw.get("disposition"))
    if disposition != ACKNOWLEDGEMENT_DISPOSITION:
        valid = False
        add(
            findings,
            doc,
            "error",
            "invalid_validation_acknowledgement_disposition",
            "Historical acknowledgement requires disposition: accepted_historical.",
            field=f"{ACKNOWLEDGEMENT_FIELD}.disposition",
            actual=disposition,
            expected=ACKNOWLEDGEMENT_DISPOSITION,
        )

    reviewed_by = scalar_text(raw.get("reviewed_by"))
    if not reviewed_by:
        valid = False
        add(
            findings,
            doc,
            "error",
            "invalid_validation_acknowledgement",
            "Historical acknowledgement requires reviewed_by.",
            field=f"{ACKNOWLEDGEMENT_FIELD}.reviewed_by",
        )

    reviewed_at = scalar_text(raw.get("reviewed_at"))
    if not reviewed_at or not DATE_RE.fullmatch(reviewed_at):
        valid = False
        add(
            findings,
            doc,
            "error",
            "invalid_validation_acknowledgement",
            "Historical acknowledgement requires reviewed_at in YYYY-MM-DD format.",
            field=f"{ACKNOWLEDGEMENT_FIELD}.reviewed_at",
            actual=reviewed_at,
        )

    accepted_raw = raw.get("accepted_codes")
    if not isinstance(accepted_raw, list) or not accepted_raw:
        valid = False
        add(
            findings,
            doc,
            "error",
            "invalid_validation_acknowledgement",
            "Historical acknowledgement requires a non-empty accepted_codes list.",
            field=f"{ACKNOWLEDGEMENT_FIELD}.accepted_codes",
            actual=accepted_raw,
        )
        return set()

    accepted: set[str] = set()
    for code in accepted_raw:
        if not isinstance(code, str) or not code.strip():
            valid = False
            add(
                findings,
                doc,
                "error",
                "invalid_validation_acknowledgement",
                "accepted_codes entries must be non-empty strings.",
                field=f"{ACKNOWLEDGEMENT_FIELD}.accepted_codes",
                actual=code,
            )
            continue
        accepted.add(code.strip())

    if len(accepted) != len(accepted_raw):
        add(
            findings,
            doc,
            "warning",
            "duplicate_validation_acknowledgement_code",
            "accepted_codes contains duplicate entries.",
            field=f"{ACKNOWLEDGEMENT_FIELD}.accepted_codes",
            actual=accepted_raw,
        )

    return accepted if valid else set()


def apply_acknowledgements(
    documents: list[Document],
    findings: list[Finding],
) -> tuple[list[Finding], AcknowledgementStats]:
    accepted_by_path: dict[str, set[str]] = {}
    for doc in documents:
        accepted = validate_acknowledgement(doc, findings)
        if accepted:
            accepted_by_path[doc.relative_path] = accepted

    retained: list[Finding] = []
    suppressed = Counter()
    for finding in findings:
        accepted = accepted_by_path.get(finding.path, set())
        suppressible = (
            finding.severity in {"warning", "info"}
            and finding.code in accepted
            and "validation_acknowledgement" not in finding.code
        )
        if suppressible:
            suppressed[finding.code] += 1
            continue
        retained.append(finding)

    return retained, AcknowledgementStats(
        acknowledged_documents=len(accepted_by_path),
        suppressed_findings=sum(suppressed.values()),
        suppressed_by_code=dict(sorted(suppressed.items())),
    )


def version_key(value: str | None) -> tuple[int, ...]:
    if not value or not VERSION_RE.fullmatch(value):
        return (-1,)
    return tuple(int(part) for part in value.split("."))


def normalize_title_for_filename(title: str) -> str:
    value = unicodedata.normalize("NFC", title).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1F]', " - ", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.rstrip(". ")


def expected_filename(doc: Document) -> str | None:
    if not doc.artifact_id or not doc.version:
        return None
    title = scalar_text(doc.frontmatter.get("title"))
    if not title:
        return None
    normalized = normalize_title_for_filename(title)
    if doc.status == "active":
        return f"{doc.artifact_id} {normalized}.md"
    return f"{doc.artifact_id}@{doc.version} {normalized}.md"


def raw_field_is_quoted(doc: Document, field: str) -> bool:
    if doc.raw_frontmatter is None:
        return False
    match = re.search(
        rf"(?m)^{re.escape(field)}:\s*(.+?)\s*$",
        doc.raw_frontmatter,
    )
    if not match:
        return False
    raw = match.group(1).strip()
    return len(raw) >= 2 and raw[0] in {'"', "'"} and raw[-1] == raw[0]


def select_line_heads(documents: list[Document]) -> dict[str, Document]:
    grouped: dict[str, list[Document]] = defaultdict(list)
    for doc in documents:
        if doc.scope_class != "managed" or not doc.artifact_id or doc.parse_error:
            continue
        if doc.validation_profile not in FULL_CURRENT_PROFILES:
            continue
        grouped[doc.artifact_id].append(doc)

    heads: dict[str, Document] = {}
    for artifact_id, docs in grouped.items():
        active = [doc for doc in docs if doc.status == "active"]
        candidates = active if active else docs
        heads[artifact_id] = max(candidates, key=lambda doc: version_key(doc.version))
    return heads


def build_alias_index(
    documents: list[Document],
    findings: list[Finding],
) -> AliasIndex:
    heads = select_line_heads(documents)
    aliases: dict[str, str] = dict(APPROVED_ALIAS_MAPPINGS)
    sources: dict[str, str] = {
        alias: "approved_bootstrap" for alias in APPROVED_ALIAS_MAPPINGS
    }
    declarations: dict[str, list[str]] = defaultdict(list)

    actual_ids = {
        doc.artifact_id
        for doc in documents
        if doc.scope_class == "managed" and doc.artifact_id and not doc.parse_error
    }

    for artifact_id, doc in heads.items():
        raw = doc.frontmatter.get("former_ids")
        if raw is None:
            approved_for_line = [
                alias
                for alias, current in APPROVED_ALIAS_MAPPINGS.items()
                if current == artifact_id
            ]
            if approved_for_line:
                add(
                    findings,
                    doc,
                    "warning",
                    "approved_alias_not_materialized",
                    "Approved former IDs are not yet declared on the current canonical artifact.",
                    field="former_ids",
                    actual=None,
                    expected=approved_for_line,
                )
            continue
        if not isinstance(raw, list):
            add(
                findings,
                doc,
                "error",
                "invalid_former_ids_type",
                "former_ids must be a YAML list of stable IDs.",
                field="former_ids",
                actual=raw,
            )
            continue
        seen_local: set[str] = set()
        for value in raw:
            if not isinstance(value, str) or not ID_RE.fullmatch(value):
                add(
                    findings,
                    doc,
                    "error",
                    "invalid_former_id",
                    "former_ids entry must be a stable ID without version.",
                    field="former_ids",
                    actual=value,
                )
                continue
            if value == artifact_id:
                add(
                    findings,
                    doc,
                    "error",
                    "former_id_equals_current_id",
                    "former_ids must not repeat the current stable ID.",
                    field="former_ids",
                    actual=value,
                )
                continue
            if value in seen_local:
                add(
                    findings,
                    doc,
                    "error",
                    "duplicate_former_id",
                    "former_ids contains a duplicate entry.",
                    field="former_ids",
                    actual=value,
                )
                continue
            seen_local.add(value)
            declarations[value].append(artifact_id)
            if value in actual_ids and value != artifact_id:
                add(
                    findings,
                    doc,
                    "error",
                    "former_id_conflicts_with_current_artifact_id",
                    "former ID is also used as an actual managed-artifact identity.",
                    field="former_ids",
                    actual=value,
                )
            previous = aliases.get(value)
            if previous and previous != artifact_id:
                add(
                    findings,
                    doc,
                    "error",
                    "former_id_claimed_by_multiple_artifacts",
                    "Former ID resolves to more than one current artifact line.",
                    field="former_ids",
                    actual=value,
                    expected=[previous, artifact_id],
                )
                continue
            aliases[value] = artifact_id
            sources[value] = doc.relative_path

    for alias, claimed in declarations.items():
        if len(set(claimed)) > 1:
            for doc in documents:
                if doc.artifact_id in claimed and alias in as_list(
                    doc.frontmatter.get("former_ids")
                ):
                    add(
                        findings,
                        doc,
                        "error",
                        "former_id_claimed_by_multiple_artifacts",
                        "Former ID is declared by multiple current artifact lines.",
                        field="former_ids",
                        actual=alias,
                        expected=sorted(set(claimed)),
                    )

    return AliasIndex(aliases=aliases, sources=sources, declarations=dict(declarations))


def split_reference(value: str, aliases: AliasIndex) -> tuple[str, str | None, bool]:
    if "@" not in value:
        canonical = aliases.canonical(value)
        return canonical, None, canonical != value
    base, version = value.split("@", 1)
    canonical = aliases.canonical(base)
    return canonical, version, canonical != base


def legacy_reference_severity(doc: Document) -> str:
    if doc.validation_profile in {
        "historical_managed",
        "closed_development_managed",
        "legacy_support",
    }:
        return "info"
    return "error"


def validate_alias_use(
    doc: Document,
    findings: list[Finding],
    field: str,
    value: str,
    aliases: AliasIndex,
) -> None:
    base = value.split("@", 1)[0]
    canonical = aliases.canonical(base)
    if canonical == base:
        return
    severity = legacy_reference_severity(doc)
    code = (
        "legacy_artifact_id_resolved"
        if severity == "info"
        else "legacy_artifact_id_in_current_reference"
    )
    add(
        findings,
        doc,
        severity,
        code,
        "Former stable ID was resolved through the approved alias model.",
        field=field,
        actual=value,
        expected=value.replace(base, canonical, 1),
    )


def validate_stable_reference_field(
    doc: Document,
    findings: list[Finding],
    field: str,
    aliases: AliasIndex,
    *,
    strict: bool,
) -> None:
    for value in as_list(doc.frontmatter.get(field)):
        if not isinstance(value, str) or not value:
            add(
                findings,
                doc,
                "error" if strict else "warning",
                "invalid_reference_form",
                "Reference value must be a non-empty string.",
                field=field,
                actual=value,
            )
            continue
        validate_alias_use(doc, findings, field, value, aliases)
        canonical, version, _ = split_reference(value, aliases)
        if version is not None or not ID_RE.fullmatch(canonical):
            add(
                findings,
                doc,
                "error" if strict else "warning",
                "invalid_affected_artifact_reference"
                if field == "affected_artifacts"
                else "invalid_reference_form",
                "Stable relation must use an unversioned stable ID.",
                field=field,
                actual=value,
                expected="stable ID without @version",
            )


def validate_versioned_reference_value(
    doc: Document,
    findings: list[Finding],
    field: str,
    value: Any,
    aliases: AliasIndex,
    *,
    strict: bool,
) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value:
        add(
            findings,
            doc,
            "error" if strict else "warning",
            "invalid_reference_form",
            "Reference value must be a non-empty string.",
            field=field,
            actual=value,
        )
        return None
    validate_alias_use(doc, findings, field, value, aliases)
    canonical, version, _ = split_reference(value, aliases)
    if (
        version is None
        or not ID_RE.fullmatch(canonical)
        or not VERSION_RE.fullmatch(version)
    ):
        add(
            findings,
            doc,
            "error" if strict else "warning",
            "invalid_reference_form",
            "Version-bound relation must use ID@version.",
            field=field,
            actual=value,
            expected="STABLE-ID@major.minor",
        )
        return None
    return canonical, version


def validate_target_artifact(
    doc: Document,
    findings: list[Finding],
    aliases: AliasIndex,
    *,
    strict: bool,
) -> tuple[str, str, bool] | None:
    raw = doc.frontmatter.get("target_artifact")
    if raw is None:
        return None
    if isinstance(raw, str):
        parsed = validate_versioned_reference_value(
            doc, findings, "target_artifact", raw, aliases, strict=strict
        )
        if parsed:
            return parsed[0], parsed[1], False
        return None
    if not isinstance(raw, dict):
        add(
            findings,
            doc,
            "error" if strict else "warning",
            "invalid_target_artifact_descriptor",
            "target_artifact must be ID@version or a mapping descriptor.",
            field="target_artifact",
            actual=raw,
        )
        return None

    allowed = {"reference", "document_type", "target_status", "proposed_canonical_path"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        add(
            findings,
            doc,
            "warning",
            "unknown_target_artifact_descriptor_field",
            "target_artifact descriptor contains unknown fields.",
            field="target_artifact",
            actual=unknown,
        )

    reference = raw.get("reference")
    if reference is None:
        add(
            findings,
            doc,
            "warning"
            if not strict or doc.validation_profile == "legacy_support"
            else "error",
            "legacy_target_artifact_descriptor",
            "Structured target_artifact lacks the required reference field.",
            field="target_artifact",
            actual=raw,
            expected={"reference": "STABLE-ID@major.minor"},
        )
        return None
    parsed = validate_versioned_reference_value(
        doc, findings, "target_artifact.reference", reference, aliases, strict=strict
    )
    if not parsed:
        return None

    document_type = raw.get("document_type")
    if document_type is not None and (
        not isinstance(document_type, str)
        or document_type not in (set(MANAGED_TYPES) | SUPPORT_TYPES)
    ):
        add(
            findings,
            doc,
            "error" if strict else "warning",
            "invalid_target_artifact_descriptor",
            "target_artifact.document_type is not recognized.",
            field="target_artifact.document_type",
            actual=document_type,
        )

    target_status = raw.get("target_status")
    if target_status is not None and (
        not isinstance(target_status, str)
        or target_status not in ALL_RECOGNIZED_STATUSES
    ):
        add(
            findings,
            doc,
            "error" if strict else "warning",
            "invalid_target_artifact_descriptor",
            "target_artifact.target_status is not a recognized status.",
            field="target_artifact.target_status",
            actual=target_status,
        )

    proposed_path = raw.get("proposed_canonical_path")
    if proposed_path is not None:
        valid = (
            isinstance(proposed_path, str)
            and proposed_path
            and not proposed_path.startswith("/")
            and proposed_path.endswith(".md")
            and "\\" not in proposed_path
        )
        if not valid:
            add(
                findings,
                doc,
                "error" if strict else "warning",
                "invalid_target_artifact_descriptor",
                "proposed_canonical_path must be a Vault-relative POSIX Markdown path.",
                field="target_artifact.proposed_canonical_path",
                actual=proposed_path,
            )
    return parsed[0], parsed[1], True


def validate_mixed_references(
    doc: Document,
    findings: list[Finding],
    aliases: AliasIndex,
    *,
    strict: bool,
) -> None:
    for value in as_list(doc.frontmatter.get("references")):
        if not isinstance(value, str) or not value:
            add(
                findings,
                doc,
                "error" if strict else "warning",
                "invalid_reference_form",
                "references must contain non-empty strings.",
                field="references",
                actual=value,
            )
            continue
        validate_alias_use(doc, findings, "references", value, aliases)
        canonical, version, _ = split_reference(value, aliases)
        if version is None:
            valid = bool(ID_RE.fullmatch(canonical))
        else:
            valid = bool(ID_RE.fullmatch(canonical) and VERSION_RE.fullmatch(version))
        if not valid:
            add(
                findings,
                doc,
                "warning",
                "unresolved_external_or_legacy_reference_form",
                "references entry is outside managed-artifact reference syntax.",
                field="references",
                actual=value,
            )


def validate_date_fields(
    doc: Document, findings: list[Finding], *, required: bool
) -> None:
    for field in ("created", "revised"):
        if required and is_empty(doc.frontmatter.get(field)):
            add(
                findings,
                doc,
                "error",
                "missing_required_field",
                f"Required field {field!r} is missing.",
                field=field,
            )
    for field in ("created", "revised", "approved_at", "effective_from"):
        if field not in doc.frontmatter or is_empty(doc.frontmatter.get(field)):
            continue
        value = scalar_text(doc.frontmatter[field])
        if value and not DATE_RE.fullmatch(value):
            add(
                findings,
                doc,
                "error",
                "invalid_date",
                "Date must use YYYY-MM-DD.",
                field=field,
                actual=value,
            )
    created = scalar_text(doc.frontmatter.get("created"))
    revised = scalar_text(doc.frontmatter.get("revised"))
    if (
        created
        and revised
        and DATE_RE.fullmatch(created)
        and DATE_RE.fullmatch(revised)
    ):
        if revised < created:
            add(
                findings,
                doc,
                "error",
                "revised_before_created",
                "revised date is earlier than created date.",
                field="revised",
                actual=revised,
                expected=f">= {created}",
            )


def validate_identity_and_version(
    doc: Document,
    findings: list[Finding],
    *,
    full: bool,
) -> None:
    required = [
        "document_type",
        doc.id_field,
        "title",
        "version",
        "status",
    ]
    if full:
        required.extend(["owner", "created", "revised", "canonical_path"])
    for field in required:
        if field and is_empty(doc.frontmatter.get(field)):
            add(
                findings,
                doc,
                "error",
                "missing_required_field",
                f"Required field {field!r} is missing.",
                field=field,
            )

    artifact_id = doc.artifact_id
    if artifact_id and not ID_RE.fullmatch(artifact_id):
        add(
            findings,
            doc,
            "error",
            "invalid_artifact_id",
            "Stable artifact ID has invalid syntax.",
            field=doc.id_field,
            actual=artifact_id,
        )
    if artifact_id and len(artifact_id) > 32:
        add(
            findings,
            doc,
            "error" if full else "info",
            "artifact_id_too_long" if full else "legacy_artifact_id",
            "Stable artifact ID exceeds 32 characters."
            if full
            else "Historical stable artifact ID exceeds the current recommended length and is preserved as legacy identity.",
            field=doc.id_field,
            actual=len(artifact_id),
            expected="<= 32" if full else "preserve unless a controlled migration is authorized",
        )
    if (
        doc.document_type == "process"
        and artifact_id
        and not PROCESS_ID_RE.fullmatch(artifact_id)
    ):
        add(
            findings,
            doc,
            "error",
            "invalid_process_id",
            "Process ID must match <DOMAIN>-P<2-3 digits>.",
            field="process_id",
            actual=artifact_id,
        )

    if doc.version:
        if not VERSION_RE.fullmatch(doc.version):
            add(
                findings,
                doc,
                "error",
                "invalid_version",
                "version must use major.minor or major.minor.patch.",
                field="version",
                actual=doc.version,
            )
        if not isinstance(
            doc.frontmatter.get("version"), str
        ) or not raw_field_is_quoted(doc, "version"):
            add(
                findings,
                doc,
                "error",
                "version_must_be_yaml_string",
                "version must be quoted and stored as a YAML string.",
                field="version",
                actual=doc.frontmatter.get("version"),
            )


def validate_status(doc: Document, findings: list[Finding], *, full: bool) -> None:
    status = doc.status
    if not status:
        return
    allowed = TYPE_SPECIFIC_STATUSES.get(doc.document_type or "", COMMON_STATUSES)
    if status not in allowed:
        severity = "error" if full else "warning"
        add(
            findings,
            doc,
            severity,
            "invalid_status_for_document_type",
            "Status is not allowed for this document type.",
            field="status",
            actual=status,
            expected=sorted(allowed),
        )
    supersedes = as_list(doc.frontmatter.get("supersedes"))
    if status == "withdrawn" and supersedes:
        add(
            findings,
            doc,
            "error" if full else "warning",
            "withdrawn_artifact_has_supersedes",
            "A never-active withdrawn artifact must not supersede another version.",
            field="supersedes",
            actual=doc.frontmatter.get("supersedes"),
        )


def status_group(status: str | None) -> str | None:
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


def validate_canonical_path_and_filename(
    doc: Document,
    findings: list[Finding],
    *,
    check_filename: bool,
) -> None:
    canonical_path = scalar_text(doc.frontmatter.get("canonical_path"))
    if canonical_path and unicodedata.normalize("NFC", canonical_path) != unicodedata.normalize("NFC", doc.relative_path):
        add(
            findings,
            doc,
            "error",
            "canonical_path_mismatch",
            "canonical_path does not match the actual Vault-relative path.",
            field="canonical_path",
            actual=canonical_path,
            expected=doc.relative_path,
        )
    if check_filename:
        expected = expected_filename(doc)
        actual = Path(doc.relative_path).name
        if expected and unicodedata.normalize("NFC", expected) != unicodedata.normalize("NFC", actual):
            add(
                findings,
                doc,
                "error",
                "active_filename_mismatch"
                if doc.status == "active"
                else "versioned_filename_mismatch",
                "Filename does not match ID, version, status and normalized title.",
                actual=actual,
                expected=expected,
            )


def validate_lifecycle(doc: Document, findings: list[Finding]) -> None:
    status = doc.status
    profile = doc.validation_profile
    if status == "active" and profile != "current_managed":
        add(
            findings,
            doc,
            "error",
            "active_artifact_outside_active_zone",
            "Active managed artifact is outside an active canonical zone.",
            actual=profile,
        )
    if (
        profile == "current_managed"
        and doc.scan_zone == "active_processes"
        and doc.document_type == "process"
        and status != "active"
    ):
        add(
            findings,
            doc,
            "error",
            "inactive_process_in_processes",
            "A managed process under Processes/ must be active.",
            field="status",
            actual=status,
            expected="active",
        )
    if profile == "current_managed" and status in {"draft", "proposed", "withdrawn"}:
        add(
            findings,
            doc,
            "error",
            "inactive_artifact_in_active_zone",
            "Inactive artifact is located in an active canonical zone.",
            field="status",
            actual=status,
        )
    if profile == "historical_managed" and status == "active":
        add(
            findings,
            doc,
            "error",
            "active_artifact_in_history_or_archive",
            "Active artifact is located in history or archive.",
        )
    if profile == "closed_development_managed" and status in {
        "active",
        "draft",
        "proposed",
    }:
        add(
            findings,
            doc,
            "error",
            "closed_development_status_not_terminal",
            "Closed Development artifact requires a terminal non-active status.",
            field="status",
            actual=status,
            expected=sorted(CLOSED_DEVELOPMENT_STATUSES | {"archived"}),
        )
    if (
        profile == "current_development_managed"
        and status in CLOSED_DEVELOPMENT_STATUSES
    ):
        add(
            findings,
            doc,
            "error",
            "closed_development_artifact_outside_history",
            "Closed Development artifact is not in a closed Development zone.",
            field="status",
            actual=status,
        )


def validate_process(doc: Document, findings: list[Finding], *, full: bool) -> None:
    if full and is_empty(doc.frontmatter.get("process_domain")):
        add(
            findings,
            doc,
            "error",
            "missing_process_domain",
            "Process requires process_domain.",
            field="process_domain",
        )
    if full:
        for section in PROCESS_SECTIONS:
            if section not in doc.body:
                add(
                    findings,
                    doc,
                    "error",
                    "missing_process_section",
                    f"Required process section is missing: {section}",
                    expected=section,
                )
    for field in ("parent_process", "belongs_to_process"):
        if field in doc.frontmatter and isinstance(doc.frontmatter[field], list):
            add(
                findings,
                doc,
                "error" if full else "warning",
                "invalid_reference_form",
                f"{field} must be a scalar stable process ID.",
                field=field,
                actual=doc.frontmatter[field],
            )


def validate_managed_document(
    doc: Document,
    findings: list[Finding],
    aliases: AliasIndex,
) -> None:
    full = doc.validation_profile in FULL_CURRENT_PROFILES
    validate_identity_and_version(doc, findings, full=full)
    validate_status(doc, findings, full=full)
    validate_evidence_class(doc, findings)
    validate_date_fields(doc, findings, required=full)
    validate_canonical_path_and_filename(doc, findings, check_filename=full)
    validate_lifecycle(doc, findings)

    if doc.status == "active":
        for field in ("approved_by", "approved_at", "effective_from"):
            if is_empty(doc.frontmatter.get(field)):
                add(
                    findings,
                    doc,
                    "error",
                    "missing_approval_metadata",
                    f"Active artifact requires {field!r}.",
                    field=field,
                )

    strict_refs = full
    for field in STABLE_FIELDS:
        if field in doc.frontmatter:
            validate_stable_reference_field(
                doc, findings, field, aliases, strict=strict_refs
            )
    for field in VERSIONED_LIST_FIELDS:
        if field in doc.frontmatter:
            for value in as_list(doc.frontmatter.get(field)):
                validate_versioned_reference_value(
                    doc, findings, field, value, aliases, strict=strict_refs
                )
    for field in VERSIONED_SCALAR_FIELDS:
        if field in doc.frontmatter:
            validate_versioned_reference_value(
                doc,
                findings,
                field,
                doc.frontmatter.get(field),
                aliases,
                strict=strict_refs,
            )
    if "target_artifact" in doc.frontmatter:
        validate_target_artifact(doc, findings, aliases, strict=strict_refs)
    if "references" in doc.frontmatter:
        validate_mixed_references(doc, findings, aliases, strict=strict_refs)

    if (
        doc.document_type in ACTIVE_NORMATIVE_TYPES
        and doc.status == "active"
        and "affected_artifacts" in doc.frontmatter
    ):
        add(
            findings,
            doc,
            "error",
            "affected_artifacts_on_active_normative_artifact",
            "Active normative artifact must not retain affected_artifacts.",
            field="affected_artifacts",
        )

    if doc.document_type == "process":
        validate_process(doc, findings, full=full)


def validate_support_document(
    doc: Document,
    findings: list[Finding],
    aliases: AliasIndex,
) -> None:
    strict = doc.validation_profile == "current_support"
    canonical_path = scalar_text(doc.frontmatter.get("canonical_path"))
    if canonical_path and unicodedata.normalize("NFC", canonical_path) != unicodedata.normalize("NFC", doc.relative_path):
        add(
            findings,
            doc,
            "error" if strict else "warning",
            "canonical_path_mismatch",
            "Support document canonical_path does not match its actual path.",
            field="canonical_path",
            actual=canonical_path,
            expected=doc.relative_path,
        )

    if doc.document_type in IMPACT_RELEVANT_TYPES:
        if "affected_artifacts" not in doc.frontmatter:
            add(
                findings,
                doc,
                "error" if strict else "warning",
                "missing_affected_artifacts"
                if strict
                else "affected_artifacts_missing_on_legacy_change_artifact",
                "Current change artifact requires affected_artifacts."
                if strict
                else "Legacy change artifact predates the current impact rule.",
                field="affected_artifacts",
            )
        else:
            validate_stable_reference_field(
                doc, findings, "affected_artifacts", aliases, strict=strict
            )

    for field in STABLE_FIELDS - {"affected_artifacts"}:
        if field in doc.frontmatter:
            validate_stable_reference_field(
                doc, findings, field, aliases, strict=strict
            )
    for field in VERSIONED_LIST_FIELDS:
        if field in doc.frontmatter:
            for value in as_list(doc.frontmatter.get(field)):
                validate_versioned_reference_value(
                    doc, findings, field, value, aliases, strict=strict
                )
    for field in VERSIONED_SCALAR_FIELDS:
        if field in doc.frontmatter:
            validate_versioned_reference_value(
                doc, findings, field, doc.frontmatter.get(field), aliases, strict=strict
            )
    if "target_artifact" in doc.frontmatter:
        validate_target_artifact(doc, findings, aliases, strict=strict)
    if "references" in doc.frontmatter:
        validate_mixed_references(doc, findings, aliases, strict=strict)


def validate_document(
    doc: Document,
    findings: list[Finding],
    aliases: AliasIndex,
) -> None:
    if doc.parse_error:
        add(
            findings,
            doc,
            "error",
            "invalid_yaml_frontmatter",
            doc.parse_error,
        )
        return
    if not doc.has_frontmatter:
        return
    if doc.scope_class == "unmanaged":
        if doc.document_type:
            add(
                findings,
                doc,
                "info",
                "unmanaged_document_type",
                "document_type is outside the current managed/support model.",
                field="document_type",
                actual=doc.document_type,
            )
        return
    if doc.scope_class == "support":
        validate_support_document(doc, findings, aliases)
        return
    validate_managed_document(doc, findings, aliases)


def canonical_identity(doc: Document, aliases: AliasIndex) -> str | None:
    if not doc.artifact_id:
        return None
    return aliases.canonical(doc.artifact_id)


def build_resolution_indexes(
    documents: list[Document],
    aliases: AliasIndex,
) -> tuple[dict[tuple[str, str], list[Document]], dict[str, list[Document]]]:
    exact: dict[tuple[str, str], list[Document]] = defaultdict(list)
    active: dict[str, list[Document]] = defaultdict(list)
    for doc in documents:
        if doc.scope_class != "managed" or doc.parse_error:
            continue
        identity = canonical_identity(doc, aliases)
        if identity and doc.version:
            exact[(identity, doc.version)].append(doc)
        if identity and doc.status == "active":
            active[identity].append(doc)
    return exact, active


def resolve_stable_references(
    doc: Document,
    findings: list[Finding],
    aliases: AliasIndex,
    active: dict[str, list[Document]],
) -> None:
    if doc.validation_profile not in FULL_CURRENT_PROFILES | {"current_support"}:
        return
    for field in ACTIVE_TARGET_STABLE_FIELDS:
        for value in as_list(doc.frontmatter.get(field)):
            if not isinstance(value, str) or "@" in value:
                continue
            identity = aliases.canonical(value)
            targets = active.get(identity, [])
            if not targets:
                add(
                    findings,
                    doc,
                    "error",
                    "no_active_reference_target",
                    "Stable relation does not resolve to an active target.",
                    field=field,
                    actual=value,
                )
            elif len(targets) > 1:
                add(
                    findings,
                    doc,
                    "error",
                    "multiple_active_reference_targets",
                    "Stable relation resolves to multiple active targets.",
                    field=field,
                    actual=value,
                    expected=[target.relative_path for target in targets],
                )


def resolve_versioned_references(
    doc: Document,
    findings: list[Finding],
    aliases: AliasIndex,
    exact: dict[tuple[str, str], list[Document]],
) -> None:
    if doc.validation_profile not in FULL_CURRENT_PROFILES | {"current_support"}:
        return

    def resolve(field: str, value: Any, *, allow_planned: bool = False) -> None:
        if not isinstance(value, str):
            return
        identity, version, _ = split_reference(value, aliases)
        if version is None or not VERSION_RE.fullmatch(version):
            return
        targets = exact.get((identity, version), [])
        if not targets:
            add(
                findings,
                doc,
                "info" if allow_planned else "error",
                "planned_target_not_materialized"
                if allow_planned
                else "unresolved_versioned_reference",
                "Planned target version is not materialized yet."
                if allow_planned
                else "Version-bound reference does not resolve.",
                field=field,
                actual=value,
            )
        elif len(targets) > 1:
            add(
                findings,
                doc,
                "error",
                "parallel_canonical_version",
                "Version-bound relation resolves to multiple managed files.",
                field=field,
                actual=value,
                expected=[target.relative_path for target in targets],
            )

    for field in VERSIONED_LIST_FIELDS:
        for value in as_list(doc.frontmatter.get(field)):
            resolve(field, value)
    for field in VERSIONED_SCALAR_FIELDS:
        if field in doc.frontmatter:
            resolve(field, doc.frontmatter.get(field))
    if "target_artifact" in doc.frontmatter:
        raw = doc.frontmatter["target_artifact"]
        if isinstance(raw, str):
            resolve("target_artifact", raw, allow_planned=False)
        elif isinstance(raw, dict) and isinstance(raw.get("reference"), str):
            resolve("target_artifact.reference", raw["reference"], allow_planned=True)
    for value in as_list(doc.frontmatter.get("references")):
        if isinstance(value, str) and "@" in value:
            identity, version, _ = split_reference(value, aliases)
            if version and not exact.get((identity, version)):
                add(
                    findings,
                    doc,
                    "info",
                    "reference_not_in_representative_managed_scan",
                    "Versioned references entry does not resolve in this configured scan.",
                    field="references",
                    actual=value,
                )


def concrete_creation_date(doc: Document) -> dt.date | None:
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


def validate_global(
    documents: list[Document],
    findings: list[Finding],
    aliases: AliasIndex,
) -> None:
    managed = [
        doc for doc in documents if doc.scope_class == "managed" and not doc.parse_error
    ]
    by_identity_version: dict[tuple[str, str], list[Document]] = defaultdict(list)
    by_active_identity: dict[str, list[Document]] = defaultdict(list)
    by_canonical_path: dict[str, list[Document]] = defaultdict(list)

    for doc in managed:
        identity = canonical_identity(doc, aliases)
        if identity and doc.version:
            by_identity_version[(identity, doc.version)].append(doc)
        if identity and doc.status == "active":
            by_active_identity[identity].append(doc)
        canonical_path = scalar_text(doc.frontmatter.get("canonical_path"))
        if canonical_path:
            by_canonical_path[unicodedata.normalize("NFC", canonical_path)].append(doc)

    for (identity, version), docs in by_identity_version.items():
        if len(docs) > 1:
            for doc in docs:
                add(
                    findings,
                    doc,
                    "error",
                    "duplicate_stable_id_and_version",
                    "Multiple managed files share the same stable ID and version.",
                    actual=[item.relative_path for item in docs],
                    expected=f"one canonical file for {identity}@{version}",
                )
    for identity, docs in by_active_identity.items():
        if len(docs) > 1:
            for doc in docs:
                add(
                    findings,
                    doc,
                    "error",
                    "multiple_active_versions",
                    "Multiple active artifacts share the same stable ID.",
                    actual=[item.relative_path for item in docs],
                )
    for path, docs in by_canonical_path.items():
        if len(docs) > 1:
            for doc in docs:
                add(
                    findings,
                    doc,
                    "error",
                    "duplicate_canonical_path",
                    "Multiple documents claim the same canonical_path.",
                    field="canonical_path",
                    actual=path,
                )

    validate_version_sequences(documents, findings, aliases)

    exact, active = build_resolution_indexes(documents, aliases)
    for doc in documents:
        if doc.parse_error or doc.scope_class not in {"managed", "support"}:
            continue
        resolve_stable_references(doc, findings, aliases, active)
        resolve_versioned_references(doc, findings, aliases, exact)

    # A former ID may only resolve to versions that actually exist on the
    # canonical artifact line. Report only when a historical/current reference
    # uses an alias and its requested version cannot be found.
    for doc in documents:
        if doc.parse_error or not doc.has_frontmatter:
            continue
        for field, raw in doc.frontmatter.items():
            values: list[Any]
            if field == "target_artifact" and isinstance(raw, dict):
                values = [raw.get("reference")]
            else:
                values = as_list(raw)
            for value in values:
                if not isinstance(value, str) or "@" not in value:
                    continue
                base, version = value.split("@", 1)
                canonical = aliases.canonical(base)
                if canonical == base or not VERSION_RE.fullmatch(version):
                    continue
                if not exact.get((canonical, version)):
                    severity = "error" if doc.is_current_profile else "warning"
                    add(
                        findings,
                        doc,
                        severity,
                        "alias_version_target_missing",
                        "Alias resolves to an artifact line, but the referenced version is missing.",
                        field=field,
                        actual=value,
                        expected=f"{canonical}@{version}",
                    )


def validate_vault(
    vault: Path,
) -> tuple[list[Document], list[Finding], AliasIndex, AcknowledgementStats]:
    documents = [load_document(vault, path) for path in iter_candidate_paths(vault)]
    findings: list[Finding] = []
    aliases = build_alias_index(documents, findings)
    for document in documents:
        validate_document(document, findings, aliases)
    validate_global(documents, findings, aliases)
    findings, acknowledgement_stats = apply_acknowledgements(documents, findings)
    return documents, findings, aliases, acknowledgement_stats


def markdown_escape(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(
    vault: Path,
    documents: list[Document],
    findings: list[Finding],
    aliases: AliasIndex,
    acknowledgement_stats: AcknowledgementStats,
    generated_at: str,
) -> str:
    severity_counts = Counter(finding.severity for finding in findings)
    profile_counts = Counter(doc.validation_profile for doc in documents)
    scope_counts = Counter(doc.scope_class for doc in documents)
    type_counts = Counter(doc.document_type or "no_document_type" for doc in documents)
    current_managed_docs = [doc for doc in documents if doc.scope_class == "managed" and doc.validation_profile in FULL_CURRENT_PROFILES]
    evidence_counts = Counter(doc.evidence_class or "missing" for doc in current_managed_docs)
    required_evidence_missing = sum(1 for item in findings if item.code == "missing_evidence_class")
    unmanaged_process_files = [
        doc
        for doc in documents
        if doc.scan_zone == "active_processes" and doc.scope_class == "unmanaged"
    ]
    active_processes = [
        doc
        for doc in documents
        if doc.document_type == "process" and doc.status == "active"
    ]

    lines = [
        "# Managed Artifact Validation Report — Revision 3.2",
        "",
        f"- Generated: `{generated_at}`",
        f"- Vault: `{vault}`",
        f"- Validation basis: `{VALIDATION_BASIS[0]}` and `{VALIDATION_BASIS[1]}` (active)",
        "- Mode: read-only",
        f"- Files inventoried: **{len(documents)}**",
        f"- Managed artifacts: **{scope_counts['managed']}**",
        f"- Support documents: **{scope_counts['support']}**",
        f"- Unmanaged files: **{scope_counts['unmanaged']}**",
        f"- Active managed processes: **{len(active_processes)}**",
        f"- Unmanaged files under `Processes/`: **{len(unmanaged_process_files)}**",
        f"- Alias mappings available: **{len(aliases.aliases)}**",
        f"- Current managed artifacts with evidence_class: **{sum(count for key, count in evidence_counts.items() if key != 'missing')}**",
        f"- Current managed artifacts without evidence_class: **{evidence_counts['missing']}**",
        f"- Required evidence_class missing errors: **{required_evidence_missing}**",
        f"- Historical acknowledgement records: **{acknowledgement_stats.acknowledged_documents}**",
        f"- Acknowledged findings suppressed: **{acknowledgement_stats.suppressed_findings}**",
        f"- Errors: **{severity_counts['error']}**",
        f"- Warnings: **{severity_counts['warning']}**",
        f"- Info: **{severity_counts['info']}**",
        "",
        "> Unmanaged files under `Processes/` are inventory only. They are not process-conformance errors.",
        "",
        "## 1. Executive assessment",
        "",
    ]
    if severity_counts["error"]:
        lines.append("The configured inventory contains blocking findings.")
    else:
        lines.append("No blocking errors were found in the configured inventory.")

    lines.extend(
        [
            "",
            "## 2. Validation profiles",
            "",
            "| Profile | Files | Treatment |",
            "|---|---:|---|",
        ]
    )
    treatments = {
        "current_managed": "full current conformance",
        "historical_managed": "historical integrity and lifecycle resolution",
        "current_development_managed": "full current Development conformance",
        "closed_development_managed": "closed Development integrity",
        "current_support": "current cross-cutting support rules",
        "legacy_support": "legacy support integrity and migration diagnostics",
        "unmanaged": "inventory only",
    }
    for profile, count in sorted(profile_counts.items()):
        lines.append(f"| `{profile}` | {count} | {treatments.get(profile, '')} |")

    lines.extend(["", "## 3. Document types", "", "| Type | Files |", "|---|---:|"])
    for document_type, count in sorted(type_counts.items()):
        lines.append(f"| `{document_type}` | {count} |")

    lines.extend(["", "## 4. Alias model", ""])
    lines.append(
        "Approved and distributed former IDs are resolved without rewriting historical files."
    )
    lines.extend(["", "| Former ID | Current ID | Source |", "|---|---|---|"])
    for alias, current in sorted(aliases.aliases.items()):
        lines.append(
            f"| `{alias}` | `{current}` | `{aliases.sources.get(alias, '')}` |"
        )

    lines.extend(["", "## 5. Historical acknowledgements", ""])
    if acknowledgement_stats.acknowledged_documents:
        lines.append(
            "Reviewed historical and legacy findings were suppressed only when their exact codes were listed in valid "
            "`validation_acknowledgement.accepted_codes` metadata."
        )
        lines.extend(["", "| Code | Suppressed |", "|---|---:|"])
        for code, count in acknowledgement_stats.suppressed_by_code.items():
            lines.append(f"| `{code}` | {count} |")
    else:
        lines.append("No valid historical acknowledgement metadata was found.")

    lines.extend(
        [
            "",
            "## 6. Finding summary",
            "",
            "| Severity | Code | Count |",
            "|---|---|---:|",
        ]
    )
    ordering = {"error": 0, "warning": 1, "info": 2}
    summary = Counter((finding.severity, finding.code) for finding in findings)
    for (severity, code), count in sorted(
        summary.items(),
        key=lambda item: (ordering.get(item[0][0], 9), -item[1], item[0][1]),
    ):
        lines.append(f"| `{severity}` | `{code}` | {count} |")

    lines.extend(["", "## 6. Detailed findings", ""])
    if not findings:
        lines.append("No findings.")
    else:
        lines.extend(
            [
                "| Severity | Code | Profile | Path | Field | Message | Actual | Expected |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        by_path = {doc.relative_path: doc.validation_profile for doc in documents}
        for finding in sorted(
            findings,
            key=lambda item: (
                ordering.get(item.severity, 9),
                item.path,
                item.code,
                item.field or "",
            ),
        ):
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{finding.severity}`",
                        f"`{finding.code}`",
                        f"`{by_path.get(finding.path, '')}`",
                        f"`{markdown_escape(finding.path)}`",
                        f"`{markdown_escape(finding.field)}`" if finding.field else "",
                        markdown_escape(finding.message),
                        f"`{markdown_escape(finding.actual)}`"
                        if finding.actual is not None
                        else "",
                        f"`{markdown_escape(finding.expected)}`"
                        if finding.expected is not None
                        else "",
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## 8. Process inventory",
            "",
            f"- Active managed process definitions: **{len(active_processes)}**",
            f"- Unmanaged files/placeholders under `Processes/`: **{len(unmanaged_process_files)}**",
            "",
            "## 9. Interpretation",
            "",
            "- Current and current-Development artifacts are checked against the complete draft schema.",
            "- Historical and closed-Development artifacts retain period-correct metadata; YAML, identity, version, path and duplicate integrity remain blocking.",
            "- Current use of former IDs is an error; historical use is resolved and reported as information.",
            "- A valid structured target descriptor may point to a not-yet-materialized version.",
            "- Historical acknowledgements suppress only explicitly accepted warning/info codes; integrity errors remain blocking.",
            "- The validator does not repair files, activate artifacts, commit or push.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(
    report_root: Path,
    vault: Path,
    documents: list[Document],
    findings: list[Finding],
    aliases: AliasIndex,
    acknowledgement_stats: AcknowledgementStats,
) -> Path:
    generated = dt.datetime.now().astimezone()
    timestamp = generated.strftime("%Y%m%dT%H%M%S%z")
    report_dir = (
        report_root.expanduser() / f"{timestamp}-managed-artifact-validation-v3-2"
    )
    report_dir.mkdir(parents=True, exist_ok=False)

    payload = {
        "generated_at": generated.isoformat(),
        "vault": str(vault),
        "validator_revision": VALIDATOR_REVISION,
        "validation_basis": VALIDATION_BASIS,
        "evidence_class_coverage": {
            "current_managed_total": len([doc for doc in documents if doc.scope_class == "managed" and doc.validation_profile in FULL_CURRENT_PROFILES]),
            "by_class": dict(Counter(doc.evidence_class or "missing" for doc in documents if doc.scope_class == "managed" and doc.validation_profile in FULL_CURRENT_PROFILES)),
            "required_missing_errors": sum(1 for item in findings if item.code == "missing_evidence_class"),
        },
        "mode": "read-only",
        "files_inventoried": len(documents),
        "scope_counts": dict(Counter(doc.scope_class for doc in documents)),
        "validation_profiles": dict(
            Counter(doc.validation_profile for doc in documents)
        ),
        "scan_zones": dict(Counter(doc.scan_zone for doc in documents)),
        "document_types": dict(
            Counter(doc.document_type or "no_document_type" for doc in documents)
        ),
        "active_managed_processes": len(
            [
                doc
                for doc in documents
                if doc.document_type == "process" and doc.status == "active"
            ]
        ),
        "unmanaged_files_under_processes": len(
            [
                doc
                for doc in documents
                if doc.scan_zone == "active_processes"
                and doc.scope_class == "unmanaged"
            ]
        ),
        "alias_mappings": aliases.aliases,
        "alias_sources": aliases.sources,
        "historical_acknowledgements": {
            "documents": acknowledgement_stats.acknowledged_documents,
            "suppressed_findings": acknowledgement_stats.suppressed_findings,
            "suppressed_by_code": acknowledgement_stats.suppressed_by_code,
        },
        "summary": dict(Counter(finding.severity for finding in findings)),
        "findings": [asdict(finding) for finding in findings],
    }
    (report_dir / "validation-report-v3-2.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (report_dir / "validation-report-v3-2.md").write_text(
        render_markdown(
            vault,
            documents,
            findings,
            aliases,
            acknowledgement_stats,
            generated.isoformat(),
        ),
        encoding="utf-8",
    )
    return report_dir


def write_fixture(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def managed_note(
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

def support_note(
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

def run_filename_unit_tests() -> list[str]:
    cases = {
        "Änderung und Überprüfung": "Änderung und Überprüfung",
        "  Mehrfache   Leerzeichen  ": "Mehrfache Leerzeichen",
        "A: B": "A - B",
        "A/B": "A - B",
        "A < B > C": "A - B - C",
        "Ende...   ": "Ende",
        "Cafe\u0301": "Café",
        "A -- B": "A - B",
    }
    passed: list[str] = []
    for source, expected in cases.items():
        actual = normalize_title_for_filename(source)
        if actual != expected:
            raise SelfTestFailure(
                f"Filename normalization failed: {source!r} -> {actual!r}, expected {expected!r}"
            )
        if unicodedata.normalize("NFC", actual) != actual:
            raise SelfTestFailure(f"Filename result is not NFC: {actual!r}")
        passed.append(source)
    return passed


def run_self_tests() -> dict[str, Any]:
    filename_cases = run_filename_unit_tests()
    with tempfile.TemporaryDirectory(prefix="cpwiki-validator-v3-2-") as temp:
        vault = Path(temp) / "cp-wiki"

        # 1. Active managed artifact with distributed alias declaration.
        active_path = Path(
            "Systems/cpKnowledgeSystem/Governance/Policies/TEST-POL Policy.md"
        )
        write_fixture(
            vault / active_path,
            managed_note(
                document_type="policy",
                id_field="policy_id",
                artifact_id="TEST-POL",
                title="Policy",
                version="1.0",
                status="active",
                canonical_path=active_path.as_posix(),
                extra="former_ids:\n  - TEST-POLICY-LEGACY\n",
            ),
        )

        # 1b. macOS-style NFD filesystem name must compare equal to
        # NFC canonical metadata and normalized title.
        unicode_actual_path = Path(
            "Systems/cpKnowledgeSystem/Governance/Policies/"
            "TEST-UNICODE Policy fu\u0308r Test.md"
        )
        unicode_canonical_path = (
            "Systems/cpKnowledgeSystem/Governance/Policies/"
            "TEST-UNICODE Policy für Test.md"
        )
        write_fixture(
            vault / unicode_actual_path,
            managed_note(
                document_type="policy",
                id_field="policy_id",
                artifact_id="TEST-UNICODE",
                title="Policy für Test",
                version="0.1",
                status="active",
                canonical_path=unicode_canonical_path,
            ),
        )

        # 2. Historical managed artifact with an old alias reference.
        history_path = Path(
            "Systems/cpKnowledgeSystem/Governance/Archive/Policies/"
            "TEST-POL@0.9 Policy.md"
        )
        write_fixture(
            vault / history_path,
            managed_note(
                document_type="policy",
                id_field="policy_id",
                artifact_id="TEST-POL",
                title="Policy",
                version="0.9",
                status="superseded",
                canonical_path=history_path.as_posix(),
                extra="references:\n  - TEST-POLICY-LEGACY@0.9\n",
            ),
        )

        # Validation-basis specification used by current-support fixtures.
        basis_path = Path(
            "Development/cpKnowledgeSystem/Specifications/"
            "CPKS-SPEC-ART@0.3 Managed Artifact Metadata and Validation Specification.md"
        )
        write_fixture(
            vault / basis_path,
            managed_note(
                document_type="specification",
                id_field="specification_id",
                artifact_id="CPKS-SPEC-ART",
                title="Managed Artifact Metadata and Validation Specification",
                version="0.3",
                status="draft",
                canonical_path=basis_path.as_posix(),
            ),
        )

        # 2b. Closed-development legacy artifact: long stable ID,
        # no canonical_path and legacy filename are preserved under the
        # restricted historical profile and must not be blocking errors.
        legacy_managed_path = Path(
            "Development/cpKnowledgeTools/Archive/Specifications/"
            "Legacy Platform Specification.md"
        )
        write_fixture(
            vault / legacy_managed_path,
            "---\n"
            "document_type: specification\n"
            "specification_id: TEST-DEVELOPMENT-PLATFORM-ARCHITECTURE\n"
            "title: Legacy Platform Specification\n"
            "version: \"1.0\"\n"
            "status: superseded\n"
            "owner: Owner\n"
            "created: 2026-07-16\n"
            "revised: 2026-07-16\n"
            "---\n"
            "# Legacy fixture\n",
        )

        # 3. Current Development managed artifact.
        dev_path = Path(
            "Development/cpKnowledgeSystem/Specifications/"
            "TEST-SPEC@0.2 Specification.md"
        )
        write_fixture(
            vault / dev_path,
            managed_note(
                document_type="specification",
                id_field="specification_id",
                artifact_id="TEST-SPEC",
                title="Specification",
                version="0.2",
                status="draft",
                canonical_path=dev_path.as_posix(),
                extra="governed_by:\n  - TEST-POL\n",
            ),
        )

        # 4. Closed Development managed process; current process schema fields
        # and sections are intentionally absent and must not be retroactive errors.
        closed_path = Path(
            "Development/cpKnowledgeSystem/Governance/Draft Processes/Archive/"
            "TEST-P01@0.1 Closed Process.md"
        )
        write_fixture(
            vault / closed_path,
            managed_note(
                document_type="process",
                id_field="process_id",
                artifact_id="TEST-P01",
                title="Closed Process",
                version="0.1",
                status="withdrawn",
                canonical_path=closed_path.as_posix(),
                extra=(
                    "governed_by:\n"
                    "  - TEST-POLICY-LEGACY@1.0\n"
                    "validation_acknowledgement:\n"
                    "  disposition: accepted_historical\n"
                    "  reviewed_by: Owner\n"
                    '  reviewed_at: "2026-07-26"\n'
                    '  source_report_generated_at: "2026-07-26T23:13:34+02:00"\n'
                    "  accepted_codes:\n"
                    "    - invalid_reference_form\n"
                    "    - legacy_artifact_id_resolved\n"
                    "  rationale: Historical fixture accepted.\n"
                ),
            ),
        )

        # 5. Current support with a valid planned target descriptor.
        current_support_path = Path(
            "Development/cpKnowledgeSystem/Governance/Reviews/Current Preflight.md"
        )
        write_fixture(
            vault / current_support_path,
            support_note(
                document_type="preflight",
                canonical_path=current_support_path.as_posix(),
                current=True,
                extra=(
                    "affected_artifacts:\n  - TEST-SPEC\n"
                    "target_artifact:\n"
                    "  reference: TEST-SPEC@0.3\n"
                    "  document_type: specification\n"
                    "  target_status: draft\n"
                    "  proposed_canonical_path: Development/cpKnowledgeSystem/Specifications/TEST-SPEC@0.3 Specification.md\n"
                ),
            ),
        )

        # 6. Legacy support with a legacy target descriptor. Warning only.
        legacy_support_path = Path(
            "Development/cpKnowledgeSystem/Governance/Reviews/Preflights/"
            "Legacy Preflight.md"
        )
        write_fixture(
            vault / legacy_support_path,
            support_note(
                document_type="preflight",
                canonical_path=legacy_support_path.as_posix(),
                current=False,
                extra=(
                    "governed_by:\n  - TEST-POLICY-LEGACY@1.0\n"
                    "target_artifact:\n"
                    "  document_type: specification\n"
                    '  target_version: "0.3"\n'
                ),
            ),
        )

        # 7. Unmanaged process placeholder.
        write_fixture(
            vault / "Processes/Governance/P01 Placeholder.md",
            "# Placeholder",
        )

        # 8. Active baseline may remain verified_current_state after activation.
        baseline_path = Path(
            "Systems/cpKnowledgeSystem/Governance/System Control/TEST-BL Baseline.md"
        )
        baseline_content = managed_note(
            document_type="baseline",
            id_field="baseline_id",
            artifact_id="TEST-BL",
            title="Baseline",
            version="0.1",
            status="active",
            canonical_path=baseline_path.as_posix(),
        ).replace("evidence_class: active_constraint\n", "evidence_class: verified_current_state\n")
        write_fixture(vault / baseline_path, baseline_content)

        # 9. committed_target without a mechanically visible binding is valid
        # syntactically but requires semantic review.
        committed_path = Path(
            "Development/cpKnowledgeSystem/Specifications/TEST-COMMIT@0.1 Committed.md"
        )
        committed_content = managed_note(
            document_type="specification",
            id_field="specification_id",
            artifact_id="TEST-COMMIT",
            title="Committed",
            version="0.1",
            status="draft",
            canonical_path=committed_path.as_posix(),
        ).replace("evidence_class: design_candidate\n", "evidence_class: committed_target\n")
        write_fixture(vault / committed_path, committed_content)

        # 10. Active Work Packages remain current in both system-wide and
        # component-specific Development contexts.
        system_work_package_path = Path(
            "Development/cpKnowledgeSystem/Work Packages/"
            "TEST-WP-SYSTEM System Work Package.md"
        )
        component_work_package_path = Path(
            "Development/cpKnowledgeTools/Work Packages/"
            "TEST-WP-COMPONENT Component Work Package.md"
        )
        for path, artifact_id, title in (
            (system_work_package_path, "TEST-WP-SYSTEM", "System Work Package"),
            (
                component_work_package_path,
                "TEST-WP-COMPONENT",
                "Component Work Package",
            ),
        ):
            write_fixture(
                vault / path,
                managed_note(
                    document_type="work_package",
                    id_field="work_package_id",
                    artifact_id=artifact_id,
                    title=title,
                    version="0.1",
                    status="active",
                    canonical_path=path.as_posix(),
                    extra="affected_artifacts: []\n",
                ),
            )

        documents, findings, aliases, acknowledgement_stats = validate_vault(vault)
        errors = [finding for finding in findings if finding.severity == "error"]
        if errors:
            raise SelfTestFailure(
                "Positive fixture produced errors:\n"
                + "\n".join(f"{item.code}: {item.path}" for item in errors)
            )
        unicode_regressions = [
            finding
            for finding in findings
            if finding.path == unicode_actual_path.as_posix()
            and finding.code in {"canonical_path_mismatch", "active_filename_mismatch", "versioned_filename_mismatch"}
        ]
        if unicode_regressions:
            raise SelfTestFailure(
                "Unicode NFC/NFD path equivalence regression: "
                + ", ".join(item.code for item in unicode_regressions)
            )

        documents_by_path = {doc.relative_path: doc for doc in documents}
        for path in (system_work_package_path, component_work_package_path):
            document = documents_by_path.get(path.as_posix())
            if document is None:
                raise SelfTestFailure(
                    f"Active Work Package was not inventoried: {path.as_posix()}"
                )
            if document.validation_profile != "current_managed":
                raise SelfTestFailure(
                    "Active Work Package was not classified as current_managed: "
                    f"{path.as_posix()} -> {document.validation_profile}"
                )

        legacy_blockers = [
            finding
            for finding in findings
            if finding.path == legacy_managed_path.as_posix()
            and finding.severity == "error"
        ]
        if legacy_blockers:
            raise SelfTestFailure(
                "Historical-profile regression produced blocking errors: "
                + ", ".join(item.code for item in legacy_blockers)
            )
        if not any(
            finding.path == legacy_managed_path.as_posix()
            and finding.code == "legacy_artifact_id"
            and finding.severity == "info"
            for finding in findings
        ):
            raise SelfTestFailure(
                "Historical long stable ID did not produce legacy_artifact_id info."
            )

        if acknowledgement_stats.acknowledged_documents != 1:
            raise SelfTestFailure(
                "Expected one valid historical acknowledgement in the positive fixture."
            )
        if acknowledgement_stats.suppressed_findings < 2:
            raise SelfTestFailure(
                "Historical acknowledgement did not suppress the expected warning/info findings."
            )
        if any(item.path == closed_path.as_posix() for item in findings):
            raise SelfTestFailure(
                "Acknowledged closed-Development findings remained in the detailed result."
            )

        profiles = Counter(doc.validation_profile for doc in documents)
        expected_profiles = {
            "current_managed",
            "historical_managed",
            "current_development_managed",
            "closed_development_managed",
            "current_support",
            "legacy_support",
            "unmanaged",
        }
        missing = expected_profiles - set(profiles)
        if missing:
            raise SelfTestFailure(
                f"Missing validation profiles in fixture: {sorted(missing)}"
            )

        codes = Counter(finding.code for finding in findings)
        for required_code in (
            "legacy_artifact_id_resolved",
            "planned_target_not_materialized",
            "legacy_target_artifact_descriptor",
            "evidence_class_semantic_review_required",
        ):
            if not codes[required_code]:
                raise SelfTestFailure(
                    f"Expected diagnostic not produced: {required_code}"
                )

        # Negative guardrails: invalid YAML, duplicate version, invalid target,
        # current legacy relation and filename mismatch must all be detected.
        negative = Path(temp) / "negative"
        duplicate_a = Path(
            "Systems/cpKnowledgeSystem/Governance/Policies/NEG-POL Policy.md"
        )
        duplicate_b = Path(
            "Systems/cpKnowledgeSystem/Governance/Decisions/NEG-POL Policy.md"
        )
        content = managed_note(
            document_type="policy",
            id_field="policy_id",
            artifact_id="NEG-POL",
            title="Policy",
            version="1.0",
            status="active",
            canonical_path=duplicate_a.as_posix(),
            extra=(
                "governed_by:\n"
                "  - CPKS-BASELINE\n"
                "validation_acknowledgement:\n"
                "  disposition: accepted_historical\n"
                "  reviewed_by: Owner\n"
                '  reviewed_at: "2026-07-26"\n'
                "  accepted_codes:\n"
                "    - legacy_artifact_id_in_current_reference\n"
            ),
        )
        write_fixture(negative / duplicate_a, content)
        write_fixture(
            negative / duplicate_b,
            content.replace(duplicate_a.as_posix(), duplicate_b.as_posix()),
        )
        invalid_target_path = Path(
            "Development/cpKnowledgeSystem/Governance/Reviews/Invalid Target.md"
        )
        write_fixture(
            negative / invalid_target_path,
            support_note(
                document_type="preflight",
                canonical_path=invalid_target_path.as_posix(),
                current=True,
                extra=(
                    "affected_artifacts: []\n"
                    "target_artifact:\n"
                    "  reference: not-a-reference\n"
                ),
            ),
        )
        write_fixture(
            negative
            / "Development/cp-wiki Vault/Specifications/Architecture Specification/Archive/BAD@1.0 Bad.md",
            "---\ndocument_type specification\n---\n# bad",
        )
        # ART 0.3 evidence-class guardrails.
        missing_evidence_path = Path(
            "Systems/cpKnowledgeSystem/Governance/Policies/NEG-MISSING-EVIDENCE Policy.md"
        )
        missing_evidence = managed_note(
            document_type="policy", id_field="policy_id", artifact_id="NEG-MISSING-EVIDENCE",
            title="Policy", version="0.1", status="active", canonical_path=missing_evidence_path.as_posix(),
        ).replace("evidence_class: active_constraint\n", "")
        write_fixture(negative / missing_evidence_path, missing_evidence)

        invalid_evidence_path = Path(
            "Systems/cpKnowledgeSystem/Governance/Policies/NEG-INVALID-EVIDENCE Policy.md"
        )
        invalid_evidence = managed_note(
            document_type="policy", id_field="policy_id", artifact_id="NEG-INVALID-EVIDENCE",
            title="Policy", version="0.1", status="active", canonical_path=invalid_evidence_path.as_posix(),
        ).replace("evidence_class: active_constraint", "evidence_class: not_a_class")
        write_fixture(negative / invalid_evidence_path, invalid_evidence)

        mismatch_evidence_path = Path(
            "Systems/cpKnowledgeSystem/Governance/Policies/NEG-MISMATCH-EVIDENCE Policy.md"
        )
        mismatch_evidence = managed_note(
            document_type="policy", id_field="policy_id", artifact_id="NEG-MISMATCH-EVIDENCE",
            title="Policy", version="0.1", status="active", canonical_path=mismatch_evidence_path.as_posix(),
        ).replace("evidence_class: active_constraint", "evidence_class: design_candidate")
        write_fixture(negative / mismatch_evidence_path, mismatch_evidence)

        # Active Work Packages must remain invalid below Archive/History, and
        # the Development exception must not apply to ordinary active specs.
        closed_work_package_paths = []
        for zone in ("Archive", "History"):
            path = Path(
                "Development/cpKnowledgeTools/Work Packages/"
                f"{zone}/NEG-WP-{zone.upper()} Closed Work Package.md"
            )
            closed_work_package_paths.append(path)
            write_fixture(
                negative / path,
                managed_note(
                    document_type="work_package",
                    id_field="work_package_id",
                    artifact_id=f"NEG-WP-{zone.upper()}",
                    title="Closed Work Package",
                    version="0.1",
                    status="active",
                    canonical_path=path.as_posix(),
                    extra="affected_artifacts: []\n",
                ),
            )

        active_development_spec_path = Path(
            "Development/cpKnowledgeTools/Specifications/"
            "NEG-SPEC-DEVELOPMENT Active Development Specification.md"
        )
        write_fixture(
            negative / active_development_spec_path,
            managed_note(
                document_type="specification",
                id_field="specification_id",
                artifact_id="NEG-SPEC-DEVELOPMENT",
                title="Active Development Specification",
                version="0.1",
                status="active",
                canonical_path=active_development_spec_path.as_posix(),
            ),
        )

        # Prospective initial-version rule for a new non-Decision line.
        bad_initial_path = Path(
            "Development/cpKnowledgeSystem/Specifications/NEG-INITIAL@0.2 Bad Initial.md"
        )
        bad_initial = managed_note(
            document_type="specification", id_field="specification_id", artifact_id="NEG-INITIAL",
            title="Bad Initial", version="0.2", status="draft", canonical_path=bad_initial_path.as_posix(),
        ).replace("created: 2026-07-26", "created: 2026-08-01").replace("revised: 2026-07-26", "revised: 2026-08-01")
        write_fixture(negative / bad_initial_path, bad_initial)

        # Prospective initial-version rule for a new Decision line.
        bad_decision_path = Path(
            "Development/cpKnowledgeSystem/Governance/Draft Decisions/NEG-DEC@0.2 Bad Decision.md"
        )
        bad_decision = managed_note(
            document_type="decision_record", id_field="decision_id", artifact_id="NEG-DEC",
            title="Bad Decision", version="0.2", status="draft", canonical_path=bad_decision_path.as_posix(),
        ).replace("created: 2026-07-26", "created: 2026-08-01").replace("revised: 2026-07-26", "revised: 2026-08-01")
        write_fixture(negative / bad_decision_path, bad_decision)

        # Chronological/numeric sequence conflict with a valid 0.1 initial version.
        seq_01 = Path("Development/cpKnowledgeSystem/Specifications/Archive/NEG-SEQ@0.1 Sequence.md")
        seq_03 = Path("Development/cpKnowledgeSystem/Specifications/NEG-SEQ@0.3 Sequence.md")
        seq_02 = Path("Development/cpKnowledgeSystem/Specifications/Archive/NEG-SEQ@0.2 Sequence.md")
        for path, version, status, created in (
            (seq_01, "0.1", "withdrawn", "2026-08-01"),
            (seq_03, "0.3", "draft", "2026-08-02"),
            (seq_02, "0.2", "withdrawn", "2026-08-03"),
        ):
            content = managed_note(
                document_type="specification", id_field="specification_id", artifact_id="NEG-SEQ",
                title="Sequence", version=version, status=status, canonical_path=path.as_posix(),
            ).replace("created: 2026-07-26", f"created: {created}").replace("revised: 2026-07-26", f"revised: {created}")
            write_fixture(negative / path, content)

        _, negative_findings, _, _ = validate_vault(negative)
        negative_codes = Counter(item.code for item in negative_findings)
        for required_code in (
            "invalid_yaml_frontmatter",
            "duplicate_stable_id_and_version",
            "multiple_active_versions",
            "legacy_artifact_id_in_current_reference",
            "invalid_reference_form",
            "validation_acknowledgement_not_allowed",
            "missing_evidence_class",
            "invalid_evidence_class",
            "evidence_class_status_mismatch",
            "invalid_initial_artifact_version",
            "invalid_initial_decision_version",
            "non_monotonic_artifact_version_sequence",
        ):
            if not negative_codes[required_code]:
                raise SelfTestFailure(
                    f"Negative guardrail not detected: {required_code}"
                )

        for path in closed_work_package_paths:
            path_codes = {
                item.code
                for item in negative_findings
                if item.path == path.as_posix() and item.severity == "error"
            }
            if "closed_development_status_not_terminal" not in path_codes:
                raise SelfTestFailure(
                    "Active Work Package in a closed subtree was not rejected: "
                    f"{path.as_posix()} -> {sorted(path_codes)}"
                )

        development_spec_codes = {
            item.code
            for item in negative_findings
            if item.path == active_development_spec_path.as_posix()
            and item.severity == "error"
        }
        if "active_artifact_outside_active_zone" not in development_spec_codes:
            raise SelfTestFailure(
                "Ordinary active Development specification was not rejected: "
                f"{sorted(development_spec_codes)}"
            )

        return {
            "profiles": dict(profiles),
            "positive_findings": dict(codes),
            "negative_guardrails": dict(negative_codes),
            "alias_mappings": aliases.aliases,
            "acknowledgement_stats": asdict(acknowledgement_stats),
            "filename_cases": len(filename_cases),
        }


def publish_reports_to_vault(
    report_dir: Path,
    publish_root: Path,
) -> list[Path]:
    """Copy durable report outputs from the technical run into Generated."""
    report_dir = report_dir.expanduser().resolve()
    publish_root = publish_root.expanduser().resolve()
    publish_root.mkdir(parents=True, exist_ok=True)

    suffix = "-managed-artifact-validation-v3-2"
    run_name = report_dir.name
    if not run_name.endswith(suffix):
        raise RuntimeError(f"Unexpected validator report directory name: {run_name}")
    timestamp = run_name[:-len(suffix)]

    source_md = report_dir / "validation-report-v3-2.md"
    source_json = report_dir / "validation-report-v3-2.json"
    for source in (source_md, source_json):
        if not source.is_file():
            raise RuntimeError(f"Expected validator report missing: {source}")

    targets = [
        publish_root / f"{timestamp}-managed-artifact-validation-v3-2.md",
        publish_root / f"{timestamp}-managed-artifact-validation-v3-2.json",
    ]

    for source, target in zip((source_md, source_json), targets):
        if target.exists():
            raise RuntimeError(f"Published validator report already exists: {target}")
        shutil.copy2(source, target)

    return targets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument(
        "--publish-report",
        action="store_true",
        help=(
            "Additionally publish the Markdown/JSON report to "
            "<vault>/Generated/Validation."
        ),
    )
    parser.add_argument(
        "--publish-report-root",
        type=Path,
        default=None,
        help=(
            "Override the durable report directory. "
            "Default: <vault>/Generated/Validation."
        ),
    )
    parser.add_argument(
        "--strict-exit",
        action="store_true",
        help="Return exit code 1 when blocking errors are found.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run embedded profile, alias, target descriptor and filename tests.",
    )
    args = parser.parse_args()

    if args.self_test:
        try:
            result = run_self_tests()
        except SelfTestFailure as exc:
            print(f"SELF-TEST FAILED: {exc}", file=sys.stderr)
            return 1
        print("Managed-artifact validator v3.2 self-test passed.")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    vault = args.vault.expanduser().resolve()
    if not vault.is_dir():
        print(f"ERROR: Vault not found: {vault}", file=sys.stderr)
        return 2

    documents, findings, aliases, acknowledgement_stats = validate_vault(vault)
    report_dir = write_reports(
        args.report_root,
        vault,
        documents,
        findings,
        aliases,
        acknowledgement_stats,
    )

    published_reports: list[Path] = []
    if args.publish_report:
        publish_root = (
            args.publish_report_root.expanduser()
            if args.publish_report_root is not None
            else vault / "Generated" / "Validation"
        )
        try:
            published_reports = publish_reports_to_vault(report_dir, publish_root)
        except Exception as exc:
            print(f"ERROR: Could not publish validator report: {exc}", file=sys.stderr)
            return 2

    severity_counts = Counter(finding.severity for finding in findings)
    profile_counts = Counter(doc.validation_profile for doc in documents)
    print("Managed-artifact validation v3.2 completed.")
    print(f"Files inventoried: {len(documents)}")
    for profile in (
        "current_managed",
        "historical_managed",
        "current_development_managed",
        "closed_development_managed",
        "current_support",
        "legacy_support",
        "unmanaged",
    ):
        print(f"{profile + ':':38} {profile_counts[profile]}")
    print(f"Alias mappings:                        {len(aliases.aliases)}")
    print(
        f"Historical acknowledgements:           {acknowledgement_stats.acknowledged_documents}"
    )
    print(
        f"Acknowledged findings suppressed:      {acknowledgement_stats.suppressed_findings}"
    )
    print(f"Errors:                                {severity_counts['error']}")
    print(f"Warnings:                              {severity_counts['warning']}")
    print(f"Info:                                  {severity_counts['info']}")
    print(f"Report directory:                      {report_dir}")
    for published_report in published_reports:
        print(f"Published report:                      {published_report}")

    if args.strict_exit and severity_counts["error"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
