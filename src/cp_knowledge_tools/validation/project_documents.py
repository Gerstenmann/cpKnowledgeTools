"""Read-only validation of cp-wiki ``project_document`` Markdown files."""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

VALIDATOR_NAME = "cp-wiki-project-document-validator"
VALIDATOR_VERSION = "1.0"
RULE_SOURCE = "CPKS-SPEC-PDOC@0.1"

PROFILE_CURRENT = "project_document_current"
PROFILE_HISTORY = "project_document_history"
PROFILE_COMPLETE = "project_document_complete"
PROFILES = (PROFILE_CURRENT, PROFILE_HISTORY, PROFILE_COMPLETE)

PROJECT_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DOCUMENT_KEY_PATTERN = PROJECT_KEY_PATTERN
INFORMATION_ROLE_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
STABLE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
PROJECT_DOCUMENT_MARKER = re.compile(
    r"(?m)^\s*type\s*:\s*['\"]?project_document['\"]?\s*$"
)

CURRENT_STATUSES = {"working", "current"}
HISTORICAL_STATUSES = {"superseded", "archived"}
ALLOWED_STATUSES = CURRENT_STATUSES | HISTORICAL_STATUSES
KNOWN_INFORMATION_ROLES = {
    "mvp_scope_and_acceptance",
    "architecture_and_reuse_boundaries",
    "current_state_and_gap_assessment",
    "project_plan_and_work_packages",
    "validation_and_evaluation_plan",
    "decisions_risks_open_questions",
    "initial_readiness_report",
    "research_brief",
    "golden_truth_matrix",
    "status_report",
    "evaluation_report",
    "inventory",
}
AS_OF_ROLES = {
    "current_state_and_gap_assessment",
    "initial_readiness_report",
    "status_report",
    "evaluation_report",
    "inventory",
}
CURRENT_REQUIRED_FIELDS = (
    "type",
    "project_key",
    "document_key",
    "information_role",
    "title",
    "version",
    "status",
    "owner",
    "created",
    "revised",
    "canonical_path",
)
RELATION_FIELDS = (
    "governance_refs",
    "related_documents",
    "related_work_packages",
)
MIGRATION_CODES = {
    "project_document_missing_required_field",
    "project_document_invalid_project_key",
    "project_document_invalid_document_key",
    "project_document_invalid_information_role",
    "project_document_invalid_version",
    "project_document_invalid_status",
    "project_document_invalid_date",
    "project_document_revised_before_created",
    "project_document_canonical_path_mismatch",
    "project_document_current_in_archive",
    "project_document_historical_outside_archive",
    "project_document_filename_mismatch",
    "project_document_historical_filename_mismatch",
    "project_document_versioned_relation",
    "project_document_missing_as_of",
    "project_document_legacy_missing_field",
    "project_document_legacy_status",
    "project_document_legacy_archive_placement",
}


class ProjectDocumentValidationError(RuntimeError):
    """A technical failure prevented a reliable validation run."""


@dataclass(frozen=True, slots=True)
class ProjectDocumentFinding:
    """One non-blocking diagnostic governed by CPKS-SPEC-PDOC."""

    severity: str
    code: str
    message: str
    path: str
    line: int | None = None
    field: str | None = None
    project_key: str | None = None
    document_key: str | None = None
    profile: str | None = None
    actual: Any = None
    expected: Any = None
    rule_source: str = RULE_SOURCE

    def __post_init__(self) -> None:
        if self.severity not in {"warning", "info"}:
            raise ValueError("Project-document findings may only be warning or info.")


@dataclass(frozen=True, slots=True)
class ProjectDocumentValidationResult:
    """Inventory and findings from one deterministic validation run."""

    generated_at: str
    vault_root: str
    profile: str
    inventory: dict[str, Any]
    findings: tuple[ProjectDocumentFinding, ...]

    @property
    def summary(self) -> dict[str, Any]:
        """Return stable severity and code counts."""

        severity = Counter(item.severity for item in self.findings)
        by_code = Counter(item.code for item in self.findings)
        return {
            "warning": severity["warning"],
            "info": severity["info"],
            "total": len(self.findings),
            "by_code": dict(sorted(by_code.items())),
        }


