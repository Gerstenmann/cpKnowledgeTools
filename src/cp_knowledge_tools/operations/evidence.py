"""Persistence for technical run evidence."""

from __future__ import annotations

import json
from pathlib import Path

from cp_knowledge_tools.validation.temporal import (
    TechnicalTimestampSchema,
    validate_technical_timestamps,
)

from .contracts import TechnicalRunEvidence
from .results import to_primitive

RUN_TIMESTAMP_SCHEMA = TechnicalTimestampSchema(
    required_fields=("started_at", "completed_at"),
    ordered_pairs=(("started_at", "completed_at"),),
)


class TechnicalRunEvidenceWriter:
    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root.resolve()

    def write(self, evidence: TechnicalRunEvidence) -> Path:
        findings = validate_technical_timestamps(
            evidence.event_timestamps,
            RUN_TIMESTAMP_SCHEMA,
        )
        if findings:
            codes = ", ".join(finding.code for finding in findings)
            raise ValueError(f"invalid technical run timestamps: {codes}")
        target = self.run_root / evidence.run_id / "technical-run-evidence.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                to_primitive(evidence), ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        return target
