"""Shared technical report and bounded, non-clobbering evidence persistence."""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from cp_knowledge_tools.operations.results import to_primitive


@dataclass
class Report:
    scope: dict[str, Any]
    repository_state: dict[str, Any]
    status: str = "passed"
    status_scope: str = "required_technical_checks"
    review_status: str = "not_evaluated"
    decision: str = "not_evaluated"
    applicable_rules: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    commit_state: str = "not_performed"
    next_action: str = "Review evidence within the resolved authority and scope."
    schema_version: str = "cpks.assurance/1"
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def check(
        self,
        name: str,
        status: str,
        *,
        kind: str = "self_check",
        required: bool = True,
        **data,
    ):
        if status not in {
            "passed",
            "failed",
            "incomplete",
            "not_applicable",
            "review_required",
            "external_evidence",
        }:
            raise ValueError("invalid check status")
        if type(required) is not bool:
            raise ValueError("required must be a boolean")
        if kind not in {
            "self_check",
            "independent_agent_challenge",
            "human_review_required",
            "external_tool_finding",
        }:
            raise ValueError("invalid evidence kind")
        self.checks.append(
            {
                "name": name,
                "status": status,
                "evidence_kind": kind,
                "required": required,
                **data,
            }
        )
        if status in {"review_required", "external_evidence"}:
            self.review_status = "review_required"
        if not required:
            return
        if status == "failed":
            self.status = "failed"
        elif (
            status in {"incomplete", "review_required", "external_evidence"}
            and self.status == "passed"
        ):
            self.status = "incomplete"

    @property
    def exit_code(self) -> int:
        return {"passed": 0, "failed": 1, "incomplete": 2}[self.status]

    def payload(self) -> dict[str, Any]:
        return to_primitive(self)


@contextlib.contextmanager
def _evidence_directory(root: Path) -> Iterator[int]:
    """Open the fixed evidence directory without following directory symlinks."""
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root, directory_flags)
    try:
        for name in ("artifacts", "assurance"):
            with contextlib.suppress(FileExistsError):
                os.mkdir(name, mode=0o700, dir_fd=fd)
            child = os.open(name, directory_flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _write_private(directory_fd: int, name: str, content: bytes) -> None:
    output_fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        with os.fdopen(output_fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.unlink(name, dir_fd=directory_fd)
        raise


def persist(report: Report, root: Path) -> Path:
    """Write a new private report under repo/artifacts/assurance only."""
    with _evidence_directory(root) as fd:
        name = f"{uuid4().hex}.json"
        path = root / "artifacts" / "assurance" / name
        report.evidence_refs.append(str(path))
        try:
            content = json.dumps(report.payload(), ensure_ascii=False, indent=2)
            _write_private(fd, name, (content + "\n").encode("utf-8"))
        except BaseException:
            report.evidence_refs.remove(str(path))
            raise
        return path


def persist_blob(root: Path, content: bytes) -> Path:
    """Retain a bounded, already sanitized SBOM in the fixed evidence directory.

    This is not a general file writer: the directory and filename suffix are
    fixed, existing files are never replaced, and the new file is private.
    Validation and sanitization remain the scanner adapter's responsibility.
    """
    if not isinstance(content, bytes) or len(content) > 10_000_000:
        raise ValueError("SBOM evidence must be bounded bytes")
    with _evidence_directory(root) as fd:
        name = f"{uuid4().hex}.sbom.json"
        _write_private(fd, name, content)
        return root / "artifacts" / "assurance" / name