@dataclass(slots=True)
class _ProjectDocument:
    relative_path: str
    validation_profile: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    raw_frontmatter: str | None = None
    parse_error: str | None = None
    parse_error_line: int | None = None

    @property
    def project_key(self) -> str | None:
        return _scalar_text(self.frontmatter.get("project_key"))

    @property
    def document_key(self) -> str | None:
        return _scalar_text(self.frontmatter.get("document_key"))

    @property
    def status(self) -> str | None:
        return _scalar_text(self.frontmatter.get("status"))

    @property
    def in_archive(self) -> bool:
        return "Archive" in Path(self.relative_path).parts


def _scalar_text(value: Any) -> str | None:
    if value is None or isinstance(value, (list, dict)):
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _field_line(document: _ProjectDocument, field_name: str) -> int | None:
    if document.raw_frontmatter is None:
        return None
    pattern = re.compile(rf"^\s*{re.escape(field_name)}\s*:")
    for line_number, line in enumerate(
        document.raw_frontmatter.splitlines(), start=2
    ):
        if pattern.match(line):
            return line_number
    return None


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise ValueError("YAML frontmatter is not closed with '---'.")


def _parse_candidate(relative_path: str, text: str) -> _ProjectDocument | None:
    in_archive = "Archive" in Path(relative_path).parts
    validation_profile = PROFILE_HISTORY if in_archive else PROFILE_CURRENT
    try:
        raw_frontmatter, _ = _split_frontmatter(text)
    except ValueError as exc:
        if not PROJECT_DOCUMENT_MARKER.search(text):
            return None
        return _ProjectDocument(
            relative_path=relative_path,
            validation_profile=validation_profile,
            parse_error=str(exc),
        )

    if raw_frontmatter is None:
        return None

    try:
        parsed = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError as exc:
        if not PROJECT_DOCUMENT_MARKER.search(raw_frontmatter):
            return None
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 2 if mark is not None else None
        problem = getattr(exc, "problem", None) or str(exc)
        return _ProjectDocument(
            relative_path=relative_path,
            validation_profile=validation_profile,
            raw_frontmatter=raw_frontmatter,
            parse_error=f"Invalid YAML frontmatter: {problem}",
            parse_error_line=line,
        )

    if not isinstance(parsed, dict) or parsed.get("type") != "project_document":
        return None

    return _ProjectDocument(
        relative_path=relative_path,
        validation_profile=validation_profile,
        frontmatter=parsed,
        raw_frontmatter=raw_frontmatter,
    )


def _normalize_title(title: str) -> str:
    value = unicodedata.normalize("NFC", title.strip())
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", " - ", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"(?:\s*-\s*){2,}", " - ", value)
    return value.rstrip(". ")


def _date_value(value: Any) -> str | None:
    text = _scalar_text(value)
    if text is None or not DATE_PATTERN.fullmatch(text):
        return None
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _equivalent_path(left: str, right: str) -> bool:
    return unicodedata.normalize("NFC", left) == unicodedata.normalize("NFC", right)


def _add(
    findings: list[ProjectDocumentFinding],
    document: _ProjectDocument,
    severity: str,
    code: str,
    message: str,
    *,
    field_name: str | None = None,
    actual: Any = None,
    expected: Any = None,
    line: int | None = None,
) -> None:
    findings.append(
        ProjectDocumentFinding(
            severity=severity,
            code=code,
            message=message,
            path=document.relative_path,
            line=line if line is not None else (
                _field_line(document, field_name) if field_name else None
            ),
            field=field_name,
            project_key=document.project_key,
            document_key=document.document_key,
            profile=document.validation_profile,
            actual=actual,
            expected=expected,
        )
    )


def _validate_required_fields(
    document: _ProjectDocument,
    findings: list[ProjectDocumentFinding],
) -> None:
    for field_name in CURRENT_REQUIRED_FIELDS:
        if not _is_empty(document.frontmatter.get(field_name)):
            continue
        if document.validation_profile == PROFILE_CURRENT:
            _add(
                findings,
                document,
                "warning",
                "project_document_missing_required_field",
                f"Current Project document requires {field_name!r}.",
                field_name=field_name,
            )
        else:
            _add(
                findings,
                document,
                "info",
                "project_document_legacy_missing_field",
                f"Historical Project document does not carry {field_name!r}.",
                field_name=field_name,
            )


