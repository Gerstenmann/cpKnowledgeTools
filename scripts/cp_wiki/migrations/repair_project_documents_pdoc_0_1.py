#!/usr/bin/env python3
"""Report-bound, dry-run-first migration for the PDOC 0.1 legacy inventory."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPORT_SHA256 = "a0cf397c7acd45208a3005835444c078e5b91d02cb51123a8ff4c84f3d1e780a"
RULE_SOURCE = "CPKS-SPEC-PDOC@0.1"
VALIDATOR_NAME = "cp-wiki-project-document-validator"
VALIDATOR_VERSION = "1.0"
MIGRATION_DATE = "2026-08-09"
DEFAULT_VAULT = Path("/Users/cp/Documents/cp-wiki")
PROJECT_ROOT = (
    "Projects/Internal/Kommunikations-Wissen verarbeiten und bereitstellen"
)


class MigrationError(RuntimeError):
    """A report, drift or filesystem guard prevented the migration."""


@dataclass(frozen=True, slots=True)
class MigrationSpec:
    source_path: str
    target_path: str
    expected_frontmatter: dict[str, Any]
    expected_body_sha256: str
    updates: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PreparedMigration:
    source_path: Path
    target_path: Path
    relative_source: str
    relative_target: str
    before: bytes
    after: bytes
    diff: str


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    vault_root: Path
    report_path: Path
    report_sha256: str
    operations: tuple[PreparedMigration, ...]


def _expected_frontmatter(
    *,
    information_role: str,
    title: str,
    status: str,
    created: str,
    revised: str,
    canonical_path: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "project_document",
        "project_key": "communications-knowledge-pilot",
        "information_role": information_role,
        "title": title,
        "status": status,
        "owner": "Christoph Peters",
        "created": created,
        "revised": revised,
        "language": "de",
    }
    if canonical_path is not None:
        result["canonical_path"] = canonical_path
    result.update(extra)
    return result


ARCHITECTURE_PATH = f"{PROJECT_ROOT}/Architektur und Wiederverwendungsgrenzen.md"
ARCHIVE_MVP_SOURCE = f"{PROJECT_ROOT}/Archive/MVP Scope und Abnahmekriterien.md"
ARCHIVE_MVP_TARGET = (
    f"{PROJECT_ROOT}/Archive/"
    "mvp-scope@1.0 MVP Scope und Abnahmekriterien.md"
)
DECISIONS_PATH = f"{PROJECT_ROOT}/Entscheidungen Risiken und offene Fragen.md"
GOLDEN_SOURCE = f"{PROJECT_ROOT}/Golden-Truth-Matrix.md"
GOLDEN_TARGET = (
    f"{PROJECT_ROOT}/"
    "Golden-Truth-Matrix – Source-to-Knowledge Core MVP Mini-Dossier.md"
)
GAP_PATH = f"{PROJECT_ROOT}/IST-Stand und Gap-Analyse.md"
MVP_PATH = f"{PROJECT_ROOT}/MVP Scope und Abnahmekriterien.md"
PLAN_PATH = f"{PROJECT_ROOT}/Projektplan und Arbeitspakete.md"
READINESS_PATH = (
    f"{PROJECT_ROOT}/Reports/"
    "Initial-Readiness-Report – cp-wiki Tools DEV - cpKnowledgeTools.md"
)
VALIDATION_PATH = f"{PROJECT_ROOT}/Validierungs- und Evaluationsplan.md"

MIGRATIONS = (
    MigrationSpec(
        source_path=ARCHITECTURE_PATH,
        target_path=ARCHITECTURE_PATH,
        expected_frontmatter=_expected_frontmatter(
            information_role="architecture_and_reuse_boundaries",
            title="Architektur und Wiederverwendungsgrenzen",
            status="working",
            created="2026-07-28",
            revised="2026-08-08",
            canonical_path=ARCHITECTURE_PATH,
        ),
        expected_body_sha256=(
            "cae59f9280fcae73efd9b282038075af8565c5592f16e0f6a2721fd325ad8d23"
        ),
        updates={
            "document_key": "architecture",
            "version": "1.0",
            "revised": MIGRATION_DATE,
        },
    ),
    MigrationSpec(
        source_path=ARCHIVE_MVP_SOURCE,
        target_path=ARCHIVE_MVP_TARGET,
        expected_frontmatter=_expected_frontmatter(
            information_role="mvp_scope_and_acceptance",
            title="MVP Scope und Abnahmekriterien",
            status="working",
            created="2026-07-28",
            revised="2026-07-28",
            canonical_path=MVP_PATH,
        ),
        expected_body_sha256=(
            "5a90952f555afa0cfe31d7bb9b7a04db591a4837a1d73115b70e649f857d229c"
        ),
        updates={
            "document_key": "mvp-scope",
            "version": "1.0",
            "status": "superseded",
            "revised": MIGRATION_DATE,
            "canonical_path": ARCHIVE_MVP_TARGET,
        },
    ),
    MigrationSpec(
        source_path=DECISIONS_PATH,
        target_path=DECISIONS_PATH,
        expected_frontmatter=_expected_frontmatter(
            information_role="decisions_risks_open_questions",
            title="Entscheidungen Risiken und offene Fragen",
            status="working",
            created="2026-07-28",
            revised="2026-07-28",
            canonical_path=DECISIONS_PATH,
        ),
        expected_body_sha256=(
            "fecea49fa97b43a41eb56ca6774af87a2b82692e912c85514ae208e0dd999508"
        ),
        updates={
            "document_key": "decisions-risks-open-questions",
            "version": "1.0",
            "revised": MIGRATION_DATE,
        },
    ),
    MigrationSpec(
        source_path=GOLDEN_SOURCE,
        target_path=GOLDEN_TARGET,
        expected_frontmatter=_expected_frontmatter(
            information_role="golden_truth_matrix",
            title="Golden-Truth-Matrix – Source-to-Knowledge Core MVP Mini-Dossier",
            status="working",
            created="2026-08-08",
            revised="2026-08-08",
            proposed_canonical_path=GOLDEN_SOURCE,
            source_test_design="EXPECTED.md",
            decision_basis=["CPKS-DEC-028@1.0"],
            contract_alignment=[
                "CPKS-SPEC-SRC@0.2",
                "CPKS-SPEC-KM@0.20",
                "CPKS-SPEC-KM-VOC@0.1",
                "CPKS-SPEC-KM-PU@0.1",
                "CPKS-TPL-KM-PU@0.1",
            ],
        ),
        expected_body_sha256=(
            "276131e468ff2885053de1092a03f0600463d23e034d8c8045ff7d7136942d8b"
        ),
        updates={
            "document_key": "golden-truth-matrix",
            "version": "1.0",
            "revised": MIGRATION_DATE,
            "canonical_path": GOLDEN_TARGET,
        },
    ),
    MigrationSpec(
        source_path=GAP_PATH,
        target_path=GAP_PATH,
        expected_frontmatter=_expected_frontmatter(
            information_role="current_state_and_gap_assessment",
            title="IST-Stand und Gap-Analyse",
            status="working",
            created="2026-07-28",
            revised="2026-07-28",
            canonical_path=GAP_PATH,
        ),
        expected_body_sha256=(
            "641c126b2a844002f00331eeca91a9d8f8f8f724a2a1b20efe3001d78ae4f9e0"
        ),
        updates={
            "document_key": "current-state-gap-assessment",
            "version": "1.0",
            "as_of": "2026-07-28",
            "revised": MIGRATION_DATE,
        },
    ),
    MigrationSpec(
        source_path=MVP_PATH,
        target_path=MVP_PATH,
        expected_frontmatter=_expected_frontmatter(
            information_role="mvp_scope_and_acceptance",
            title="MVP Scope und Abnahmekriterien",
            status="active",
            created="2026-07-28",
            revised="2026-08-08",
            canonical_path=MVP_PATH,
        ),
        expected_body_sha256=(
            "cff03bfed0c85b8411990ec490cfe6770bf11c8428c7996002fbb18473f32b7c"
        ),
        updates={
            "document_key": "mvp-scope",
            "version": "1.0",
            "status": "current",
            "revised": MIGRATION_DATE,
        },
    ),
    MigrationSpec(
        source_path=PLAN_PATH,
        target_path=PLAN_PATH,
        expected_frontmatter=_expected_frontmatter(
            information_role="project_plan_and_work_packages",
            title="Projektplan und Arbeitspakete",
            status="working",
            created="2026-07-28",
            revised="2026-07-28",
            canonical_path=PLAN_PATH,
        ),
        expected_body_sha256=(
            "baf139181dd4cea604f4d2353030b6293e851a17f4481c4f140fb30f958e8e09"
        ),
        updates={
            "document_key": "project-plan",
            "version": "1.0",
            "revised": MIGRATION_DATE,
        },
    ),
    MigrationSpec(
        source_path=READINESS_PATH,
        target_path=READINESS_PATH,
        expected_frontmatter=_expected_frontmatter(
            information_role="initial_readiness_report",
            title="Initial-Readiness-Report – cp-wiki Tools DEV / cpKnowledgeTools",
            status="completed",
            created="2026-08-07",
            revised="2026-08-07",
            canonical_path=READINESS_PATH,
            primary_system="cpKnowledgeSystem",
            primary_component="cpKnowledgeTools",
            scan_date="2026-08-07",
            repository_head="9f48303a879bbe0257ced6e8049c5664a2eac4dd",
        ),
        expected_body_sha256=(
            "697a8887151285736f411ae0a5b3102852f58a921469ac2b2164860a07dce7cc"
        ),
        updates={
            "document_key": "initial-readiness",
            "version": "1.0",
            "status": "current",
            "as_of": "2026-08-07",
            "revised": MIGRATION_DATE,
        },
    ),
    MigrationSpec(
        source_path=VALIDATION_PATH,
        target_path=VALIDATION_PATH,
        expected_frontmatter=_expected_frontmatter(
            information_role="validation_and_evaluation_plan",
            title="Validierungs- und Evaluationsplan",
            status="working",
            created="2026-07-28",
            revised="2026-07-28",
            canonical_path=VALIDATION_PATH,
        ),
        expected_body_sha256=(
            "fc1733ec04edac78ed90ed6e2c105f4d6db216a7938089e3c90382f01def6757"
        ),
        updates={
            "document_key": "validation-plan",
            "version": "1.0",
            "revised": MIGRATION_DATE,
        },
    ),
)


def _normalize(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _body_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise MigrationError("Expected YAML frontmatter at the beginning of the file.")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise MigrationError("YAML frontmatter is not closed with '---'.")


def _safe_vault_path(vault_root: Path, relative_path: str) -> Path:
    requested = Path(relative_path)
    if requested.is_absolute() or ".." in requested.parts:
        raise MigrationError(f"Unsafe Vault-relative path: {relative_path}")
    path = vault_root / requested
    resolved_parent = path.parent.resolve()
    try:
        resolved_parent.relative_to(vault_root)
    except ValueError as exc:
        raise MigrationError(f"Path escapes the Vault: {relative_path}") from exc
    if path.is_symlink():
        raise MigrationError(
            "Symbolic-link migration targets are not allowed: "
            f"{relative_path}"
        )
    return path


def _validate_report(
    report_path: Path,
    expected_sha256: str,
    specs: tuple[MigrationSpec, ...],
    expected_inventory: tuple[int, int, int],
) -> str:
    try:
        raw = report_path.read_bytes()
    except OSError as exc:
        raise MigrationError(f"Could not read validator report: {exc}") from exc
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        raise MigrationError(
            "Validator report SHA-256 does not match the authorized report: "
            f"{actual_sha256} != {expected_sha256}"
        )
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MigrationError(f"Validator report is not valid JSON: {exc}") from exc

    expected_header = {
        "validator": {"name": VALIDATOR_NAME, "version": VALIDATOR_VERSION},
        "rule_basis": [RULE_SOURCE],
        "profile": "project_document_complete",
    }
    for field_name, expected in expected_header.items():
        if report.get(field_name) != expected:
            raise MigrationError(
                f"Unexpected report {field_name}: {report.get(field_name)!r}"
            )
    inventory = report.get("inventory")
    if not isinstance(inventory, dict) or (
        inventory.get("total"),
        inventory.get("current"),
        inventory.get("history"),
    ) != expected_inventory:
        raise MigrationError(f"Unexpected report inventory: {inventory!r}")
    inventory_paths = set(inventory.get("current_paths", [])) | set(
        inventory.get("history_paths", [])
    )
    expected_paths = {item.source_path for item in specs}
    if inventory_paths != expected_paths:
        raise MigrationError(
            "Report inventory does not match the migration manifest: "
            f"{sorted(inventory_paths ^ expected_paths)}"
        )
    return actual_sha256


def _render_document(frontmatter: dict[str, Any], body: str) -> bytes:
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
    )
    return ("---\n" + yaml_text + "---\n" + body).encode("utf-8")


def build_migration_plan(
    vault_root: Path,
    report_path: Path,
    *,
    specs: tuple[MigrationSpec, ...] = MIGRATIONS,
    expected_report_sha256: str = REPORT_SHA256,
    expected_inventory: tuple[int, int, int] = (9, 8, 1),
) -> MigrationPlan:
    """Validate report and source state, then build an in-memory preview."""

    vault_root = vault_root.expanduser().resolve()
    if not vault_root.is_dir():
        raise MigrationError(f"Vault root is not a directory: {vault_root}")
    report_path = report_path.expanduser().resolve()
    report_sha256 = _validate_report(
        report_path,
        expected_report_sha256,
        specs,
        expected_inventory,
    )

    operations: list[PreparedMigration] = []
    for spec in specs:
        source = _safe_vault_path(vault_root, spec.source_path)
        target = _safe_vault_path(vault_root, spec.target_path)
        if not source.is_file():
            raise MigrationError(f"Expected source file is missing: {spec.source_path}")
        if source != target and target.exists():
            raise MigrationError(
                f"Migration target already exists: {spec.target_path}"
            )
        try:
            before = source.read_bytes()
            text = before.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise MigrationError(f"Could not read {spec.source_path}: {exc}") from exc
        raw_frontmatter, body = _split_frontmatter(text)
        try:
            frontmatter = yaml.safe_load(raw_frontmatter)
        except yaml.YAMLError as exc:
            raise MigrationError(
                f"Invalid YAML in migration source {spec.source_path}: {exc}"
            ) from exc
        if not isinstance(frontmatter, dict):
            raise MigrationError(
                f"Frontmatter is not a mapping: {spec.source_path}"
            )
        if _normalize(frontmatter) != spec.expected_frontmatter:
            raise MigrationError(
                f"Frontmatter drift detected: {spec.source_path}"
            )
        body_fingerprint = _body_sha256(body)
        if body_fingerprint != spec.expected_body_sha256:
            raise MigrationError(
                "Document body drift detected: "
                f"{spec.source_path} ({body_fingerprint} != "
                f"{spec.expected_body_sha256})"
            )

        updated = dict(_normalize(frontmatter))
        updated.update(spec.updates)
        after = _render_document(updated, body)
        diff = "".join(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                after.decode("utf-8").splitlines(keepends=True),
                fromfile=f"a/{spec.source_path}",
                tofile=f"b/{spec.target_path}",
            )
        )
        operations.append(
            PreparedMigration(
                source_path=source,
                target_path=target,
                relative_source=spec.source_path,
                relative_target=spec.target_path,
                before=before,
                after=after,
                diff=diff,
            )
        )

    return MigrationPlan(
        vault_root=vault_root,
        report_path=report_path,
        report_sha256=report_sha256,
        operations=tuple(operations),
    )


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def apply_migration(plan: MigrationPlan, confirmation_sha256: str) -> None:
    """Apply one fully preflighted migration transaction."""

    if confirmation_sha256 != plan.report_sha256:
        raise MigrationError(
            "Apply confirmation must equal the authorized report SHA-256."
        )
    for operation in plan.operations:
        if not operation.source_path.is_file():
            raise MigrationError(
                f"Source disappeared before apply: {operation.relative_source}"
            )
        if operation.source_path.read_bytes() != operation.before:
            raise MigrationError(
                f"Source drifted after preview: {operation.relative_source}"
            )
        if (
            operation.source_path != operation.target_path
            and operation.target_path.exists()
        ):
            raise MigrationError(
                f"Target appeared after preview: {operation.relative_target}"
            )

    temporary_paths: dict[PreparedMigration, Path] = {}
    committed: list[PreparedMigration] = []
    try:
        for operation in plan.operations:
            temporary = operation.target_path.with_name(
                f".{operation.target_path.name}.pdoc-{uuid.uuid4().hex}.tmp"
            )
            _write_exclusive(temporary, operation.after)
            temporary_paths[operation] = temporary

        for operation in plan.operations:
            temporary = temporary_paths[operation]
            os.replace(temporary, operation.target_path)
            committed.append(operation)
            if operation.source_path != operation.target_path:
                operation.source_path.unlink()
    except Exception as exc:
        for operation in reversed(committed):
            if (
                operation.source_path != operation.target_path
                and operation.target_path.exists()
            ):
                operation.target_path.unlink()
            rollback = operation.source_path.with_name(
                f".{operation.source_path.name}.rollback-{uuid.uuid4().hex}.tmp"
            )
            _write_exclusive(rollback, operation.before)
            os.replace(rollback, operation.source_path)
        for temporary in temporary_paths.values():
            if temporary.exists():
                temporary.unlink()
        raise MigrationError(f"Apply failed and was rolled back: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or apply the report-bound PDOC 0.1 migration. "
            "Dry run is the default."
        )
    )
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the exact preflighted migration instead of previewing it.",
    )
    parser.add_argument(
        "--confirm-report-sha256",
        default="",
        help="Required with --apply; must equal the authorized report SHA-256.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = build_migration_plan(args.vault, args.report)
    except MigrationError as exc:
        print(f"MIGRATION PREFLIGHT FAILED: {exc}", file=sys.stderr)
        return 2

    print("PDOC 0.1 report-bound migration preflight passed.")
    print(f"Report SHA-256: {plan.report_sha256}")
    print(f"Files: {len(plan.operations)}")
    print(
        "Renames: "
        + str(
            sum(
                item.relative_source != item.relative_target
                for item in plan.operations
            )
        )
    )
    for operation in plan.operations:
        print(operation.diff, end="" if operation.diff.endswith("\n") else "\n")

    if not args.apply:
        print("DRY RUN ONLY: no cp-wiki file was changed.")
        return 0
    try:
        apply_migration(plan, args.confirm_report_sha256)
    except MigrationError as exc:
        print(f"MIGRATION APPLY FAILED: {exc}", file=sys.stderr)
        return 2
    print("Migration applied. No Git commit or push was performed.")
    print(
        "Required next step: rerun validate_cpwiki_project_documents_v1.py "
        "with project_document_complete."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
