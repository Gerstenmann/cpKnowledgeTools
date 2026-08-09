#!/usr/bin/env python3
"""
Patch cp-wiki Managed Artifact Validator v3.2 to compare filesystem paths
and filenames Unicode-normalized (NFC).

Why:
macOS commonly exposes filenames in decomposed Unicode (NFD), while the
canonical cp-wiki metadata and ART title-normalization rules use NFC.
Logical equality must therefore be checked after Unicode normalization.

This patch:
- normalizes canonical_path vs actual relative path comparisons;
- normalizes expected vs actual filename comparisons;
- normalizes canonical_path keys for duplicate-path detection;
- adds an embedded self-test fixture for NFC metadata vs NFD filesystem path;
- runs the validator self-test before replacing the installed file.

It does not modify the cp-wiki Vault.
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
        'if canonical_path and canonical_path != doc.relative_path:',
        'if canonical_path and unicodedata.normalize("NFC", canonical_path) != unicodedata.normalize("NFC", doc.relative_path):',
        "canonical_path Unicode comparison",
        expected_count=2,
    )

    source = replace_exact(
        source,
        'if expected and expected != actual:',
        'if expected and unicodedata.normalize("NFC", expected) != unicodedata.normalize("NFC", actual):',
        "filename Unicode comparison",
    )

    source = replace_exact(
        source,
        """        canonical_path = scalar_text(doc.frontmatter.get("canonical_path"))
        if canonical_path:
            by_canonical_path[canonical_path].append(doc)
""",
        """        canonical_path = scalar_text(doc.frontmatter.get("canonical_path"))
        if canonical_path:
            by_canonical_path[unicodedata.normalize("NFC", canonical_path)].append(doc)
""",
        "canonical_path duplicate-key normalization",
    )

    anchor = """        # 2. Historical managed artifact with an old alias reference.
"""
    insert = r"""        # 1b. macOS-style NFD filesystem name must compare equal to
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

"""
    source = replace_exact(
        source,
        anchor,
        insert + anchor,
        "Unicode self-test insertion",
    )

    anchor2 = """        if acknowledgement_stats.acknowledged_documents != 1:
"""
    insert2 = r"""        unicode_regressions = [
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

"""
    source = replace_exact(
        source,
        anchor2,
        insert2 + anchor2,
        "Unicode regression assertion",
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
        help="Build, parse and self-test the patched validator without replacing the installed file.",
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

    with tempfile.TemporaryDirectory(prefix="cpwiki-validator-v3-2-unicode-") as td:
        candidate = Path(td) / target.name
        candidate.write_text(patched, encoding="utf-8")
        run_self_test(python_exe, candidate)

        if args.check:
            print("CHECK PASSED: Unicode NFC/NFD patch built, parsed and self-tested.")
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