def _validate_keys_and_role(
    document: _ProjectDocument,
    findings: list[ProjectDocumentFinding],
) -> None:
    for field_name, pattern, code in (
        ("project_key", PROJECT_KEY_PATTERN, "project_document_invalid_project_key"),
        (
            "document_key",
            DOCUMENT_KEY_PATTERN,
            "project_document_invalid_document_key",
        ),
    ):
        value = _scalar_text(document.frontmatter.get(field_name))
        if value is not None and not pattern.fullmatch(value):
            _add(
                findings,
                document,
                "warning",
                code,
                f"{field_name} does not match the required kebab-case syntax.",
                field_name=field_name,
                actual=value,
                expected=pattern.pattern,
            )

    role = _scalar_text(document.frontmatter.get("information_role"))
    if role is None:
        return
    if not INFORMATION_ROLE_PATTERN.fullmatch(role):
        _add(
            findings,
            document,
            "warning",
            "project_document_invalid_information_role",
            "information_role does not match the required snake_case syntax.",
            field_name="information_role",
            actual=role,
            expected=INFORMATION_ROLE_PATTERN.pattern,
        )
    elif role not in KNOWN_INFORMATION_ROLES:
        _add(
            findings,
            document,
            "info",
            "project_document_unknown_information_role",
            "The syntactically valid information_role is not in the "
            "recommended catalog.",
            field_name="information_role",
            actual=role,
            expected="recommended or project-specific role",
        )


def _validate_version_status_and_dates(
    document: _ProjectDocument,
    findings: list[ProjectDocumentFinding],
) -> None:
    version_raw = document.frontmatter.get("version")
    version = _scalar_text(version_raw)
    if version is not None and (
        not isinstance(version_raw, str) or not VERSION_PATTERN.fullmatch(version)
    ):
        _add(
            findings,
            document,
            "warning",
            "project_document_invalid_version",
            "version must be a YAML string with two or three numeric segments.",
            field_name="version",
            actual=version_raw,
            expected=VERSION_PATTERN.pattern,
        )

    status = document.status
    if status is not None and status not in ALLOWED_STATUSES:
        if document.validation_profile == PROFILE_HISTORY:
            _add(
                findings,
                document,
                "info",
                "project_document_legacy_status",
                "Historical Project document uses a legacy lifecycle status.",
                field_name="status",
                actual=status,
                expected=sorted(HISTORICAL_STATUSES),
            )
        else:
            _add(
                findings,
                document,
                "warning",
                "project_document_invalid_status",
                "Current Project document uses an unsupported lifecycle status.",
                field_name="status",
                actual=status,
                expected=sorted(ALLOWED_STATUSES),
            )

    parsed_dates: dict[str, str] = {}
    for field_name in ("created", "revised", "as_of"):
        if field_name not in document.frontmatter:
            continue
        value = document.frontmatter[field_name]
        parsed = _date_value(value)
        if parsed is None:
            _add(
                findings,
                document,
                "warning",
                "project_document_invalid_date",
                f"{field_name} must be a valid ISO date in YYYY-MM-DD form.",
                field_name=field_name,
                actual=value,
                expected="YYYY-MM-DD",
            )
        else:
            parsed_dates[field_name] = parsed

    created = parsed_dates.get("created")
    revised = parsed_dates.get("revised")
    if created and revised and revised < created:
        _add(
            findings,
            document,
            "warning",
            "project_document_revised_before_created",
            "revised must not be earlier than created.",
            field_name="revised",
            actual=revised,
            expected=f">= {created}",
        )


