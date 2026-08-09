#!/usr/bin/env python3
"""Patch validator v3.2 to optionally publish durable reports into cp-wiki.

Technical run output remains under Application Support. With --publish-report,
the generated Markdown and JSON report pair is additionally copied to:

    <vault>/Generated/Validation/

This preserves the CPKS-DEC-020 / CPKS-SPEC-ART separation between technical
run data and durable human-relevant generated reports.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys

DEFAULT_REPO = Path("/Users/cp/Developer/cpKnowledgeTools")
TARGET_REL = Path("scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py")


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor occurrence, found {count}")
    return text.replace(old, new, 1)


def build_patched_text(text: str) -> str:
    if "--publish-report" in text and "publish_reports_to_vault" in text:
        return text

    if "import shutil\n" not in text:
        text = replace_once(
            text,
            "from pathlib import Path\n",
            "from pathlib import Path\nimport shutil\n",
            "add shutil import",
        )

    helper = '''\ndef publish_reports_to_vault(\n    report_dir: Path,\n    publish_root: Path,\n) -> list[Path]:\n    \"\"\"Copy durable report outputs from the technical run into Generated.\"\"\"\n    report_dir = report_dir.expanduser().resolve()\n    publish_root = publish_root.expanduser().resolve()\n    publish_root.mkdir(parents=True, exist_ok=True)\n\n    suffix = \"-managed-artifact-validation-v3-2\"\n    run_name = report_dir.name\n    if not run_name.endswith(suffix):\n        raise RuntimeError(f\"Unexpected validator report directory name: {run_name}\")\n    timestamp = run_name[:-len(suffix)]\n\n    source_md = report_dir / \"validation-report-v3-2.md\"\n    source_json = report_dir / \"validation-report-v3-2.json\"\n    for source in (source_md, source_json):\n        if not source.is_file():\n            raise RuntimeError(f\"Expected validator report missing: {source}\")\n\n    targets = [\n        publish_root / f\"{timestamp}-managed-artifact-validation-v3-2.md\",\n        publish_root / f\"{timestamp}-managed-artifact-validation-v3-2.json\",\n    ]\n\n    for source, target in zip((source_md, source_json), targets):\n        if target.exists():\n            raise RuntimeError(f\"Published validator report already exists: {target}\")\n        shutil.copy2(source, target)\n\n    return targets\n\n\n'''
    text = replace_once(
        text,
        "\ndef main() -> int:\n",
        helper + "def main() -> int:\n",
        "insert publishing helper",
    )

    report_arg = '    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)\n'
    publish_args = report_arg + '''    parser.add_argument(\n        \"--publish-report\",\n        action=\"store_true\",\n        help=(\n            \"Additionally publish the Markdown/JSON report to \"\n            \"<vault>/Generated/Validation.\"\n        ),\n    )\n    parser.add_argument(\n        \"--publish-report-root\",\n        type=Path,\n        default=None,\n        help=(\n            \"Override the durable report directory. \"\n            \"Default: <vault>/Generated/Validation.\"\n        ),\n    )\n'''
    text = replace_once(text, report_arg, publish_args, "add publishing CLI arguments")

    write_call_end = '''        acknowledgement_stats,\n    )\n\n    severity_counts = Counter(finding.severity for finding in findings)\n'''
    publish_call = '''        acknowledgement_stats,\n    )\n\n    published_reports: list[Path] = []\n    if args.publish_report:\n        publish_root = (\n            args.publish_report_root.expanduser()\n            if args.publish_report_root is not None\n            else vault / \"Generated\" / \"Validation\"\n        )\n        try:\n            published_reports = publish_reports_to_vault(report_dir, publish_root)\n        except Exception as exc:\n            print(f\"ERROR: Could not publish validator report: {exc}\", file=sys.stderr)\n            return 2\n\n    severity_counts = Counter(finding.severity for finding in findings)\n'''
    text = replace_once(text, write_call_end, publish_call, "add publish call")

    report_print = '    print(f"Report directory:                      {report_dir}")\n'
    published_print = report_print + '''    for published_report in published_reports:\n        print(f\"Published report:                      {published_report}\")\n'''
    text = replace_once(text, report_print, published_print, "add published-report output")

    return text


def run_self_test(repo: Path, target: Path) -> None:
    python_exe = repo / ".venv/bin/python"
    if not python_exe.is_file():
        raise PatchError(f"Python environment not found: {python_exe}")
    proc = subprocess.run(
        [str(python_exe), str(target), "--self-test"],
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode != 0:
        raise PatchError("Validator embedded self-test failed after patch:\n" + proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    target = repo / TARGET_REL
    if not target.is_file():
        raise PatchError(f"Validator v3.2 not found: {target}")

    original = target.read_text(encoding="utf-8")
    patched = build_patched_text(original)
    if patched == original:
        print("ALREADY PATCHED: validator v3.2 already contains report publishing.")
        return 0

    compile(patched, str(target), "exec")

    if args.check:
        print("CHECK PASSED.")
        print(f"Target: {target}")
        print("External technical report root remains unchanged.")
        print("New option: --publish-report")
        print("Published target: <vault>/Generated/Validation/")
        return 0

    backup = target.with_suffix(target.suffix + ".pre-publish-generated-validation.bak")
    if backup.exists():
        raise PatchError(f"Backup already exists: {backup}")
    shutil.copy2(target, backup)

    try:
        target.write_text(patched, encoding="utf-8")
        py_compile.compile(str(target), doraise=True)
        run_self_test(repo, target)
    except Exception:
        shutil.copy2(backup, target)
        raise

    print(f"PATCHED: {target}")
    print(f"BACKUP:  {backup}")
    print("Validator syntax check and embedded self-test passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
