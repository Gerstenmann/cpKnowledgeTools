#!/usr/bin/env python3
"""Capture a before/after evaluation for the Minecraft Esports MVP test.

This is a repository work script. It does not mutate production code or Golden
Truth. It runs the stable pytest acceptance test and stores run evidence under
git-ignored artifacts/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label",
        choices=("before", "after"),
        required=True,
        help="Evaluation label; use before now and after after MVP implementation.",
    )
    parser.add_argument(
        "--result-path",
        default=None,
        help="Optional black-box result.json path produced by the MVP runner.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    scenario_path = (
        repo_root
        / "tests/golden/source_to_knowledge/minecraft_esports/expected/scenario.v1.json"
    )
    test_path = (
        repo_root
        / "tests/e2e/source_to_knowledge/test_minecraft_esports_source_to_knowledge.py"
    )

    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))

    git_rev = run(["git", "rev-parse", "HEAD"], repo_root)
    git_status = run(["git", "status", "--short"], repo_root)

    fixture_state = []
    for fixture in scenario["fixture_bindings"]:
        path = repo_root / fixture["path"]
        fixture_state.append(
            {
                "path": fixture["path"],
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else None,
                "sha256": sha256(path) if path.is_file() else None,
                "expected_sha256": fixture["sha256"],
                "hash_matches": (
                    sha256(path) == fixture["sha256"] if path.is_file() else False
                ),
            }
        )

    env = os.environ.copy()
    if args.result_path:
        env["CPKT_MVP_RESULT_PATH"] = str(Path(args.result_path).resolve())

    pytest_run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_path)],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    report = {
        "evaluation_type": "source_to_knowledge_before_after",
        "label": args.label,
        "scenario_ref": scenario["scenario_ref"],
        "scenario_version": scenario["scenario_version"],
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "repository": {
            "root": str(repo_root),
            "head": git_rev.stdout.strip() if git_rev.returncode == 0 else None,
            "working_tree_clean": git_status.stdout.strip() == "",
            "git_status_short": git_status.stdout.splitlines(),
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
        },
        "fixtures": fixture_state,
        "test": {
            "path": str(test_path.relative_to(repo_root)),
            "exit_code": pytest_run.returncode,
            "passed": pytest_run.returncode == 0,
            "stdout": pytest_run.stdout,
            "stderr": pytest_run.stderr,
        },
        "black_box_result_path": env.get(
            "CPKT_MVP_RESULT_PATH",
            scenario["test_harness_contract"]["result_default_path"],
        ),
    }

    out_dir = (
        repo_root
        / "artifacts/tests/source_to_knowledge/minecraft_esports/evaluations"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.label}.json"
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote evaluation: {out_path}")
    print()
    print(pytest_run.stdout, end="")
    if pytest_run.stderr:
        print(pytest_run.stderr, file=sys.stderr, end="")
    print()
    print(
        f"{args.label.upper()} RESULT: "
        f"{'GREEN/PASS' if pytest_run.returncode == 0 else 'RED/FAIL'}"
    )
    return pytest_run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