def _validate_path_and_filename(
    document: _ProjectDocument,
    findings: list[ProjectDocumentFinding],
) -> None:
    canonical_path = _scalar_text(document.frontmatter.get("canonical_path"))
    if canonical_path is not None and not _equivalent_path(
        canonical_path, document.relative_path
    ):
        _add(
            findings,
            document,
            "warning",
            "project_document_canonical_path_mismatch",
            "canonical_path does not match the actual Vault-relative path.",
            field_name="canonical_path",
            actual=canonical_path,
            expected=document.relative_path,
        )

    status = document.status
    if document.in_archive and status in CURRENT_STATUSES:
        _add(
            findings,
            document,
            "warning",
            "project_document_current_in_archive",
            "A current/working Project document is located below Archive/.",
            field_name="status",
            actual=status,
            expected=sorted(HISTORICAL_STATUSES),
        )
    elif not document.in_archive and status in HISTORICAL_STATUSES:
        _add(
            findings,
            document,
            "warning",
            "project_document_historical_outside_archive",
            "A historical Project document is outside a project-local Archive/.",
            field_name="status",
            actual=status,
            expected="path below Archive/",
        )
        _add(
            findings,
            document,
            "info",
            "project_document_legacy_archive_placement",
            "The historical document is a candidate for project-local "
            "archival placement.",
            field_name="status",
            actual=document.relative_path,
            expected="<Project-Root>/Archive/",
        )

    title = _scalar_text(document.frontmatter.get("title"))
    if title is None:
        return
    actual_name = Path(document.relative_path).name
    normalized_title = _normalize_title(title)
    if document.in_archive:
        document_key = document.document_key
        version = _scalar_text(document.frontmatter.get("version"))
        if document_key and version and VERSION_PATTERN.fullmatch(version):
            expected_name = f"{document_key}@{version} {normalized_title}.md"
            if not _equivalent_path(actual_name, expected_name):
                _add(
                    findings,
                    document,
                    "warning",
                    "project_document_historical_filename_mismatch",
                    "Historical filename does not match document_key, version "
                    "and title.",
                    actual=actual_name,
                    expected=expected_name,
                )
    else:
        expected_name = f"{normalized_title}.md"
        if not _equivalent_path(actual_name, expected_name):
            _add(
                findings,
                document,
                "warning",
                "project_document_filename_mismatch",
                "Current filename does not match the normalized title.",
                actual=actual_name,
                expected=expected_name,
            )


def _valid_unversioned_relation(field_name: str, value: str) -> bool:
    if field_name == "related_documents":
        return bool(DOCUMENT_KEY_PATTERN.fullmatch(value))
    return bool(STABLE_ID_PATTERN.fullmatch(value))


def _validate_relations_and_as_of(
    document: _ProjectDocument,
    findings: list[ProjectDocumentFinding],
) -> None:
    for field_name in RELATION_FIELDS:
        raw = document.frontmatter.get(field_name)
        if raw is None:
            continue
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if not isinstance(value, str):
                continue
            if "@" in value:
                _add(
                    findings,
                    document,
                    "warning",
                    "project_document_versioned_relation",
                    f"{field_name} must contain unversioned references.",
                    field_name=field_name,
                    actual=value,
                    expected="unversioned reference",
                )
            elif not _valid_unversioned_relation(field_name, value):
                _add(
                    findings,
                    document,
                    "warning",
                    "project_document_versioned_relation",
                    f"{field_name} contains an invalid general relation.",
                    field_name=field_name,
                    actual=value,
                    expected="valid unversioned reference",
                )

    role = _scalar_text(document.frontmatter.get("information_role"))
    if (
        document.validation_profile == PROFILE_CURRENT
        and role in AS_OF_ROLES
        and _is_empty(document.frontmatter.get("as_of"))
    ):
        _add(
            findings,
            document,
            "warning",
            "project_document_missing_as_of",
            "The information role describes a dated state and requires as_of review.",
            field_name="as_of",
            expected="YYYY-MM-DD",
        )


def _validate_document(
    document: _ProjectDocument,
) -> list[ProjectDocumentFinding]:
    findings: list[ProjectDocumentFinding] = []
    if document.parse_error:
        _add(
            findings,
            document,
            "warning",
            "project_document_unreadable_frontmatter",
            document.parse_error,
            line=document.parse_error_line,
        )
        _add(
            findings,
            document,
            "info",
            "project_document_migration_candidate",
            "Unreadable Project-document frontmatter requires controlled review.",
        )
        return findings

    _validate_required_fields(document, findings)
    _validate_keys_and_role(document, findings)
    _validate_version_status_and_dates(document, findings)
    _validate_path_and_filename(document, findings)
    _validate_relations_and_as_of(document, findings)

    if any(item.code in MIGRATION_CODES for item in findings):
        _add(
            findings,
            document,
            "info",
            "project_document_migration_candidate",
            "The document has one or more PDOC migration or maintenance findings.",
        )
    return findings


