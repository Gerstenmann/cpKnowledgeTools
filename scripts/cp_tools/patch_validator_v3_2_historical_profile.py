#!/usr/bin/env python3
"""
Patch Managed Artifact Validator v3.2 to apply the restricted historical /
closed-development profile required by CPKS-SPEC-ART@0.3.

The patch does NOT weaken current/current-development validation.

Changes:
- canonical_path is mandatory only in full current profiles; for historical
  files it is validated if present, but absence is not a blocking error;
- stable IDs longer than 32 characters remain blocking for current profiles,
  but are reported as legacy_artifact_id info in historical/closed profiles;
- current filename normalization rules are enforced only in full current
  profiles; historical legacy filenames are not retroactively rejected;
- adds a regression fixture for a closed-development legacy specification
  with a long ID, no canonical_path and a legacy filename.

The patch modifies only the validator source, never the cp-wiki Vault.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import subprocess
import sys
import tempfile

DEFAULT_REPO = Path("/Users/cp/Developer/cpKnowledgeTools")
RELATIVE_TARGET = Path("scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py")


class PatchError(RuntimeError):
    pass


def replace_exact(source: str, old: str, new: str, label: str, expected_count: int = 1) -> str:
    count = source.count(old)
    if count != expected_count:
        raise PatchError(
            f"{label}: expected {expected_count} occurrence(s), found {count}. "
            "Refusing to patch an unexpected validator state."
        )
    return source.replace(old, new)


def patch_source(source: str) -> str:
    source = replace_exact(
        source,
        '    required = [\n'
        '        "document_type",\n'
        '        doc.id_field,\n'
        '        "title",\n'
        '        "version",\n'
        '        "status",\n'
        '        "canonical_path",\n'
        '    ]\n'
        '    if full:\n'
        '        required.extend(["owner", "created", "revised"])\n',
        '    required = [\n'
        '        "document_type",\n'
        '        doc.id_field,\n'
        '        "title",\n'
        '        "version",\n'
        '        "status",\n'
        '    ]\n'
        '    if full:\n'
        '        required.extend(["owner", "created", "revised", "canonical_path"])\n',
        "historical required-field treatment",
    )

    source = replace_exact(
        source,
        '    if artifact_id and len(artifact_id) > 32:\n'
        '        add(\n'
        '            findings,\n'
        '            doc,\n'
        '            "error",\n'
        '            "artifact_id_too_long",\n'
        '            "Stable artifact ID exceeds 32 characters.",\n'
        '            field=doc.id_field,\n'
        '            actual=len(artifact_id),\n'
        '            expected="<= 32",\n'
        '        )\n',
        '    if artifact_id and len(artifact_id) > 32:\n'
        '        add(\n'
        '            findings,\n'
        '            doc,\n'
        '            "error" if full else "info",\n'
        '            "artifact_id_too_long" if full else "legacy_artifact_id",\n'
        '            "Stable artifact ID exceeds 32 characters."\n'
        '            if full\n'
        '            else "Historical stable artifact ID exceeds the current recommended length and is preserved as legacy identity.",\n'
        '            field=doc.id_field,\n'
        '            actual=len(artifact_id),\n'
        '            expected="<= 32" if full else "preserve unless a controlled migration is authorized",\n'
        '        )\n',
        "legacy long-ID treatment",
    )

    source = replace_exact(
        source,
        '    validate_canonical_path_and_filename(doc, findings, check_filename=True)\n',
        '    validate_canonical_path_and_filename(doc, findings, check_filename=full)\n',
        "historical filename treatment",
    )

    anchor = '        # 3. Current Development managed artifact.\n'
    fixture_text = (
        '        # 2b. Closed-development legacy artifact: long stable ID,\\n'
        '        # no canonical_path and legacy filename are preserved under the\\n'
        '        # restricted historical profile and must not be blocking errors.\\n'
        '        legacy_managed_path = Path(\\n'
        '            "Development/cpKnowledgeTools/Archive/Specifications/"\\n'
        '            "Legacy Platform Specification.md"\\n'
        '        )\\n'
        '        write_fixture(\\n'
        '            vault / legacy_managed_path,\\n'
        '            "---\\\\n"\\n'
        '            "document_type: specification\\\\n"\\n'
        '            "specification_id: TEST-DEVELOPMENT-PLATFORM-ARCHITECTURE\\\\n"\\n'
        '            "title: Legacy Platform Specification\\\\n"\\n'
        '            "version: \\\\\\"1.0\\\\\\"\\\\n"\\n'
        '            "status: superseded\\\\n"\\n'
        '            "owner: Owner\\\\n"\\n'
        '            "created: 2026-07-16\\\\n"\\n'
        '            "revised: 2026-07-16\\\\n"\\n'
        '            "---\\\\n"\\n'
        '            "# Legacy fixture\\\\n",\\n'
        '        )\\n\\n'
    ).encode("utf-8").decode("unicode_escape")
    source = replace_exact(
        source,
        anchor,
        fixture_text + anchor,
        "historical regression fixture insertion",
    )

    anchor2 = '        if acknowledgement_stats.acknowledged_documents != 1:\n'
    assertion_text = (
        '        legacy_blockers = [\\n'
        '            finding\\n'
        '            for finding in findings\\n'
        '            if finding.path == legacy_managed_path.as_posix()\\n'
        '            and finding.severity == "error"\\n'
        '        ]\\n'
        '        if legacy_blockers:\\n'
        '            raise SelfTestFailure(\\n'
        '                "Historical-profile regression produced blocking errors: "\\n'
        '                + ", ".join(item.code for item in legacy_blockers)\\n'
        '            )\\n'
        '        if not any(\\n'
        '            finding.path == legacy_managed_path.as_posix()\\n'
        '            and finding.code == "legacy_artifact_id"\\n'
        '            and finding.severity == "info"\\n'
        '            for finding in findings\\n'
        '        ):\\n'
        '            raise SelfTestFailure(\\n'
        '                "Historical long stable ID did not produce legacy_artifact_id info."\\n'
        '            )\\n\\n'
    ).encode("utf-8").decode("unicode_escape")
    source = replace_exact(
        source,
        anchor2,
        assertion_text + anchor2,
        "historical regression assertions",
    )

    return source


def run_self_test(python_exe: Path, candidate: Path) -> None:
    proc = subprocess.run(
        [str(python_exe), str(candidate), "--self-test"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(proc.stdout, end="")
    if proc.returncode != 0:
        raise PatchError(f"v3.2 self-test failed with exit code {proc.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Build, parse and self-test without replacing the installed validator.",
    )
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    target = repo / RELATIVE_TARGET
    python_exe = repo / ".venv/bin/python"

    if not target.is_file():
        raise PatchError(f"Validator v3.2 not found: {target}")
    if not python_exe.is_file():
        raise PatchError(f"Repository Python not found: {python_exe}")

    original = target.read_text(encoding="utf-8")
    patched = patch_source(original)
    ast.parse(patched, filename=str(target))

    with tempfile.TemporaryDirectory(prefix="cpwiki-validator-v3-2-history-") as td:
        candidate = Path(td) / target.name
        candidate.write_text(patched, encoding="utf-8")
        run_self_test(python_exe, candidate)

        if args.check:
            print("CHECK PASSED: historical-profile patch built, parsed and self-tested.")
            return 0

        target.write_text(patched, encoding="utf-8")

    ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    print(f"PATCHED: {target}")
    print("Next step: rerun v3.2 against the canonical cp-wiki Vault with --strict-exit.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
