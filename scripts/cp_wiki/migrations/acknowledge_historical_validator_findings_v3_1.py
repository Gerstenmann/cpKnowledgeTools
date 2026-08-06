#!/usr/bin/env python3
"""
Acknowledge reviewed historical validator findings in cp-wiki.

This is a controlled one-time metadata migration for the findings reported by
validator revision 3 on 2026-07-26T23:13:34.788366+02:00.

Canonical script location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/migrations/
  acknowledge_historical_validator_findings_v3_1.py

Default: dry run.
Use --apply to write changes.

The script:
- modifies only the explicit manifest of historical, closed-Development and
  legacy-support documents;
- adds validation_acknowledgement metadata;
- does not modify active or current-Development artifacts;
- does not suppress future unknown findings;
- does not suppress errors;
- creates recovery copies and a migration report outside the Vault;
- does not commit or push.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required in the cpKnowledgeTools environment. "
        "Install it with: .venv/bin/python -m pip install PyYAML"
    ) from exc


VAULT = Path("/Users/cp/Documents/cp-wiki")
TOOLS = Path("/Users/cp/Developer/cpKnowledgeTools")
CANONICAL_SCRIPT = (
    TOOLS / "scripts/cp_wiki/migrations/"
    "acknowledge_historical_validator_findings_v3_1.py"
)
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/migrations"
)

SOURCE_REPORT_GENERATED_AT = "2026-07-26T23:13:34.788366+02:00"
REVIEWED_BY = "Christoph Peters"
REVIEWED_AT = "2026-07-26"
RATIONALE = (
    "Historische Metadatenabweichungen wurden geprüft, zur Kenntnis genommen "
    "und nach Vorliegen aktueller Nachfolgeartefakte als abgeschlossen akzeptiert."
)

MANIFEST: dict[str, list[str]] = {
    "Development/cpKnowledgeSystem/Governance/Draft Decisions/CPKS-DEC-012@1.0 Governance Artifact Consolidation and Dependency Management.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Development/cpKnowledgeSystem/Governance/Draft Decisions/CPKS-DEC-014@0.1 Organisation des Governance-Prozessregisters und der Prozessbeschreibungen.md": [
        "invalid_affected_artifact_reference",
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Development/cpKnowledgeSystem/Governance/Draft Decisions/CPKS-DEC-019@0.1 Governance Artifact Naming, Versioning and Lifecycle Placement.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Development/cpKnowledgeSystem/Governance/Draft Processes/Archive/GOV-P01@0.2 Governance Artifact Consolidation and Impact Review.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Development/cpKnowledgeSystem/Governance/Reviews/GOV-P01 v0.2 Governance Review.md": [
        "legacy_artifact_id_resolved"
    ],
    "Development/cpKnowledgeSystem/Governance/Reviews/Preflights/CPKS-BASELINE Update Preflight v0.2.md": [
        "invalid_affected_artifact_reference",
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Development/cpKnowledgeSystem/Governance/Reviews/Preflights/CPKS-BL@0.4 Baseline Update Preflight.md": [
        "invalid_affected_artifact_reference"
    ],
    "Development/cpKnowledgeSystem/Governance/Reviews/Preflights/CPKS-DEC-017 Activation and Impact Preflight v0.1.md": [
        "invalid_affected_artifact_reference",
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Development/cpKnowledgeSystem/Governance/Reviews/Preflights/CPKS-FWK-AI-WORKING 0.3 Preflight v0.2.md": [
        "invalid_affected_artifact_reference",
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Development/cpKnowledgeSystem/Governance/Reviews/Preflights/CPKS-FWK-AI-WORKING 0.3 Preflight.md": [
        "affected_artifacts_missing_on_legacy_change_artifact",
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Development/cpKnowledgeSystem/Governance/Reviews/Preflights/GOV-P01 v0.1 Preflight v0.2.md": [
        "affected_artifacts_missing_on_legacy_change_artifact",
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
        "legacy_target_artifact_descriptor",
        "unknown_target_artifact_descriptor_field",
    ],
    "Development/cpKnowledgeSystem/Governance/Reviews/Preflights/GOV-P01 v0.1 Preflight.md": [
        "affected_artifacts_missing_on_legacy_change_artifact",
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
        "legacy_target_artifact_descriptor",
        "unknown_target_artifact_descriptor_field",
    ],
    "Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.2 cpKnowledgeSystem Authoritative Baseline.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.3 cpKnowledgeSystem Authoritative Baseline.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Systems/cpKnowledgeSystem/Governance/Archive/Frameworks/CPKS-FWK-AIW@0.2 AI Working Governance Framework.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Systems/cpKnowledgeSystem/Governance/Archive/Frameworks/CPKS-FWK-AIW@0.3 AI Working Governance Framework.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Systems/cpKnowledgeSystem/Governance/Decisions/History/CPKS-DEC-012@1.1 Governance Artifact Consolidation and Dependency Management.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
    "Systems/cpKnowledgeSystem/Governance/Decisions/History/CPKS-DEC-014@1.0 Organisation des Governance-Prozessregisters und der Prozessbeschreibungen.md": [
        "invalid_reference_form",
        "legacy_artifact_id_resolved",
    ],
}

MANAGED_TYPES = {
    "baseline",
    "decision_record",
    "policy",
    "framework",
    "specification",
    "process",
    "work_package",
    "template",
    "manual",
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
TERMINAL_STATUSES = {
    "withdrawn",
    "superseded",
    "deprecated",
    "archived",
    "rejected",
    "completed",
    "cancelled",
}


class MigrationError(RuntimeError):
    pass


def assert_canonical_script_location() -> None:
    actual = Path(__file__).resolve()
    expected = CANONICAL_SCRIPT.resolve()
    if actual != expected:
        raise MigrationError(
            "Script is not in its canonical repository location.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )


def split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise MigrationError("Missing YAML frontmatter.")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise MigrationError("Unclosed YAML frontmatter.")


def parse_frontmatter(raw: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise MigrationError(f"Invalid YAML frontmatter: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MigrationError("Frontmatter must be a YAML mapping.")
    return parsed


def is_eligible(relative_path: str, frontmatter: dict[str, Any]) -> bool:
    document_type = str(frontmatter.get("document_type") or "")
    status = str(frontmatter.get("status") or "")

    if status == "active":
        return False

    if document_type in MANAGED_TYPES:
        return (
            status in TERMINAL_STATUSES
            or "/Archive/" in relative_path
            or "/History/" in relative_path
        )

    if document_type in SUPPORT_TYPES:
        return relative_path.startswith("Development/cpKnowledgeSystem/Governance/")

    return False


def acknowledgement_block(codes: list[str]) -> str:
    lines = [
        "validation_acknowledgement:",
        "  disposition: accepted_historical",
        f"  reviewed_by: {REVIEWED_BY}",
        f'  reviewed_at: "{REVIEWED_AT}"',
        f'  source_report_generated_at: "{SOURCE_REPORT_GENERATED_AT}"',
        "  accepted_codes:",
    ]
    lines.extend(f"    - {code}" for code in sorted(set(codes)))
    escaped = RATIONALE.replace('"', '\\"')
    lines.append(f'  rationale: "{escaped}"')
    return "\n".join(lines) + "\n"


def validate_existing_acknowledgement(
    frontmatter: dict[str, Any],
    expected_codes: list[str],
) -> bool:
    raw = frontmatter.get("validation_acknowledgement")
    if raw is None:
        return False
    if not isinstance(raw, dict):
        raise MigrationError(
            "Existing validation_acknowledgement is not a YAML mapping."
        )
    if raw.get("disposition") != "accepted_historical":
        raise MigrationError(
            "Existing validation_acknowledgement has another disposition."
        )
    accepted = raw.get("accepted_codes")
    if not isinstance(accepted, list):
        raise MigrationError(
            "Existing validation_acknowledgement.accepted_codes is invalid."
        )
    return set(str(item) for item in accepted) >= set(expected_codes)


def add_acknowledgement(
    text: str,
    relative_path: str,
    codes: list[str],
) -> tuple[str, str]:
    raw, body = split_frontmatter(text)
    frontmatter = parse_frontmatter(raw)

    if not is_eligible(relative_path, frontmatter):
        raise MigrationError(
            "Manifest target is not an eligible historical, closed-Development "
            f"or legacy-support document: {relative_path}"
        )

    if "validation_acknowledgement" in frontmatter:
        if validate_existing_acknowledgement(frontmatter, codes):
            return text, "already_acknowledged"
        raise MigrationError(
            "Existing acknowledgement does not cover the expected findings: "
            f"{relative_path}"
        )

    updated_raw = raw.rstrip() + "\n" + acknowledgement_block(codes)
    updated = "---\n" + updated_raw + "---\n" + body.lstrip("\n")

    parsed_updated = parse_frontmatter(split_frontmatter(updated)[0])
    if not validate_existing_acknowledgement(parsed_updated, codes):
        raise MigrationError(
            f"Post-write acknowledgement validation failed: {relative_path}"
        )
    return updated, "planned"


def unified_diff(
    before: str,
    after: str,
    relative_path: str,
) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )


def atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".acknowledgement.tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    assert_canonical_script_location()

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    mode = "apply" if args.apply else "dry-run"
    run_dir = (
        RUN_ROOT / f"{timestamp}-acknowledge-historical-validator-findings-v3-1-{mode}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    planned: list[dict[str, Any]] = []
    combined_diff: list[str] = []
    updates: dict[Path, tuple[str, str, int]] = {}

    for relative_path, codes in MANIFEST.items():
        path = VAULT / relative_path
        if not path.is_file():
            raise MigrationError(f"Manifest target is missing: {relative_path}")

        before = path.read_text(encoding="utf-8")
        after, state = add_acknowledgement(before, relative_path, codes)
        mode_bits = path.stat().st_mode & 0o777

        planned.append(
            {
                "path": relative_path,
                "state": state,
                "accepted_codes": codes,
                "before_sha256": sha256(before),
                "after_sha256": sha256(after),
            }
        )

        if after != before:
            combined_diff.append(unified_diff(before, after, relative_path))
            updates[path] = (before, after, mode_bits)

    (run_dir / "planned-changes.diff").write_text(
        "".join(combined_diff),
        encoding="utf-8",
    )
    (run_dir / "acknowledgement-manifest.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "source_report_generated_at": SOURCE_REPORT_GENERATED_AT,
                "reviewed_by": REVIEWED_BY,
                "reviewed_at": REVIEWED_AT,
                "targets": planned,
                "files_in_manifest": len(MANIFEST),
                "files_requiring_change": len(updates),
                "active_or_current_artifacts_modified": False,
                "commit_created": False,
                "push_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not args.apply:
        print("Dry run completed. No Vault files were changed.")
        print(f"Manifest files: {len(MANIFEST)}")
        print(f"Files requiring change: {len(updates)}")
        print(f"Run report: {run_dir}")
        return 0

    changed: list[Path] = []
    try:
        for path, (before, after, mode_bits) in updates.items():
            relative_path = path.relative_to(VAULT)
            recovery = run_dir / "recovery" / relative_path
            recovery.parent.mkdir(parents=True, exist_ok=True)
            recovery.write_text(before, encoding="utf-8")

            atomic_write(path, after, mode_bits)
            changed.append(path)

            raw, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            parsed = parse_frontmatter(raw)
            expected_codes = MANIFEST[relative_path.as_posix()]
            if not validate_existing_acknowledgement(parsed, expected_codes):
                raise MigrationError(f"Post-write validation failed: {relative_path}")

    except Exception:
        for path in reversed(changed):
            relative_path = path.relative_to(VAULT)
            recovery = run_dir / "recovery" / relative_path
            if recovery.is_file():
                mode_bits = path.stat().st_mode & 0o777
                atomic_write(
                    path,
                    recovery.read_text(encoding="utf-8"),
                    mode_bits,
                )
        raise

    (run_dir / "migration-report.json").write_text(
        json.dumps(
            {
                "state": "applied",
                "files_changed": len(changed),
                "files_already_acknowledged": len(MANIFEST) - len(changed),
                "source_report_generated_at": SOURCE_REPORT_GENERATED_AT,
                "active_or_current_artifacts_modified": False,
                "commit_created": False,
                "push_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print("Historical validator findings acknowledged.")
    print(f"Files changed: {len(changed)}")
    print(f"Run report: {run_dir}")
    print("No active or current-Development artifacts were modified.")
    print("No Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
