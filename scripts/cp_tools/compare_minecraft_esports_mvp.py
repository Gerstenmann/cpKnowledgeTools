#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = (
    REPO_ROOT
    / "artifacts/tests/source_to_knowledge/minecraft_esports/evaluations"
)


def load(label: str) -> dict:
    path = EVAL_DIR / f"{label}.json"
    if not path.is_file():
        raise SystemExit(f"Missing evaluation: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    before = load("before")
    after = load("after")
    comparison = {
        "scenario_ref": before["scenario_ref"],
        "scenario_version": before["scenario_version"],
        "before": {
            "head": before["repository"]["head"],
            "test_passed": before["test"]["passed"],
            "exit_code": before["test"]["exit_code"],
        },
        "after": {
            "head": after["repository"]["head"],
            "test_passed": after["test"]["passed"],
            "exit_code": after["test"]["exit_code"],
        },
        "transition": (
            "RED_TO_GREEN"
            if not before["test"]["passed"] and after["test"]["passed"]
            else "NO_RED_TO_GREEN_TRANSITION"
        ),
        "fixtures_unchanged": [
            {
                "path": b["path"],
                "before_sha256": b["sha256"],
                "after_sha256": a["sha256"],
                "unchanged": b["sha256"] == a["sha256"],
            }
            for b, a in zip(before["fixtures"], after["fixtures"], strict=True)
        ],
    }
    out_path = EVAL_DIR / "comparison.json"
    out_path.write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Transition: {comparison['transition']}")
    print(f"Before: {'PASS' if comparison['before']['test_passed'] else 'FAIL'}")
    print(f"After:  {'PASS' if comparison['after']['test_passed'] else 'FAIL'}")
    print("Fixtures unchanged:")
    for item in comparison["fixtures_unchanged"]:
        print(f"  {'yes' if item['unchanged'] else 'NO'}  {item['path']}")
    print(f"Wrote comparison: {out_path}")
    return 0 if comparison["transition"] == "RED_TO_GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
