from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from cp_knowledge_tools.operations.contracts import (
    IncidentRecord,
    ResultDisposition,
    TechnicalRunEvidence,
)
from cp_knowledge_tools.operations.evidence import TechnicalRunEvidenceWriter
from cp_knowledge_tools.operations.incidents import ExecFailureIncidentWriter
from cp_knowledge_tools.operations.results import to_primitive


@dataclass(frozen=True)
class _DatedContract:
    created: dt.date
    observed_at: dt.datetime


def test_to_primitive_serializes_date_and_aware_datetime() -> None:
    observed_at = dt.datetime(
        2026,
        8,
        28,
        17,
        16,
        tzinfo=dt.timezone(dt.timedelta(hours=2)),
    )

    assert to_primitive(dt.date(2026, 8, 28)) == "2026-08-28"
    assert to_primitive(observed_at) == "2026-08-28T17:16:00+02:00"


def test_to_primitive_serializes_nested_and_dataclass_dates_to_json() -> None:
    observed_at = dt.datetime(
        2026,
        8,
        28,
        17,
        16,
        tzinfo=dt.timezone(dt.timedelta(hours=2)),
    )
    value = {
        "tuple_dates": (dt.date(2026, 8, 26),),
        "set_dates": {dt.date(2026, 8, 25)},
        "postconditions": [
            {
                "code": "completion_preserve",
                "actual": {
                    "created": dt.date(2026, 8, 28),
                    "contract": _DatedContract(
                        created=dt.date(2026, 8, 27),
                        observed_at=observed_at,
                    ),
                },
            }
        ]
    }

    primitive = to_primitive(value)
    rendered = json.dumps(primitive)
    loaded = json.loads(rendered)

    assert loaded["tuple_dates"] == ["2026-08-26"]
    assert loaded["set_dates"] == ["2026-08-25"]
    actual = loaded["postconditions"][0]["actual"]
    assert actual["created"] == "2026-08-28"
    assert actual["contract"] == {
        "created": "2026-08-27",
        "observed_at": "2026-08-28T17:16:00+02:00",
    }


def test_technical_run_evidence_writer_serializes_yaml_style_dates(
    tmp_path: Path,
) -> None:
    evidence = TechnicalRunEvidence.create(
        started_at="2026-08-28T17:16:00+02:00",
        completed_at="2026-08-28T17:16:01+02:00",
        run_id="run-dated-postcondition",
        correlation_id="corr-dated-postcondition",
        operation_name="artifact.transition",
        operation_version="0.1",
        scope={"transition_profile": "work_package.complete"},
        authority_context={"authority_ref": "CPKT-WP-003@0.1"},
        versions={"contract": "0.1"},
        inputs={"target": "CPKT-WP-003"},
        fingerprints={"active": "abc"},
        plan_ref="plan-dated-postcondition",
        preview_ref=None,
        actual_mutations=("completed-work-package.md",),
        validation_results=(),
        postconditions=(
            {
                "code": "completion_preserve",
                "passed": True,
                "actual": {"created": dt.date(2026, 8, 28)},
            },
        ),
        outputs={"status": "completed"},
        disposition=ResultDisposition.SUCCEEDED,
        compensation_status="none",
        recovery_status="none",
    )

    path = TechnicalRunEvidenceWriter(tmp_path).write(evidence)
    rendered = path.read_text(encoding="utf-8")
    loaded = json.loads(rendered)

    assert path.name == "technical-run-evidence.json"
    assert loaded["postconditions"][0]["actual"]["created"] == "2026-08-28"
    assert loaded["event_timestamps"] == {
        "started_at": "2026-08-28T17:16:00+02:00",
        "completed_at": "2026-08-28T17:16:01+02:00",
    }
    assert "datetime.date" not in rendered
    assert "datetime.datetime" not in rendered


def test_technical_run_evidence_roundtrip_uses_aware_timestamps(
    tmp_path: Path,
) -> None:
    evidence = TechnicalRunEvidence.create(
        started_at="2026-08-28T10:00:00+00:00",
        completed_at="2026-08-28T10:00:01+00:00",
        run_id="run-1",
        correlation_id="corr-1",
        operation_name="artifact.activate",
        operation_version="0.1",
        scope={"document_type": "specification"},
        authority_context={"authority_ref": "CPKT-WP-002@0.1"},
        versions={"contract": "0.1"},
        inputs={"target": "CPKS-SPEC-ART"},
        fingerprints={"active": "abc"},
        plan_ref="plan-1",
        preview_ref="preview-1",
        actual_mutations=("one.md",),
        validation_results=(),
        postconditions=(),
        outputs={"status": "active"},
        disposition=ResultDisposition.SUCCEEDED,
        compensation_status="none",
        recovery_status="none",
    )
    path = TechnicalRunEvidenceWriter(tmp_path).write(evidence)
    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert loaded["event_timestamps"]["started_at"].endswith("+00:00")
    assert loaded["event_timestamps"]["completed_at"].endswith("+00:00")
    assert (
        loaded["event_timestamps"]["completed_at"]
        > loaded["event_timestamps"]["started_at"]
    )


def test_incident_writer_sanitizes_secrets(tmp_path: Path) -> None:
    writer = ExecFailureIncidentWriter(tmp_path)
    record = IncidentRecord.create(
        capture_mode="at_failure",
        failure_phase="apply",
        mutation_state="partial",
        details={
            "token": "super-secret",
            "terminal_output": "Authorization: Bearer abc123 password=hunter2",
        },
    )

    path = writer.capture(record)
    assert path is not None
    rendered = path.read_text(encoding="utf-8")
    assert "super-secret" not in rendered
    assert "abc123" not in rendered
    assert "hunter2" not in rendered
    assert "[REDACTED]" in rendered


def test_incident_capture_is_non_blocking(tmp_path: Path) -> None:
    writer = ExecFailureIncidentWriter(tmp_path / "not-a-directory")
    (tmp_path / "not-a-directory").write_text("occupied", encoding="utf-8")
    record = IncidentRecord.create(
        capture_mode="retrospective",
        failure_phase="runtime",
        mutation_state="none",
        details={"message": "original failure"},
    )

    assert writer.capture(record) is None
