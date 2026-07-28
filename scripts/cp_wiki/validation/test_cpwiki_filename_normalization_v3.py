#!/usr/bin/env python3
"""
macOS/Git integration test for validator-v3 filename normalization.

Canonical repository location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/validation/
  test_cpwiki_filename_normalization_v3.py

The script creates an isolated fixture Vault and Git repository under:
  /Users/cp/Library/Application Support/
  cpKnowledgeTools/Runs/cp-wiki/validation/

It does not modify cp-wiki. Obsidian link resolution requires one small manual
check because the Obsidian application/API is not invoked by this CLI test.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import unicodedata

TOOLS = Path("/Users/cp/Developer/cpKnowledgeTools")
SCRIPT_ROOT = TOOLS / "scripts/cp_wiki/validation"
CANONICAL_SCRIPT = SCRIPT_ROOT / "test_cpwiki_filename_normalization_v3.py"
VALIDATOR_PATH = SCRIPT_ROOT / "validate_cpwiki_managed_artifacts_draft_v3.py"
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/"
    "cpKnowledgeTools/Runs/cp-wiki/validation"
)


class IntegrationFailure(RuntimeError):
    pass


def assert_canonical_location() -> None:
    actual = Path(__file__).resolve()
    expected = CANONICAL_SCRIPT.resolve()
    if actual != expected:
        raise IntegrationFailure(
            "Script is not in its canonical repository location.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )


def load_validator_module():
    if not VALIDATOR_PATH.is_file():
        raise IntegrationFailure(f"Validator v3 not found: {VALIDATOR_PATH}")
    spec = importlib.util.spec_from_file_location("cpwiki_validator_v3", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise IntegrationFailure("Could not load validator v3 module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise IntegrationFailure(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-non-macos",
        action="store_true",
        help="Run for development diagnostics outside macOS.",
    )
    args = parser.parse_args()

    assert_canonical_location()
    system = platform.system()
    if system != "Darwin" and not args.allow_non_macos:
        raise IntegrationFailure(
            f"This integration test must run on macOS; current platform is {system}."
        )

    validator = load_validator_module()
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    run_dir = RUN_ROOT / f"{timestamp}-filename-normalization-v3"
    fixture = run_dir / "fixture-vault"
    fixture.mkdir(parents=True, exist_ok=False)

    titles = [
        "Änderung und Überprüfung",
        "Straße und Größenprüfung",
        "A – B",
        "A: B",
        "A/B",
        "Mehrfache   Leerzeichen",
        "Café",
        "Cafe\u0301",
        "Titel mit Schluss...",
    ]

    normalized: dict[str, str] = {}
    for title in titles:
        value = validator.normalize_title_for_filename(title)
        normalized[title] = value
        if unicodedata.normalize("NFC", value) != value:
            raise IntegrationFailure(f"Normalization result is not NFC: {value!r}")
        if any(character in value for character in '<>:"/\\|?*'):
            raise IntegrationFailure(f"Forbidden filename character remains: {value!r}")

    # Both Unicode spellings must collapse to one normalized filename.
    if normalized["Café"] != normalized["Cafe\u0301"]:
        raise IntegrationFailure("Composed and decomposed Café did not normalize equally.")

    created_names: list[str] = []
    seen_names: set[str] = set()
    for index, title in enumerate(titles, start=1):
        filename = f"TEST-{index:02d} {normalized[title]}.md"
        if filename in seen_names:
            continue
        seen_names.add(filename)
        created_names.append(filename)
        (fixture / filename).write_text(
            f"# {title}\n\nNormalized filename: `{filename}`\n",
            encoding="utf-8",
        )

    actual_directory_names = sorted(path.name for path in fixture.glob("*.md"))
    normalized_directory_names = sorted(
        unicodedata.normalize("NFC", name) for name in actual_directory_names
    )
    if normalized_directory_names != sorted(created_names):
        raise IntegrationFailure(
            "Filesystem round-trip changed normalized filenames unexpectedly."
        )

    index_lines = ["# Obsidian filename integration check", ""]
    for filename in created_names:
        index_lines.append(f"- [[{Path(filename).stem}]]")
    index_lines.extend(
        [
            "",
            "## Manual check",
            "",
            "Open this fixture directory as a temporary Obsidian Vault.",
            "Every wikilink above must open exactly one note without creating a new file.",
        ]
    )
    (fixture / "Obsidian Link Test.md").write_text(
        "\n".join(index_lines) + "\n",
        encoding="utf-8",
    )

    git_available = shutil.which("git") is not None
    git_report: dict[str, object] = {"available": git_available}
    if git_available:
        run(["git", "init", "-q"], fixture)
        run(["git", "config", "user.name", "cpKnowledgeTools Test"], fixture)
        run(["git", "config", "user.email", "test@localhost"], fixture)
        run(["git", "add", "."], fixture)
        run(["git", "commit", "-q", "-m", "Initial filename fixture"], fixture)

        case_source = fixture / "Case Rename Test.md"
        case_source.write_text("# Case rename\n", encoding="utf-8")
        run(["git", "add", case_source.name], fixture)
        run(["git", "commit", "-q", "-m", "Add case rename fixture"], fixture)
        run(["git", "mv", case_source.name, "case-rename-intermediate.md"], fixture)
        run(["git", "mv", "case-rename-intermediate.md", "case rename test.md"], fixture)
        status = run(["git", "status", "--short"], fixture).stdout.strip()
        if not status:
            raise IntegrationFailure("Git did not detect the controlled case-only rename.")
        git_report.update(
            {
                "case_only_rename_detected": True,
                "status": status.splitlines(),
            }
        )

    report = {
        "generated_at": dt.datetime.now().astimezone().isoformat(),
        "platform": system,
        "fixture_vault": str(fixture),
        "validator": str(VALIDATOR_PATH),
        "normalization_results": normalized,
        "created_files": created_names,
        "filesystem_roundtrip": "passed",
        "unicode_equivalence": "passed",
        "forbidden_character_replacement": "passed",
        "git": git_report,
        "obsidian": {
            "status": "manual_check_required",
            "entry_note": str(fixture / "Obsidian Link Test.md"),
            "criterion": "Every wikilink opens exactly one existing note.",
        },
    }
    (run_dir / "filename-normalization-report-v3.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "filename-normalization-report-v3.md").write_text(
        "\n".join(
            [
                "# Filename Normalization Integration Report v3",
                "",
                f"- Platform: `{system}`",
                f"- Fixture Vault: `{fixture}`",
                "- Validator normalization unit: **passed**",
                "- Filesystem round-trip: **passed**",
                "- Unicode NFC equivalence: **passed**",
                "- Forbidden-character replacement: **passed**",
                f"- Git available: **{git_available}**",
                "- Obsidian link resolution: **manual check required**",
                "",
                "Open `Obsidian Link Test.md` in the fixture Vault. Each link must open an existing note without creating a duplicate.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print("Filename normalization integration test completed.")
    print(f"Platform: {system}")
    print(f"Fixture Vault: {fixture}")
    print(f"Report directory: {run_dir}")
    print("Filesystem and Git checks passed.")
    print("Obsidian link resolution remains a short manual check.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IntegrationFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
