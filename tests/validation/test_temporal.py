from __future__ import annotations

import datetime as dt
import runpy
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from cp_knowledge_tools.validation.temporal import (
    EXEC_FAILURE_INCIDENT_TIMESTAMP_SCHEMA,
    TechnicalTimestampSchema,
    lifecycle_temporal_precedes,
    parse_lifecycle_temporal,
    parse_technical_timestamp,
    validate_technical_timestamps,
)

_VALIDATOR = runpy.run_path(
    str(
        Path(__file__).parents[2]
        / "scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py"
    )
)


def _validate_managed_temporals(frontmatter: dict) -> list:
    document_type = _VALIDATOR["Document"]
    document = document_type(
        path=Path("fixture.md"),
        relative_path="fixture.md",
        scan_zone="active_governance",
        text="",
        raw_frontmatter=yaml.safe_dump(frontmatter),
        body="",
        frontmatter=frontmatter,
        has_frontmatter=True,
        parse_error=None,
    )
    findings = []
    _VALIDATOR["validate_date_fields"](document, findings, required=True)
    return findings


@pytest.mark.parametrize(
    "yaml_value",
    [
        "2026-08-21",
        '"2026-08-21"',
        "2026-08-21T09:01:08+02:00",
        '"2026-08-21T09:01:08+02:00"',
        "2026-08-21T07:01:08Z",
    ],
)
def test_lifecycle_temporal_accepts_yaml_native_and_string_values(
    yaml_value: str,
) -> None:
    value = yaml.safe_load(f"value: {yaml_value}\n")["value"]

    assert parse_lifecycle_temporal(value) is not None


@pytest.mark.parametrize(
    "value",
    [
        "yesterday",
        "21.08.2026",
        "2026-99-42",
        "2026-08-21T09:01:08",
    ],
)
def test_lifecycle_temporal_rejects_invalid_values(value: str) -> None:
    assert parse_lifecycle_temporal(value) is None


def test_lifecycle_order_handles_mixed_precision_and_timestamp_offsets() -> None:
    created_date = parse_lifecycle_temporal("2026-08-20")
    revised_timestamp = parse_lifecycle_temporal("2026-08-21T08:30:00+02:00")
    created_timestamp = parse_lifecycle_temporal("2026-08-21T10:00:00+02:00")
    revised_date = parse_lifecycle_temporal("2026-08-20")
    same_instant_utc = parse_lifecycle_temporal("2026-08-21T08:00:00Z")

    assert created_date is not None
    assert revised_timestamp is not None
    assert created_timestamp is not None
    assert revised_date is not None
    assert same_instant_utc is not None
    assert lifecycle_temporal_precedes(created_date, revised_timestamp)
    assert lifecycle_temporal_precedes(revised_date, created_timestamp)
    assert not lifecycle_temporal_precedes(same_instant_utc, created_timestamp)


def test_managed_validator_accepts_aware_approval_and_effective_timestamps() -> None:
    frontmatter = yaml.safe_load(
        """
created: 2026-08-20
revised: 2026-08-21T08:30:00+02:00
approved_at: 2026-08-21T09:01:08+02:00
effective_from: 2026-08-21T07:01:08Z
"""
    )

    findings = _validate_managed_temporals(frontmatter)

    assert not findings
    assert not any(finding.code == "invalid_date" for finding in findings)


def test_managed_validator_reports_invalid_lifecycle_temporal_value() -> None:
    findings = _validate_managed_temporals(
        {
            "created": "2026-08-20",
            "revised": "2026-08-21",
            "approved_at": "yesterday",
        }
    )

    assert [finding.code for finding in findings] == [
        "invalid_lifecycle_temporal_value"
    ]


