#!/usr/bin/env python3
"""Build read-only Derived Governance State and optional impact triage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cp_knowledge_tools.derived import (
    assess_baseline_impact,
    assess_impact,
    build_governance_state,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--changed-artifact")
    parser.add_argument("--derived-only", action="store_true")
    parser.add_argument("--baseline-topic", action="append", default=[])
    args = parser.parse_args()

    state = build_governance_state(args.vault)
    payload = state.as_dict()
    if args.changed_artifact:
        payload["impact"] = {
            key: value.value
            for key, value in sorted(
                assess_impact(
                    state,
                    args.changed_artifact,
                    material_change=not args.derived_only,
                ).items()
            )
        }
    if args.baseline_topic:
        payload["baseline_impact"] = assess_baseline_impact(
            set(args.baseline_topic)
        ).value

    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
