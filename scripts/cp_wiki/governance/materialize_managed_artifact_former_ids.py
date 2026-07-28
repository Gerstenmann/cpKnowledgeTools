#!/usr/bin/env python3
"""
Materialize the owner-approved former_ids mappings on current artifact heads.

Canonical repository location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/governance/
  materialize_managed_artifact_former_ids.py

Default: dry run. Use --apply to write changes.
No version activation, Git commit or push is performed.
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

VAULT = Path("/Users/cp/Documents/cp-wiki")
TOOLS = Path("/Users/cp/Developer/cpKnowledgeTools")
CANONICAL_SCRIPT = (
    TOOLS / "scripts/cp_wiki/governance/materialize_managed_artifact_former_ids.py"
)
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/"
    "cpKnowledgeTools/Runs/cp-wiki/governance"
)
TODAY = "2026-07-26"

TARGETS = [
    {
        "path": Path(
            "Systems/cpKnowledgeSystem/Governance/Policies/"
            "CPKS-POL-GOV-AUTH Governance Artifact Authoring Policy.md"
        ),
        "id_field": "policy_id",
        "current_id": "CPKS-POL-GOV-AUTH",
        "former_id": "CPKS-POL-GOVERNANCE-AUTHORING",
    },
    {
        "path": Path(
            "Systems/cpKnowledgeSystem/Governance/"
            "CPKS-FWK-AIW AI Working Governance Framework.md"
        ),
        "id_field": "framework_id",
        "current_id": "CPKS-FWK-AIW",
        "former_id": "CPKS-FWK-AI-WORKING",
    },
    {
        "path": Path(
            "Systems/cpKnowledgeSystem/Governance/System Control/"
            "CPKS-BL cpKnowledgeSystem Authoritative Baseline.md"
        ),
        "id_field": "baseline_id",
        "current_id": "CPKS-BL",
        "former_id": "CPKS-BASELINE",
    },
    {
        "path": Path(
            "Development/cp-wiki Vault/Specifications/Architecture Specification/"
            "CPW-SPEC-VLT@1.2 Obsidian cp-wiki Vault Specification.md"
        ),
        "id_field": "specification_id",
        "current_id": "CPW-SPEC-VLT",
        "former_id": "CPWIKI-VAULT-SPEC",
    },
    {
        "path": Path(
            "Development/cpKnowledgeSystem/Specifications/"
            "CPKS-SPEC-PROC@0.3 Process Description Specification.md"
        ),
        "id_field": "specification_id",
        "current_id": "CPKS-SPEC-PROC",
        "former_id": "CPKS-SPEC-PROCESS-DESCRIPTION",
    },
]


class MigrationError(RuntimeError):
    pass


def assert_location() -> None:
    actual = Path(__file__).resolve()
    expected = CANONICAL_SCRIPT.resolve()
    if actual != expected:
        raise MigrationError(
            "Script is not in its canonical repository location.\n"
            f"Expected: {expected}\nActual:   {actual}"
        )


def split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise MigrationError("Missing YAML frontmatter.")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[: index + 1], lines[index + 1 :]
    raise MigrationError("Unclosed YAML frontmatter.")


def migrate(text: str, *, id_field: str, current_id: str, former_id: str) -> str:
    fm, body = split_frontmatter(text)
    id_line = f"{id_field}: {current_id}"
    indexes = [index for index, line in enumerate(fm) if line.strip() == id_line]
    if len(indexes) != 1:
        raise MigrationError(
            f"Expected exactly one {id_line!r}, found {len(indexes)}."
        )

    raw = "".join(fm)
    former_match = re.search(
        r"(?ms)^former_ids:\s*\n((?:\s+-\s+.*\n?)*)",
        raw,
    )
    if former_match:
        values = [
            match.group(1).strip().strip("\"'")
            for match in re.finditer(r"(?m)^\s+-\s+(.+?)\s*$", former_match.group(1))
        ]
        if former_id not in values:
            raise MigrationError(
                f"former_ids exists but does not contain {former_id}: {values}"
            )
    else:
        insert_at = indexes[0] + 1
        fm[insert_at:insert_at] = [
            "former_ids:\n",
            f"  - {former_id}\n",
        ]

    revised_indexes = [
        index for index, line in enumerate(fm) if line.startswith("revised:")
    ]
    if len(revised_indexes) != 1:
        raise MigrationError(
            f"Expected exactly one revised field, found {len(revised_indexes)}."
        )
    fm[revised_indexes[0]] = f"revised: {TODAY}\n"
    return "".join(fm + body)


def atomic_write(path: Path, content: str) -> None:
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".former-ids.tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, path.stat().st_mode & 0o777)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    assert_location()

    changes: list[dict[str, object]] = []
    prepared: list[tuple[Path, str, str]] = []
    diffs: list[str] = []

    for target in TARGETS:
        relative = target["path"]
        assert isinstance(relative, Path)
        path = VAULT / relative
        if not path.is_file():
            raise MigrationError(
                f"Required current artifact is missing: {relative}. "
                "Place CPKS-SPEC-PROC@0.3 before this migration."
            )
        before = path.read_text(encoding="utf-8")
        after = migrate(
            before,
            id_field=str(target["id_field"]),
            current_id=str(target["current_id"]),
            former_id=str(target["former_id"]),
        )
        prepared.append((path, before, after))
        changes.append(
            {
                "path": relative.as_posix(),
                "current_id": target["current_id"],
                "former_id": target["former_id"],
                "changed": before != after,
                "before_sha256": sha256(before),
                "after_sha256": sha256(after),
            }
        )
        if before != after:
            diffs.extend(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=f"a/{relative.as_posix()}",
                    tofile=f"b/{relative.as_posix()}",
                )
            )

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    mode = "apply" if args.apply else "dry-run"
    run_dir = RUN_ROOT / f"{timestamp}-materialize-former-ids-{mode}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "planned-changes.diff").write_text("".join(diffs), encoding="utf-8")
    (run_dir / "migration-report.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "mapping_authority": "Owner approval 2026-07-26",
                "changes": changes,
                "activation_performed": False,
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
        print(f"Run report: {run_dir}")
        return 0

    recovery_root = run_dir / "recovery"
    written: list[tuple[Path, str]] = []
    try:
        for path, before, after in prepared:
            relative = path.relative_to(VAULT)
            recovery = recovery_root / relative
            recovery.parent.mkdir(parents=True, exist_ok=True)
            recovery.write_text(before, encoding="utf-8")
            if before != after:
                atomic_write(path, after)
                written.append((path, before))
    except Exception:
        for path, before in reversed(written):
            atomic_write(path, before)
        raise

    for path, _, after in prepared:
        if path.read_text(encoding="utf-8") != after:
            raise MigrationError(f"Post-validation failed: {path}")

    print("Approved former_ids mappings materialized and validated.")
    print(f"Run report: {run_dir}")
    print("No activation, Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