def test_managed_validator_checks_mixed_precision_lifecycle_order() -> None:
    findings = _validate_managed_temporals(
        {
            "created": "2026-08-21T10:00:00+02:00",
            "revised": "2026-08-20",
        }
    )

    assert [finding.code for finding in findings] == ["revised_before_created"]


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-21T09:01:08+02:00",
        "2026-08-21T07:01:08Z",
        "2026-08-21T09:01:08.123456+02:00",
        dt.datetime(2026, 8, 21, 7, 1, 8, tzinfo=dt.UTC),
    ],
)
def test_technical_timestamp_requires_complete_aware_timestamp(value: object) -> None:
    assert parse_technical_timestamp(value) is not None


def test_technical_schema_is_explicit_optional_and_chronological() -> None:
    schema = TechnicalTimestampSchema(
        required_fields=("started_at", "completed_at"),
        optional_fields=("validated_at",),
        ordered_pairs=(("started_at", "completed_at"),),
    )

    assert not validate_technical_timestamps(
        {
            "started_at": "2026-08-21T09:00:00+02:00",
            "completed_at": "2026-08-21T07:04:00Z",
        },
        schema,
    )

    findings = validate_technical_timestamps(
        {
            "started_at": "2026-08-21T09:04:00+02:00",
            "completed_at": "2026-08-21T09:00:00+02:00",
        },
        schema,
    )
    assert [finding.code for finding in findings] == [
        "technical_timestamp_order_invalid"
    ]


@pytest.mark.parametrize(
    ("record", "code"),
    [
        ({}, "missing_required_technical_timestamp"),
        ({"captured_at": ""}, "missing_required_technical_timestamp"),
        ({"captured_at": "2026-08-21"}, "invalid_technical_timestamp"),
        (
            {"captured_at": "2026-08-21T09:01:08"},
            "technical_timestamp_timezone_missing",
        ),
        ({"captured_at": "yesterday"}, "invalid_technical_timestamp"),
    ],
)
def test_incident_schema_validates_only_existing_record(
    record: dict,
    code: str,
) -> None:
    findings = validate_technical_timestamps(
        record,
        EXEC_FAILURE_INCIDENT_TIMESTAMP_SCHEMA,
    )

    assert [finding.code for finding in findings] == [code]


def test_missing_optional_incident_record_is_non_blocking() -> None:
    assert not validate_technical_timestamps(
        None,
        EXEC_FAILURE_INCIDENT_TIMESTAMP_SCHEMA,
    )


def test_unrelated_field_name_does_not_create_timestamp_requirement() -> None:
    schema = TechnicalTimestampSchema(required_fields=("captured_at",))

    findings = validate_technical_timestamps(
        {
            "captured_at": "2026-08-21T07:01:08Z",
            "activated_at": "not-a-timestamp",
        },
        schema,
    )

    assert not findings


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-21T09:00:00+02:60",
        "2026-08-21T09:00:00-00:99",
        "2026-08-21T09:00:00+24:00",
        "2026-02-29T09:00:00Z",
        "2026-08-21T24:01:00Z",
    ],
)
def test_invalid_calendar_time_or_offset_is_not_normalized(value: str) -> None:
    # ART §9.8 and OPS §6.7.11 require semantic validity, not just parseability.
    assert parse_lifecycle_temporal(value) is None
    assert parse_technical_timestamp(value) is None
    findings = validate_technical_timestamps(
        {"captured_at": value}, EXEC_FAILURE_INCIDENT_TIMESTAMP_SCHEMA
    )
    assert [(item.severity, item.code, item.actual) for item in findings] == [
        ("error", "invalid_technical_timestamp", value)
    ]


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-21T09:00:00+02:60",
        "2026-08-21T09:00:00-00:99",
        "2026-08-21T09:00:00+24:00",
        "2026-02-29",
        "2026-08-21T25:00:00Z",
    ],
)
def test_yaml_invalid_temporal_reaches_structured_diagnosis(value: str) -> None:
    frontmatter = _VALIDATOR["parse_yaml_frontmatter"](
        f"created: 2026-08-20\nrevised: {value}\n"
    )

    findings = _validate_managed_temporals(frontmatter)

    assert [(item.severity, item.code, item.field) for item in findings] == [
        ("error", "invalid_lifecycle_temporal_value", "revised")
    ]
    assert frontmatter["revised"] == value


