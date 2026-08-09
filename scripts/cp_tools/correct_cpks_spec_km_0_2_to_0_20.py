#!/usr/bin/env python3
"""
Controlled cp-wiki identity correction:
    CPKS-SPEC-KM@0.2  ->  CPKS-SPEC-KM@0.20

Purpose
-------
Correct the accidentally written concrete version "0.2" to the intended
segment-based version "0.20" after predecessor CPKS-SPEC-KM@0.15.

This is treated as an identity correction of the existing active concrete
version, NOT as creation of a new material revision. Therefore the script:
- changes the active CPKS-SPEC-KM frontmatter version from "0.2" to "0.20";
- changes exact CPKS-SPEC-KM@0.2 references in current documents
  (status active/draft/proposed) to CPKS-SPEC-KM@0.20;
- corrects the one self-description "Die Version `0.2` definiert damit ..."
  inside CPKS-SPEC-KM itself;
- preserves completed reports and Archive/History documents as historical
  evidence of the state observed at their time;
- creates no supersession relation and no new artifact file;
- runs Managed Artifact Validator v3.2 after the change;
- rolls back automatically if new blocking validator errors are introduced
  or if the CPKS-SPEC-KM monotonic-version errors remain.

Safety
------
Default mode is --check. Use --apply for writes.
All touched files are backed up before mutation.
No Git commit/push is performed.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
import unicodedata

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required. Run this script with the cpKnowledgeTools .venv Python."
    ) from exc


DEFAULT_VAULT = Path("/Users/cp/Documents/cp-wiki")
DEFAULT_REPO = Path("/Users/cp/Developer/cpKnowledgeTools")
DEFAULT_BACKUP_ROOT = Path("/Users/cp/Backups/cp-wiki/Remediation")

VALIDATOR_REL = Path(
    "scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py"
)

TARGET_REL = Path(
    "Systems/cpKnowledgeSystem/Architecture/"
    "CPKS-SPEC-KM Core Knowledge Model Specification.md"
)

OLD_REF = "CPKS-SPEC-KM@0.2"
NEW_REF = "CPKS-SPEC-KM@0.20"
OLD_VERSION = "0.2"
NEW_VERSION = "0.20"

# Important: OLD_REF is a textual prefix of NEW_REF. Never use plain
# substring membership for identity checks. Match the complete version token.
OLD_REF_RE = re.compile(r"CPKS-SPEC-KM@0\.2(?![0-9.])")

CURRENT_STATUSES = {"active", "draft", "proposed"}


class CorrectionError(RuntimeError):
    pass


def normalize_nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise CorrectionError("YAML frontmatter is not closed.")


def parse_frontmatter(text: str) -> dict[str, Any]:
    raw, _ = split_frontmatter(text)
    if raw is None:
        return {}
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise CorrectionError(f"Invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise CorrectionError("YAML frontmatter must be a mapping.")
    return data


def version_as_text(fm: dict[str, Any]) -> str | None:
    value = fm.get("version")
    if value is None:
        return None
    return str(value)


def set_version_field(text: str, version: str) -> str:
    raw, body = split_frontmatter(text)
    if raw is None:
        raise CorrectionError("Target artifact has no YAML frontmatter.")

    pattern = re.compile(r'(?m)^version:\s*.*$')
    matches = pattern.findall(raw)
    if len(matches) != 1:
        raise CorrectionError(
            f"Expected exactly one top-level version field; found {len(matches)}."
        )

    raw = pattern.sub(f'version: "{version}"', raw, count=1)
    return f"---\n{raw.rstrip()}\n---\n{body}"


def classify_reference_document(vault: Path, path: Path, text: str) -> str:
    rel = path.relative_to(vault).as_posix()

    if path == vault / TARGET_REL:
        return "update"

    # Historical lifecycle zones are immutable evidence for this correction.
    if "/Archive/" in rel or "/History/" in rel:
        return "preserve"

    fm = parse_frontmatter(text)
    if not fm:
        raise CorrectionError(
            f"Unclassified {OLD_REF} occurrence without frontmatter: {rel}"
        )

    status = fm.get("status")
    if status in CURRENT_STATUSES:
        return "update"

    # Completed reports and other terminal/non-current documents preserve the
    # version string that was true at their observation time.
    return "preserve"


def inventory_occurrences(vault: Path) -> tuple[list[Path], list[Path]]:
    update: list[Path] = []
    preserve: list[Path] = []

    for path in vault.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not OLD_REF_RE.search(text):
            continue
        classification = classify_reference_document(vault, path, text)
        if classification == "update":
            update.append(path)
        else:
            preserve.append(path)

    target = vault / TARGET_REL
    if target not in update:
        raise CorrectionError(
            f"Target artifact does not contain expected exact reference {OLD_REF}: {TARGET_REL}"
        )

    return sorted(set(update)), sorted(set(preserve))


def assert_target_preconditions(vault: Path) -> None:
    target = vault / TARGET_REL
    if not target.is_file():
        raise CorrectionError(f"Target artifact not found: {target}")

    text = target.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)

    expected = {
        "document_type": "specification",
        "specification_id": "CPKS-SPEC-KM",
        "version": OLD_VERSION,
        "status": "active",
        "evidence_class": "active_constraint",
        "source_artifact": "CPKS-SPEC-KM@0.15",
    }

    actual = {
        "document_type": fm.get("document_type"),
        "specification_id": fm.get("specification_id"),
        "version": version_as_text(fm),
        "status": fm.get("status"),
        "evidence_class": fm.get("evidence_class"),
        "source_artifact": fm.get("source_artifact"),
    }

    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            raise CorrectionError(
                f"Target precondition failed for {key}: "
                f"actual={actual.get(key)!r}, expected={expected_value!r}"
            )

    if text.count("Die Version `0.2` definiert damit") != 1:
        raise CorrectionError(
            "Expected exactly one target self-description "
            "'Die Version `0.2` definiert damit'."
        )


def assert_no_existing_0_20(vault: Path) -> None:
    conflicts: list[str] = []
    for path in vault.rglob("*.md"):
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (
            fm.get("document_type") == "specification"
            and fm.get("specification_id") == "CPKS-SPEC-KM"
            and version_as_text(fm) == NEW_VERSION
        ):
            conflicts.append(path.relative_to(vault).as_posix())

    if conflicts:
        raise CorrectionError(
            "CPKS-SPEC-KM@0.20 already exists; refusing identity correction:\n- "
            + "\n- ".join(conflicts)
        )


def patch_target(text: str) -> str:
    text = set_version_field(text, NEW_VERSION)

    count = len(OLD_REF_RE.findall(text))
    if count < 1:
        raise CorrectionError(
            f"Target artifact contains no exact {OLD_REF} reference after version-field edit."
        )
    text = OLD_REF_RE.sub(NEW_REF, text)

    old_phrase = "Die Version `0.2` definiert damit"
    new_phrase = "Die Version `0.20` definiert damit"
    if text.count(old_phrase) != 1:
        raise CorrectionError(
            f"Expected exactly one target self-description {old_phrase!r}."
        )
    text = text.replace(old_phrase, new_phrase, 1)
    return text


def patch_reference_document(text: str) -> str:
    if not OLD_REF_RE.search(text):
        raise CorrectionError(
            "Reference document no longer contains the expected exact old reference."
        )
    return OLD_REF_RE.sub(NEW_REF, text)


def backup_files(vault: Path, paths: list[Path], backup_dir: Path) -> None:
    root = backup_dir / "vault_before"
    for path in paths:
        rel = path.relative_to(vault)
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def rollback_files(vault: Path, paths: list[Path], backup_dir: Path) -> None:
    root = backup_dir / "vault_before"
    for path in paths:
        rel = path.relative_to(vault)
        backup = root / rel
        if not backup.is_file():
            raise CorrectionError(f"Rollback backup missing: {backup}")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, path)


def extract_report_dir(stdout: str) -> Path:
    for line in stdout.splitlines():
        if line.startswith("Report directory:"):
            return Path(line.split(":", 1)[1].strip())
    raise CorrectionError("Validator output did not contain a report directory.")


def run_validator(repo: Path, vault: Path) -> tuple[Path, dict[str, Any], str]:
    python_exe = repo / ".venv/bin/python"
    validator = repo / VALIDATOR_REL

    if not python_exe.is_file():
        raise CorrectionError(f"Repository Python not found: {python_exe}")
    if not validator.is_file():
        raise CorrectionError(f"Validator v3.2 not found: {validator}")

    proc = subprocess.run(
        [str(python_exe), str(validator), "--vault", str(vault)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode != 0:
        raise CorrectionError(
            f"Validator execution failed with exit code {proc.returncode}:\n{proc.stdout}"
        )

    report_dir = extract_report_dir(proc.stdout)
    report_json = report_dir / "validation-report-v3-2.json"
    if not report_json.is_file():
        raise CorrectionError(f"Validator report not found: {report_json}")

    data = json.loads(report_json.read_text(encoding="utf-8"))
    return report_dir, data, proc.stdout


def error_counter(data: dict[str, Any]) -> Counter:
    result: Counter = Counter()
    for finding in data.get("findings", []):
        if finding.get("severity") != "error":
            continue
        result[
            (
                normalize_nfc(str(finding.get("path", ""))),
                str(finding.get("code", "")),
            )
        ] += 1
    return result


def km_monotonic_errors(data: dict[str, Any]) -> list[dict[str, Any]]:
    target = normalize_nfc(TARGET_REL.as_posix())
    return [
        finding
        for finding in data.get("findings", [])
        if finding.get("severity") == "error"
        and normalize_nfc(str(finding.get("path", ""))) == target
        and finding.get("code") == "non_monotonic_artifact_version_sequence"
    ]


def current_old_reference_files(vault: Path) -> list[str]:
    remaining: list[str] = []
    for path in vault.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not OLD_REF_RE.search(text):
            continue
        if classify_reference_document(vault, path, text) == "update":
            remaining.append(path.relative_to(vault).as_posix())
    return sorted(remaining)


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    vault = args.vault.expanduser().resolve()
    repo = args.repo.expanduser().resolve()

    if not vault.is_dir():
        raise CorrectionError(f"Vault not found: {vault}")
    if not repo.is_dir():
        raise CorrectionError(f"Repository not found: {repo}")
    if not (repo / VALIDATOR_REL).is_file():
        raise CorrectionError(f"Validator v3.2 not found: {repo / VALIDATOR_REL}")

    assert_target_preconditions(vault)
    assert_no_existing_0_20(vault)
    update_paths, preserve_paths = inventory_occurrences(vault)

    return {
        "vault": vault,
        "repo": repo,
        "update_paths": update_paths,
        "preserve_paths": preserve_paths,
    }


def print_plan(ctx: dict[str, Any]) -> None:
    vault: Path = ctx["vault"]
    update_paths: list[Path] = ctx["update_paths"]
    preserve_paths: list[Path] = ctx["preserve_paths"]

    print("CHECK PASSED.")
    print("Identity correction:")
    print(f"  {OLD_REF} -> {NEW_REF}")
    print()
    print(f"Current files to update: {len(update_paths)}")
    for path in update_paths:
        print(f"  UPDATE   {path.relative_to(vault).as_posix()}")
    print()
    print(f"Historical/non-current files preserved: {len(preserve_paths)}")
    for path in preserve_paths:
        print(f"  PRESERVE {path.relative_to(vault).as_posix()}")
    print()
    print("No Vault files were changed.")


def apply(args: argparse.Namespace, ctx: dict[str, Any]) -> dict[str, Any]:
    vault: Path = ctx["vault"]
    repo: Path = ctx["repo"]
    update_paths: list[Path] = ctx["update_paths"]
    preserve_paths: list[Path] = ctx["preserve_paths"]

    # Establish a blocking-error baseline before mutation.
    pre_report_dir, pre_data, pre_stdout = run_validator(repo, vault)
    pre_errors = error_counter(pre_data)

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    backup_dir = (
        args.backup_root.expanduser().resolve()
        / f"{timestamp}-cpks-spec-km-0.2-to-0.20"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    backup_files(vault, update_paths, backup_dir)
    (backup_dir / "pre-validator-stdout.txt").write_text(
        pre_stdout, encoding="utf-8"
    )

    manifest = {
        "created_at": dt.datetime.now().astimezone().isoformat(),
        "operation": "identity_correction",
        "artifact": "CPKS-SPEC-KM",
        "old_version": OLD_VERSION,
        "new_version": NEW_VERSION,
        "old_reference": OLD_REF,
        "new_reference": NEW_REF,
        "vault": str(vault),
        "repo": str(repo),
        "pre_validator_report_dir": str(pre_report_dir),
        "updated_files": [
            path.relative_to(vault).as_posix() for path in update_paths
        ],
        "preserved_historical_or_noncurrent_files": [
            path.relative_to(vault).as_posix() for path in preserve_paths
        ],
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    try:
        for path in update_paths:
            original = path.read_text(encoding="utf-8")
            if path == vault / TARGET_REL:
                patched = patch_target(original)
            else:
                patched = patch_reference_document(original)

            if patched == original:
                raise CorrectionError(
                    f"Expected change produced no diff: {path.relative_to(vault)}"
                )
            path.write_text(patched, encoding="utf-8")

        # Direct post-write identity checks before validator.
        target_text = (vault / TARGET_REL).read_text(encoding="utf-8")
        target_fm = parse_frontmatter(target_text)

        if version_as_text(target_fm) != NEW_VERSION:
            raise CorrectionError(
                f"Post-write target version is {version_as_text(target_fm)!r}, "
                f"expected {NEW_VERSION!r}."
            )
        if OLD_REF_RE.search(target_text):
            raise CorrectionError(f"Target still contains exact old reference {OLD_REF}.")
        if "Die Version `0.2` definiert damit" in target_text:
            raise CorrectionError("Target still contains old self-description.")

        remaining_current = current_old_reference_files(vault)
        if remaining_current:
            raise CorrectionError(
                f"{OLD_REF} remains in current documents:\n- "
                + "\n- ".join(remaining_current)
            )

        post_report_dir, post_data, post_stdout = run_validator(repo, vault)
        (backup_dir / "post-validator-stdout.txt").write_text(
            post_stdout, encoding="utf-8"
        )

        post_errors = error_counter(post_data)

        introduced = {
            key: post_count - pre_errors.get(key, 0)
            for key, post_count in post_errors.items()
            if post_count > pre_errors.get(key, 0)
        }
        if introduced:
            details = "\n".join(
                f"- +{count} {code}: {path}"
                for (path, code), count in sorted(introduced.items())
            )
            raise CorrectionError(
                "Identity correction introduced new blocking validator errors:\n"
                + details
            )

        residual_km = km_monotonic_errors(post_data)
        if residual_km:
            raise CorrectionError(
                "CPKS-SPEC-KM still has non_monotonic_artifact_version_sequence "
                "after correction."
            )

        result = {
            "backup_dir": str(backup_dir),
            "pre_validator_report_dir": str(pre_report_dir),
            "post_validator_report_dir": str(post_report_dir),
            "updated_file_count": len(update_paths),
            "preserved_file_count": len(preserve_paths),
            "old_reference_remaining_in_current_documents": 0,
            "km_non_monotonic_errors_remaining": 0,
            "overall_post_validator_summary": post_data.get("summary", {}),
        }
        (backup_dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return result

    except Exception:
        rollback_files(vault, update_paths, backup_dir)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Correct CPKS-SPEC-KM@0.2 to CPKS-SPEC-KM@0.20 and propagate "
            "current exact references."
        )
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Preflight only. This is the default.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply the correction, validate, and rollback on failure.",
    )

    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.apply:
        args.check = True

    ctx = preflight(args)

    if args.check:
        print_plan(ctx)
        return 0

    result = apply(args, ctx)
    print("IDENTITY CORRECTION APPLIED.")
    print(f"  {OLD_REF} -> {NEW_REF}")
    print(f"Updated files:          {result['updated_file_count']}")
    print(f"Preserved files:        {result['preserved_file_count']}")
    print(f"Backup:                 {result['backup_dir']}")
    print(f"Post-validator report:  {result['post_validator_report_dir']}")
    print("Current old references: 0")
    print("KM monotonic errors:    0")
    print(
        "Overall validator summary: "
        f"{result['overall_post_validator_summary']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CorrectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