def _validate_duplicates(
    documents: list[_ProjectDocument],
) -> list[ProjectDocumentFinding]:
    findings: list[ProjectDocumentFinding] = []
    current: dict[tuple[str, str], list[_ProjectDocument]] = defaultdict(list)
    for document in documents:
        if (
            document.status in CURRENT_STATUSES
            and document.project_key
            and document.document_key
        ):
            current[(document.project_key, document.document_key)].append(document)

    for key, duplicates in current.items():
        if len(duplicates) < 2:
            continue
        paths = sorted(item.relative_path for item in duplicates)
        for document in duplicates:
            _add(
                findings,
                document,
                "warning",
                "project_document_duplicate_current_key",
                "More than one current/working file uses the same project-local key.",
                actual={"project_key": key[0], "document_key": key[1]},
                expected={"maximum_current_files": 1, "paths": paths},
            )
    return findings


def _discover_documents(vault_root: Path, profile: str) -> list[_ProjectDocument]:
    projects_root = vault_root / "Projects"
    if not projects_root.is_dir():
        raise ProjectDocumentValidationError(
            f"Configured Vault has no readable Projects/ directory: {projects_root}"
        )

    documents: list[_ProjectDocument] = []
    for path in sorted(projects_root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            relative_path = path.relative_to(vault_root).as_posix()
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ProjectDocumentValidationError(
                f"Could not read Project Markdown file {path}: {exc}"
            ) from exc
        document = _parse_candidate(relative_path, text)
        if document is None:
            continue
        if (
            profile == PROFILE_CURRENT
            and document.validation_profile != PROFILE_CURRENT
        ):
            continue
        if (
            profile == PROFILE_HISTORY
            and document.validation_profile != PROFILE_HISTORY
        ):
            continue
        documents.append(document)
    return documents


def validate_project_documents(
    vault_root: Path,
    profile: str = PROFILE_COMPLETE,
) -> ProjectDocumentValidationResult:
    """Validate project documents without mutating the Vault."""

    if profile not in PROFILES:
        raise ProjectDocumentValidationError(
            f"Unsupported Project-document profile: {profile!r}"
        )
    resolved_vault = vault_root.expanduser().resolve()
    if not resolved_vault.is_dir():
        raise ProjectDocumentValidationError(
            f"Configured Vault root is not a directory: {resolved_vault}"
        )

    documents = _discover_documents(resolved_vault, profile)
    findings = [
        item
        for document in documents
        for item in _validate_document(document)
    ]
    findings.extend(_validate_duplicates(documents))
    findings.sort(
        key=lambda item: (
            item.severity,
            item.path,
            item.code,
            item.field or "",
        )
    )

    current_paths = sorted(
        item.relative_path
        for item in documents
        if item.validation_profile == PROFILE_CURRENT
    )
    history_paths = sorted(
        item.relative_path
        for item in documents
        if item.validation_profile == PROFILE_HISTORY
    )
    inventory = {
        "total": len(documents),
        "current": len(current_paths),
        "history": len(history_paths),
        "current_paths": current_paths,
        "history_paths": history_paths,
    }
    return ProjectDocumentValidationResult(
        generated_at=dt.datetime.now().astimezone().isoformat(),
        vault_root=str(resolved_vault),
        profile=profile,
        inventory=inventory,
        findings=tuple(findings),
    )


def _finding_payload(finding: ProjectDocumentFinding) -> dict[str, Any]:
    return {
        key: value
        for key, value in asdict(finding).items()
        if value is not None
    }


def _render_markdown(result: ProjectDocumentValidationResult) -> str:
    lines = [
        "# Project Document Validation Report — Version 1.0",
        "",
        f"- Generated: `{result.generated_at}`",
        f"- Vault: `{result.vault_root}`",
        f"- Profile: `{result.profile}`",
        f"- Rule basis: `{RULE_SOURCE}`",
        "- Mode: read-only",
        f"- Project documents: **{result.inventory['total']}**",
        f"- Current: **{result.inventory['current']}**",
        f"- History: **{result.inventory['history']}**",
        f"- Warnings: **{result.summary['warning']}**",
        f"- Info: **{result.summary['info']}**",
        "",
        "## Finding summary",
        "",
        "| Severity | Code | Count |",
        "|---|---|---:|",
    ]
    code_counts = Counter((item.severity, item.code) for item in result.findings)
    for (severity, code), count in sorted(code_counts.items()):
        lines.append(f"| `{severity}` | `{code}` | {count} |")

    lines.extend(
        [
            "",
            "## Detailed findings",
            "",
            "| Severity | Code | Profile | Path | Field | Message | Actual | "
            "Expected |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    if not result.findings:
        lines.append("|  |  |  |  |  | No findings. |  |  |")
    for finding in result.findings:
        actual = "" if finding.actual is None else json.dumps(
            finding.actual, ensure_ascii=False
        )
        expected = "" if finding.expected is None else json.dumps(
            finding.expected, ensure_ascii=False
        )
        cells = (
            finding.severity,
            finding.code,
            finding.profile or "",
            finding.path,
            finding.field or "",
            finding.message,
            actual,
            expected,
        )
        escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in cells]
        lines.append("| " + " | ".join(escaped) + " |")
    lines.append("")
    return "\n".join(lines)


def _ensure_report_root_outside_vault(report_root: Path, vault_root: Path) -> None:
    try:
        report_root.relative_to(vault_root)
    except ValueError:
        return
    raise ProjectDocumentValidationError(
        "Project-document reports must be written outside the cp-wiki Vault."
    )


def write_project_document_reports(
    result: ProjectDocumentValidationResult,
    report_root: Path,
) -> tuple[Path, Path]:
    """Write JSON and Markdown reports outside the validated Vault."""

    resolved_root = report_root.expanduser().resolve()
    vault_root = Path(result.vault_root).resolve()
    _ensure_report_root_outside_vault(resolved_root, vault_root)
    generated = dt.datetime.fromisoformat(result.generated_at)
    run_name = generated.strftime("%Y%m%dT%H%M%S%z-project-document-validation-v1")
    run_directory = resolved_root / run_name
    try:
        run_directory.mkdir(parents=True, exist_ok=False)
        json_path = run_directory / "project-document-validation-v1.json"
        markdown_path = run_directory / "project-document-validation-v1.md"
        payload = {
            "validator": {"name": VALIDATOR_NAME, "version": VALIDATOR_VERSION},
            "rule_basis": [RULE_SOURCE],
            "generated_at": result.generated_at,
            "vault_root": result.vault_root,
            "profile": result.profile,
            "inventory": result.inventory,
            "summary": result.summary,
            "findings": [_finding_payload(item) for item in result.findings],
        }
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(_render_markdown(result), encoding="utf-8")
    except OSError as exc:
        raise ProjectDocumentValidationError(
            f"Could not write Project-document reports: {exc}"
        ) from exc
    return json_path, markdown_path


def run_self_test() -> dict[str, int]:
    """Exercise the deterministic core without filesystem mutation."""

    relative_path = "Projects/Internal/Synthetic/Architecture.md"
    document = _ProjectDocument(
        relative_path=relative_path,
        validation_profile=PROFILE_CURRENT,
        frontmatter={
            "type": "project_document",
            "project_key": "synthetic-project",
            "document_key": "architecture",
            "information_role": "architecture_and_reuse_boundaries",
            "title": "Architecture",
            "version": "1.0",
            "status": "current",
            "owner": "Owner",
            "created": "2026-08-09",
            "revised": "2026-08-09",
            "canonical_path": relative_path,
        },
    )
    findings = _validate_document(document)
    if findings:
        raise ProjectDocumentValidationError(
            f"Project-document self-test produced findings: {findings!r}"
        )
    return {"documents": 1, "findings": 0}