@pytest.mark.parametrize("reverse", [False, True])
def test_native_dst_fold_is_ordered_by_instant(reverse: bool) -> None:
    # OPS §6.7.4 explicitly requires chronology across summer/winter time.
    zone = ZoneInfo("Europe/Berlin")
    earlier = dt.datetime(2026, 10, 25, 2, 50, tzinfo=zone, fold=0)
    later = dt.datetime(2026, 10, 25, 2, 10, tzinfo=zone, fold=1)
    if reverse:
        earlier, later = later, earlier
    created = parse_lifecycle_temporal(earlier)
    revised = parse_lifecycle_temporal(later)
    assert created is not None and revised is not None

    assert lifecycle_temporal_precedes(revised, created) is reverse
    schema = TechnicalTimestampSchema(
        required_fields=("started_at", "completed_at"),
        ordered_pairs=(("started_at", "completed_at"),),
    )
    record = {"started_at": earlier, "completed_at": later}
    before = record.copy()
    findings = validate_technical_timestamps(record, schema)
    assert [item.code for item in findings] == (
        ["technical_timestamp_order_invalid"] if reverse else []
    )
    assert record == before
    assert record["started_at"] is earlier
    assert record["completed_at"] is later


def test_mixed_precision_same_day_does_not_invent_midnight() -> None:
    assert not _validate_managed_temporals(
        {"created": "2026-08-21T23:59:59-04:00", "revised": "2026-08-21"}
    )


@pytest.mark.parametrize("value", [None, "", "2026-08-21"])
def test_present_invalid_optional_event_is_error_without_input_mutation(
    value: object,
) -> None:
    record = {"validated_at": value}
    schema = TechnicalTimestampSchema(optional_fields=("validated_at",))
    findings = validate_technical_timestamps(record, schema)

    assert [(item.severity, item.code) for item in findings] == [
        ("error", "invalid_technical_timestamp")
    ]
    assert record == {"validated_at": value}
    assert not validate_technical_timestamps({}, schema)


@pytest.mark.parametrize("record", [{}, {"created": "", "revised": None}])
def test_required_lifecycle_dates_remain_required(record: dict) -> None:
    findings = _validate_managed_temporals(record)
    assert [(item.severity, item.code, item.field) for item in findings] == [
        ("error", "missing_required_field", "created"),
        ("error", "missing_required_field", "revised"),
    ]


@pytest.mark.parametrize(
    ("created", "revised"),
    [
        ("0001-01-01T00:00:00+02:00", "0001-01-01T00:01:00+02:00"),
        ("9999-12-31T23:58:00-02:00", "9999-12-31T23:59:00-02:00"),
    ],
)
def test_valid_boundary_year_instants_do_not_overflow(
    created: str,
    revised: str,
) -> None:
    assert not _validate_managed_temporals({"created": created, "revised": revised})
    findings = _validate_managed_temporals({"created": revised, "revised": created})
    assert [item.code for item in findings] == ["revised_before_created"]


def test_managed_yaml_loader_preserves_valid_native_types_and_safe_loader() -> None:
    constructor = yaml.SafeLoader.yaml_constructors["tag:yaml.org,2002:timestamp"]
    frontmatter = _VALIDATOR["parse_yaml_frontmatter"](
        "created: 2026-08-20\nrevised: 2026-08-21T09:01:08+02:00\n"
    )

    assert frontmatter["created"] == dt.date(2026, 8, 20)
    assert isinstance(frontmatter["revised"], dt.datetime)
    assert frontmatter["revised"].isoformat() == "2026-08-21T09:01:08+02:00"
    assert not _validate_managed_temporals(frontmatter)
    assert (
        yaml.SafeLoader.yaml_constructors["tag:yaml.org,2002:timestamp"] is constructor
    )
