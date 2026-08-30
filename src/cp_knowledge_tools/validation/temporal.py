"""Semantic validation for lifecycle values and technical event timestamps."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_AWARE_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:[.,][0-9]+)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$"
)
_NAIVE_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.,][0-9]+)?$"
)


@dataclass(frozen=True)
class LifecycleTemporalValue:
    """A valid lifecycle date or timezone-aware timestamp."""

    calendar_date: dt.date
    instant: dt.datetime | None

    @property
    def precision(self) -> Literal["date", "timestamp"]:
        return "timestamp" if self.instant is not None else "date"


@dataclass(frozen=True)
class TechnicalTimestampFinding:
    """One schema-driven technical event-time conformance error."""

    severity: Literal["error"]
    code: str
    message: str
    field: str
    actual: Any = None
    expected: Any = None


@dataclass(frozen=True)
class TechnicalTimestampSchema:
    """Explicit timestamp obligations for one technical evidence class."""

    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    ordered_pairs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        fields = self.required_fields + self.optional_fields
        if len(fields) != len(set(fields)):
            raise ValueError("technical timestamp schema fields must be unique")
        known = set(fields)
        for earlier, later in self.ordered_pairs:
            if earlier not in known or later not in known:
                raise ValueError(
                    "technical timestamp ordering must reference declared fields"
                )


EXEC_FAILURE_INCIDENT_TIMESTAMP_SCHEMA = TechnicalTimestampSchema(
    required_fields=("captured_at",),
)


def _has_timezone(value: dt.datetime) -> bool:
    if value.tzinfo is None:
        return False
    try:
        return value.utcoffset() is not None
    except (OverflowError, ValueError):
        return False


def _parse_timestamp_string(value: str) -> dt.datetime | None:
    if not _AWARE_TIMESTAMP_RE.fullmatch(value):
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if _has_timezone(parsed) else None


def parse_lifecycle_temporal(value: Any) -> LifecycleTemporalValue | None:
    """Parse an ART lifecycle date or timezone-aware ISO-8601 timestamp."""

    if isinstance(value, dt.datetime):
        if not _has_timezone(value):
            return None
        return LifecycleTemporalValue(value.date(), value)
    if isinstance(value, dt.date):
        return LifecycleTemporalValue(value, None)
    if not isinstance(value, str):
        return None
    if _DATE_RE.fullmatch(value):
        try:
            return LifecycleTemporalValue(dt.date.fromisoformat(value), None)
        except ValueError:
            return None
    parsed = _parse_timestamp_string(value)
    if parsed is None:
        return None
    return LifecycleTemporalValue(parsed.date(), parsed)


def lifecycle_temporal_precedes(
    left: LifecycleTemporalValue,
    right: LifecycleTemporalValue,
) -> bool:
    """Return whether ``left`` is unambiguously earlier than ``right``.

    Two timestamps are compared as instants, including their UTC offsets. If
    either value has date-only precision, their lifecycle calendar dates are
    compared so an unknown time within the same date does not create a false
    ordering error.
    """

    if left.instant is not None and right.instant is not None:
        return _instant_key(left.instant) < _instant_key(right.instant)
    return left.calendar_date < right.calendar_date


def _instant_key(value: dt.datetime) -> dt.timedelta:
    """Compare actual instants even for a shared DST zone and different folds.

    Timedelta arithmetic also handles valid local dates whose UTC conversion
    would fall outside datetime's representable year range.
    """

    offset = value.utcoffset()
    assert offset is not None
    return (value.replace(tzinfo=None) - dt.datetime.min) - offset


def parse_technical_timestamp(value: Any) -> dt.datetime | None:
    """Parse a complete technical event timestamp with explicit timezone."""

    if isinstance(value, dt.datetime):
        return value if _has_timezone(value) else None
    if not isinstance(value, str):
        return None
    return _parse_timestamp_string(value)


def _technical_timestamp_error(value: Any) -> str:
    if isinstance(value, dt.datetime):
        if not _has_timezone(value):
            return "technical_timestamp_timezone_missing"
        return "invalid_technical_timestamp"
    if isinstance(value, str) and _NAIVE_TIMESTAMP_RE.fullmatch(value):
        try:
            dt.datetime.fromisoformat(value)
        except ValueError:
            return "invalid_technical_timestamp"
        return "technical_timestamp_timezone_missing"
    return "invalid_technical_timestamp"


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def validate_technical_timestamps(
    record: Mapping[str, Any] | None,
    schema: TechnicalTimestampSchema,
) -> tuple[TechnicalTimestampFinding, ...]:
    """Validate only the timestamp duties declared by ``schema``.

    ``None`` means that no optional technical evidence record was materialized
    and therefore produces no finding. Field names, paths, and unrelated
    record content never create additional timestamp requirements.
    """

    if record is None:
        return ()

    findings: list[TechnicalTimestampFinding] = []
    parsed: dict[str, dt.datetime] = {}
    required = set(schema.required_fields)

    for field in schema.required_fields + schema.optional_fields:
        if field not in record:
            if field in required:
                findings.append(
                    TechnicalTimestampFinding(
                        severity="error",
                        code="missing_required_technical_timestamp",
                        message="Required technical event timestamp is missing.",
                        field=field,
                        expected="timezone-aware ISO-8601 timestamp",
                    )
                )
            continue

        value = record[field]
        if _is_empty(value) and field in required:
            findings.append(
                TechnicalTimestampFinding(
                    severity="error",
                    code="missing_required_technical_timestamp",
                    message="Required technical event timestamp is empty.",
                    field=field,
                    actual=value,
                    expected="timezone-aware ISO-8601 timestamp",
                )
            )
            continue

        timestamp = parse_technical_timestamp(value)
        if timestamp is None:
            code = _technical_timestamp_error(value)
            findings.append(
                TechnicalTimestampFinding(
                    severity="error",
                    code=code,
                    message=(
                        "Technical event timestamp requires an explicit timezone."
                        if code == "technical_timestamp_timezone_missing"
                        else "Technical event timestamp is syntactically or "
                        "semantically invalid."
                    ),
                    field=field,
                    actual=value,
                    expected="timezone-aware ISO-8601 timestamp",
                )
            )
            continue
        parsed[field] = timestamp

    for earlier, later in schema.ordered_pairs:
        if earlier not in parsed or later not in parsed:
            continue
        if _instant_key(parsed[later]) < _instant_key(parsed[earlier]):
            findings.append(
                TechnicalTimestampFinding(
                    severity="error",
                    code="technical_timestamp_order_invalid",
                    message="Technical event timestamp order violates its schema.",
                    field=later,
                    actual=record[later],
                    expected=f">= {record[earlier]}",
                )
            )

    return tuple(findings)
