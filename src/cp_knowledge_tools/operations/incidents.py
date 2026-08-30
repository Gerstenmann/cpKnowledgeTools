"""Best-effort, sanitized exec-failure incident capture."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cp_knowledge_tools.validation.temporal import (
    EXEC_FAILURE_INCIDENT_TIMESTAMP_SCHEMA,
    validate_technical_timestamps,
)

from .contracts import (
    IncidentRecord,
    OperationRequest,
    OperationResult,
    ResultDisposition,
)
from .results import to_primitive

_SECRET_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|authorization|credential)",
    re.IGNORECASE,
)
_SECRET_TEXT = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/]+=*"),
    re.compile(r"(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*)[^\s,;]+"),
)


def sanitize(value: Any, *, key: str | None = None) -> Any:
    if key and _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): sanitize(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        rendered = value
        for pattern in _SECRET_TEXT:
            rendered = pattern.sub(r"\1[REDACTED]", rendered)
        return rendered
    return value


class ExecFailureIncidentWriter:
    """A failure in this writer is deliberately returned as ``None``."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.incident_root = (
            self.repo_root / "artifacts" / "exec-failures" / "incidents"
        )

    def capture(self, record: IncidentRecord) -> Path | None:
        try:
            findings = validate_technical_timestamps(
                {"captured_at": record.captured_at},
                EXEC_FAILURE_INCIDENT_TIMESTAMP_SCHEMA,
            )
            if findings:
                return None
            self.incident_root.mkdir(parents=True, exist_ok=True)
            target = self.incident_root / f"{record.incident_id}.json"
            target.write_text(
                json.dumps(
                    sanitize(to_primitive(record)),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return target
        except OSError, TypeError, ValueError:
            return None


def capture_operation(request: OperationRequest, **kwargs: Any) -> OperationResult:
    parameters = {**request.parameters, **kwargs}
    record = IncidentRecord.create(
        capture_mode=str(parameters.get("capture_mode", "at_failure")),
        failure_phase=str(parameters.get("failure_phase", "unknown")),
        mutation_state=str(parameters.get("mutation_state", "unknown")),
        details=dict(parameters.get("details", {})),
        relations=dict(parameters.get("relations", {})) or None,
    )
    run_id = f"incident-{record.incident_id}"
    if request.requested_mode != "apply":
        return OperationResult(
            operation_name=request.operation_name,
            operation_version=request.operation_version,
            disposition=ResultDisposition.SUCCEEDED,
            run_id=run_id,
            correlation_id=request.correlation_id,
            message="incident capture preview",
            outputs={"record": sanitize(to_primitive(record)), "written": False},
        )
    repo_root = Path(parameters["repo_root"])
    path = ExecFailureIncidentWriter(repo_root).capture(record)
    return OperationResult(
        operation_name=request.operation_name,
        operation_version=request.operation_version,
        disposition=ResultDisposition.SUCCEEDED,
        run_id=run_id,
        correlation_id=request.correlation_id,
        message="incident capture completed best effort",
        outputs={
            "incident_path": str(path) if path else None,
            "written": path is not None,
        },
        actual_mutations=(str(path),) if path else (),
    )
