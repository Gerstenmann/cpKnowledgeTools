#!/usr/bin/env python3
"""
Aggressive cp-wiki hygiene cleanup for four known validator finding groups.

Scope
-----
1. Add the 22 known missing evidence_class values.
2. Remove the four known redundant duplicate-version Development files.
3. Correct the three remaining invalid combined evidence_class values.
4. Repair known canonical_path drift and de-manage the Process Description
   example template wrapper.

Characteristics
---------------
- pragmatic / aggressive by design
- no semantic comparison before deleting known redundant duplicate drafts
- idempotent where practical: already-clean items are skipped
- creates backups of every file before it is changed or deleted
- no automatic rollback
- no Git commit or push
- runs Managed Artifact Validator v3.2 after --apply and prints the new summary

This script intentionally does NOT address:
- missing approval metadata
- missing historical CPKS-DEC-021@0.1 / CPKS-DEC-024@0.1
- CPKT-SPEC-BLD -> CPKS-SPEC-AWB dependency
- other warnings/info diagnostics
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

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required. Run this script with the cpKnowledgeTools .venv Python."
    ) from exc


DEFAULT_VAULT = Path("/Users/cp/Documents/cp-wiki")
DEFAULT_REPO = Path("/Users/cp/Developer/cpKnowledgeTools")
DEFAULT_BACKUP_ROOT = Path("/Users/cp/Backups/cp-wiki/Hygiene")

VALIDATOR_REL = Path(
    "scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py"
)

MANAGED_ID_FIELDS = {
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

# ---------------------------------------------------------------------------
# 1. Explicit evidence_class migration map: exactly the 22 known active
#    Managed Artifacts that were missing evidence_class in validator v3.2.
# ---------------------------------------------------------------------------

EVIDENCE_CLASS_BY_ID = {
    "CPW-WP-001": "active_constraint",
    "GOV-P01": "active_constraint",
    "CPKS-FWK-AIW": "active_constraint",

    "CPKS-DEC-011": "active_constraint",
    "CPKS-DEC-012": "active_constraint",
    "CPKS-DEC-013": "active_constraint",
    "CPKS-DEC-015": "active_constraint",
    "CPKS-DEC-016": "active_constraint",
    "CPKS-DEC-017": "active_constraint",
    "CPKS-DEC-018": "active_constraint",
    "CPKS-DEC-019": "active_constraint",
    "CPKS-DEC-020": "active_constraint",
    "CPKS-DEC-021": "active_constraint",
    "CPKS-DEC-022": "active_constraint",
    "CPKS-DEC-023": "active_constraint",
    "CPKS-DEC-024": "active_constraint",
    "CPKS-DEC-025": "active_constraint",

    "CPKS-POL-GOV-AUTH": "active_constraint",
    "CPKS-SPEC-PROC": "active_constraint",
    "CPKS-SPEC-WP": "active_constraint",
    "CPW-SPEC-VLT": "active_constraint",

    # Baseline documents verified current state; status alone does not turn it
    # into active_constraint.
    "CPKS-BL": "verified_current_state",
}

assert len(EVIDENCE_CLASS_BY_ID) == 22


# ---------------------------------------------------------------------------
# 2. Four known redundant duplicate-version files to remove.
#    Their active counterparts remain untouched.
# ---------------------------------------------------------------------------

DUPLICATE_DEVELOPMENT_FILES = [
    Path(
        "Development/cp-wiki Vault/Specifications/Architecture Specification/"
        "CPW-SPEC-VLT@0.4 cp-wiki Vault Specification.md"
    ),
    Path(
        "Development/cpKnowledgeSystem/Governance/Draft Decisions/"
        "CPKS-DEC-022@0.1 Reduktion und Zerlegung der cp-wiki Vault Specification.md"
    ),
    Path(
        "Development/cpKnowledgeSystem/Specifications/"
        "CPKS-SPEC-WP@0.1 Work Package Specification.md"
    ),
    Path(
        "Development/cpKnowledgeSystem/Work Packages/Draft Work Packages/"
        "CPW-WP-001@0.1 Konsolidierung und Zerlegung der cp-wiki Vault Specification.md"
    ),
]


# ---------------------------------------------------------------------------
# 3. Three remaining invalid evidence_class values.
#    CPKS-SPEC-WP@0.1 is deliberately not here: that duplicate Draft is removed
#    by group 2.
# ---------------------------------------------------------------------------

INVALID_EVIDENCE_CLASS_FIXES = {
    Path(
        "Development/cpKnowledgeSystem/Specifications/Information Model/"
        "CPKS-SPEC-CRM@0.1 CRM and Party Model Specification.md"
    ): "design_candidate",
    Path(
        "Development/cpKnowledgeSystem/Specifications/Information Model/"
        "CPKS-SPEC-ERM@0.1 Entity and Relationship Model Specification.md"
    ): "design_candidate",
    Path(
        "Development/cpKnowledgeSystem/Specifications/Security and Operations/"
        "CPKS-SPEC-OPS@0.1 Operations and Runtime Specification.md"
    ): "design_candidate",
}


# ---------------------------------------------------------------------------
# 4a. Known canonical_path hygiene targets.
#     canonical_path is simply set to the actual Vault-relative path.
# ---------------------------------------------------------------------------

CANONICAL_PATH_TARGETS = [
    Path(
        "Development/cpKnowledgeSystem/Specifications/Validation/Archive/"
        "CPKS-SPEC-VAL@0.1 Validator and Test Profile Specification.md"
    ),
    Path(
        "Development/cp-wiki Vault/Specifications/Architecture Specification/Archive/"
        "CPW-SPEC-VLT@0.2 Obsidian cp-wiki Vault Specification.md"
    ),
    Path(
        "Development/cp-wiki Vault/Specifications/Architecture Specification/Archive/"
        "CPW-SPEC-VLT@0.3 cp-wiki Vault Specification.md"
    ),
    Path(
        "Development/cp-wiki Vault/Specifications/Architecture Specification/Archive/"
        "CPW-SPEC-VLT@0.31 cp-wiki Vault Specification.md"
    ),
]

# 4b. Template wrapper that is currently incorrectly modelled as a process.
PROCESS_TEMPLATE_REL = Path(
    "Templates/Processes/Process Description Template - Single File.md"
)


class HygieneError(RuntimeError):
    pass


def split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1:])
    raise HygieneError("YAML frontmatter is not closed.")


def parse_frontmatter(text: str) -> dict[str, Any]:
    raw, _ = split_frontmatter(text)
    if raw is None:
        return {}
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise HygieneError(f"Invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise HygieneError("YAML frontmatter must be a mapping.")
    return data


def artifact_id(fm: dict[str, Any]) -> str | None:
    doc_type = fm.get("document_type")
    id_field = MANAGED_ID_FIELDS.get(str(doc_type))
    if not id_field:
        return None
    value = fm.get(id_field)
    return str(value) if value is not None else None


def set_scalar_field(text: str, field: str, value: str) -> str:
    raw, body = split_frontmatter(text)
    if raw is None:
        raise HygieneError(f"Cannot set {field}: file has no YAML frontmatter.")

    pattern = re.compile(rf"(?m)^{re.escape(field)}:[^\n]*$")
    replacement = f"{field}: {value}"

    if pattern.search(raw):
        raw = pattern.sub(replacement, raw, count=1)
    else:
        # Put evidence_class directly after status where possible.
        if field == "evidence_class":
            status_match = re.search(r"(?m)^status:[^\n]*$", raw)
            if status_match:
                pos = status_match.end()
                raw = raw[:pos] + "\n" + replacement + raw[pos:]
            else:
                raw = raw.rstrip() + "\n" + replacement
        else:
            raw = raw.rstrip() + "\n" + replacement

    return f"---\n{raw.rstrip()}\n---\n{body}"


def find_active_managed_by_id(vault: Path, stable_id: str) -> list[Path]:
    found: list[Path] = []
    for path in vault.rglob("*.md"):
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if fm.get("status") != "active":
            continue
        if artifact_id(fm) == stable_id:
            found.append(path)
    return sorted(found)


def backup_file(vault: Path, path: Path, backup_dir: Path) -> None:
    rel = path.relative_to(vault)
    dst = backup_dir / "vault_before" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def ensure_backup_once(
    vault: Path,
    path: Path,
    backup_dir: Path,
    backed_up: set[Path],
) -> None:
    if path in backed_up:
        return
    if path.exists():
        backup_file(vault, path, backup_dir)
        backed_up.add(path)


def template_cleanup(text: str) -> str:
    raw, body = split_frontmatter(text)

    # Keep only a harmless human-facing title in the wrapper. The body remains
    # unchanged, including its explicit example markers and example YAML.
    title = "Process Description Template - Single File"
    return (
        "---\n"
        f"title: {title}\n"
        "---\n"
        + body.lstrip("\n")
    )


def extract_report_dir(stdout: str) -> Path | None:
    for line in stdout.splitlines():
        if line.startswith("Report directory:"):
            return Path(line.split(":", 1)[1].strip())
    return None


def run_validator(repo: Path, vault: Path) -> tuple[int, str, Path | None]:
    python_exe = repo / ".venv/bin/python"
    validator = repo / VALIDATOR_REL

    if not python_exe.is_file():
        raise HygieneError(f"Repository Python not found: {python_exe}")
    if not validator.is_file():
        raise HygieneError(f"Validator v3.2 not found: {validator}")

    proc = subprocess.run(
        [str(python_exe), str(validator), "--vault", str(vault), "--strict-exit"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout, extract_report_dir(proc.stdout)


def parse_validator_summary(stdout: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for key in ("Errors", "Warnings", "Info"):
        match = re.search(rf"(?m)^{key}:\s+([0-9]+)\s*$", stdout)
        if match:
            result[key.lower()] = int(match.group(1))
    return result


def build_plan(vault: Path) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "evidence_class": [],
        "duplicates_delete": [],
        "invalid_evidence_class": [],
        "canonical_path": [],
        "process_template": None,
        "notes": [],
    }

    # Group 1
    for stable_id, desired_class in EVIDENCE_CLASS_BY_ID.items():
        matches = find_active_managed_by_id(vault, stable_id)
        if not matches:
            plan["notes"].append(
                f"evidence_class: active artifact not found for {stable_id}; skipped"
            )
            continue

        # Aggressive mode: if somehow multiple active matches exist, update all.
        for path in matches:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
            current = fm.get("evidence_class")
            if current == desired_class:
                continue
            plan["evidence_class"].append(
                {
                    "path": path,
                    "stable_id": stable_id,
                    "from": current,
                    "to": desired_class,
                }
            )

    # Group 2
    for rel in DUPLICATE_DEVELOPMENT_FILES:
        path = vault / rel
        if path.exists():
            plan["duplicates_delete"].append(path)

    # Group 3
    for rel, desired_class in INVALID_EVIDENCE_CLASS_FIXES.items():
        path = vault / rel
        if not path.exists():
            continue
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        current = fm.get("evidence_class")
        if current != desired_class:
            plan["invalid_evidence_class"].append(
                {
                    "path": path,
                    "from": current,
                    "to": desired_class,
                }
            )

    # Group 4a
    for rel in CANONICAL_PATH_TARGETS:
        path = vault / rel
        if not path.exists():
            continue
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        actual_rel = path.relative_to(vault).as_posix()
        current = fm.get("canonical_path")
        if current != actual_rel:
            plan["canonical_path"].append(
                {
                    "path": path,
                    "from": current,
                    "to": actual_rel,
                }
            )

    # Group 4b
    template_path = vault / PROCESS_TEMPLATE_REL
    if template_path.exists():
        text = template_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm.get("document_type") == "process" or fm.get("process_id"):
            plan["process_template"] = template_path

    return plan


def print_plan(vault: Path, plan: dict[str, Any]) -> None:
    print("cp-wiki hygiene cleanup plan")
    print("============================")
    print()

    print(f"1. evidence_class updates: {len(plan['evidence_class'])}")
    for item in plan["evidence_class"]:
        rel = item["path"].relative_to(vault).as_posix()
        print(
            f"   {item['stable_id']}: {item['from']!r} -> {item['to']}  [{rel}]"
        )

    print()
    print(f"2. duplicate Development files to delete: {len(plan['duplicates_delete'])}")
    for path in plan["duplicates_delete"]:
        print(f"   DELETE {path.relative_to(vault).as_posix()}")

    print()
    print(
        "3. invalid evidence_class corrections: "
        f"{len(plan['invalid_evidence_class'])}"
    )
    for item in plan["invalid_evidence_class"]:
        print(
            f"   {item['path'].relative_to(vault).as_posix()}: "
            f"{item['from']!r} -> {item['to']}"
        )

    print()
    print(f"4a. canonical_path corrections: {len(plan['canonical_path'])}")
    for item in plan["canonical_path"]:
        print(
            f"   {item['path'].relative_to(vault).as_posix()}: "
            f"{item['from']!r} -> {item['to']!r}"
        )

    print()
    print(
        "4b. Process template cleanup: "
        + ("1" if plan["process_template"] else "0")
    )
    if plan["process_template"]:
        print(
            "   DE-MANAGE "
            + plan["process_template"].relative_to(vault).as_posix()
        )

    if plan["notes"]:
        print()
        print("Notes:")
        for note in plan["notes"]:
            print(f"   - {note}")


def apply_plan(
    vault: Path,
    plan: dict[str, Any],
    backup_dir: Path,
) -> dict[str, int]:
    backed_up: set[Path] = set()
    counts = Counter()

    # Group 1
    for item in plan["evidence_class"]:
        path: Path = item["path"]
        ensure_backup_once(vault, path, backup_dir, backed_up)
        text = path.read_text(encoding="utf-8")
        patched = set_scalar_field(text, "evidence_class", item["to"])
        path.write_text(patched, encoding="utf-8")
        counts["evidence_class_updated"] += 1

    # Group 2: aggressive removal, no semantic comparison.
    for path in plan["duplicates_delete"]:
        ensure_backup_once(vault, path, backup_dir, backed_up)
        path.unlink()
        counts["duplicate_files_deleted"] += 1

    # Group 3
    for item in plan["invalid_evidence_class"]:
        path: Path = item["path"]
        ensure_backup_once(vault, path, backup_dir, backed_up)
        text = path.read_text(encoding="utf-8")
        patched = set_scalar_field(text, "evidence_class", item["to"])
        path.write_text(patched, encoding="utf-8")
        counts["invalid_evidence_class_fixed"] += 1

    # Group 4a
    for item in plan["canonical_path"]:
        path: Path = item["path"]
        ensure_backup_once(vault, path, backup_dir, backed_up)
        text = path.read_text(encoding="utf-8")
        patched = set_scalar_field(text, "canonical_path", item["to"])
        path.write_text(patched, encoding="utf-8")
        counts["canonical_path_fixed"] += 1

    # Group 4b
    template_path = plan["process_template"]
    if template_path:
        ensure_backup_once(vault, template_path, backup_dir, backed_up)
        text = template_path.read_text(encoding="utf-8")
        template_path.write_text(template_cleanup(text), encoding="utf-8")
        counts["process_template_cleaned"] += 1

    return dict(counts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggressive cleanup of four known cp-wiki hygiene finding groups."
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Show planned changes only. This is the default.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply the cleanup, create backups, then run validator v3.2.",
    )

    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.apply:
        args.check = True

    vault = args.vault.expanduser().resolve()
    repo = args.repo.expanduser().resolve()

    if not vault.is_dir():
        raise HygieneError(f"Vault not found: {vault}")
    if not repo.is_dir():
        raise HygieneError(f"Repository not found: {repo}")

    plan = build_plan(vault)
    print_plan(vault, plan)

    if args.check:
        print()
        print("CHECK ONLY: no Vault files changed.")
        return 0

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    backup_dir = (
        args.backup_root.expanduser().resolve()
        / f"{timestamp}-managed-artifact-hygiene"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "created_at": dt.datetime.now().astimezone().isoformat(),
        "mode": "aggressive_hygiene",
        "vault": str(vault),
        "repo": str(repo),
        "scope": [
            "22 missing_evidence_class",
            "4 known duplicate-version Development files",
            "3 remaining invalid_evidence_class",
            "known canonical_path + Process template hygiene",
        ],
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    counts = apply_plan(vault, plan, backup_dir)

    print()
    print("HYGIENE CHANGES APPLIED.")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")
    print(f"  backup: {backup_dir}")

    print()
    print("Running Managed Artifact Validator v3.2...")
    returncode, stdout, report_dir = run_validator(repo, vault)
    print(stdout, end="" if stdout.endswith("\n") else "\n")

    summary = parse_validator_summary(stdout)
    result = {
        "applied_counts": counts,
        "validator_exit_code": returncode,
        "validator_summary": summary,
        "validator_report_dir": str(report_dir) if report_dir else None,
    }
    (backup_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Important: validator errors are expected to remain because this script
    # intentionally does not address every finding. Do not roll back.
    print()
    print("Cleanup complete. Remaining validator findings are intentionally left for follow-up.")
    if report_dir:
        print(f"Validator report: {report_dir}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HygieneError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
