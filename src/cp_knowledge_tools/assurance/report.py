"""Shared technical report and bounded, non-clobbering evidence persistence."""

from __future__ import annotations

import contextlib
import json
import os
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

    def check(self, name: str, status: str, *, kind: str = "self_check", **data):
        if status not in {"passed", "failed", "incomplete", "not_applicable"}:
            raise ValueError("invalid check status")
        if kind not in {
            "self_check",
            "independent_agent_challenge",
            "human_review_required",
            "external_tool_finding",
        }:
            raise ValueError("invalid evidence kind")
        self.checks.append(
            {"name": name, "status": status, "evidence_kind": kind, **data}
        )
        if status == "failed":
            self.status = "failed"
        elif status == "incomplete" and self.status == "passed":
            self.status = "incomplete"

    @property
    def exit_code(self) -> int:
        return {"passed": 0, "failed": 1, "incomplete": 2}[self.status]

    def payload(self) -> dict[str, Any]:
        return to_primitive(self)


def persist(report: Report, root: Path) -> Path:
    """Write only to a new private file in repo/artifacts/assurance.

    Descriptor-relative traversal rejects symlinks; callers cannot redirect
    reports into source, the Vault, or a pre-existing evidence file.
    """
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root, directory_flags)
    try:
        for name in ("artifacts", "assurance"):
            with contextlib.suppress(FileExistsError):
                os.mkdir(name, mode=0o700, dir_fd=fd)
            child = os.open(name, directory_flags, dir_fd=fd)
            os.close(fd)
            fd = child
        name = f"{uuid4().hex}.json"
        path = root / "artifacts" / "assurance" / name
        report.evidence_refs.append(str(path))
        output_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(output_fd, "w", encoding="utf-8") as stream:
            json.dump(report.payload(), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return path
    finally:
        os.close(fd)
