"""Data structures used by the taxonomy validator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One validation error with source location."""

    code: str
    message: str
    path: Path
    line: int
    block: str | None = None

    def render(self) -> str:
        block_text = f" [{self.block}]" if self.block else ""
        return (
            f"{self.path}:{self.line}"
            f"{block_text} {self.code}: {self.message}"
        )


@dataclass(slots=True)
class MachineBlock:
    """One parsed DSM machine block."""

    name: str
    start_line: int
    end_line: int
    raw_content: str
    data: Any = None
    key_lines: dict[str, list[int]] = field(default_factory=dict)

    def line_for_key(self, key: str, occurrence: int = 0) -> int:
        lines = self.key_lines.get(key, [])

        if occurrence < len(lines):
            return lines[occurrence]

        return self.start_line


@dataclass(slots=True)
class ParsedDocument:
    """Parsed DSM document and all detected issues."""

    path: Path
    blocks: dict[str, list[MachineBlock]] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def first_block(self, name: str) -> MachineBlock | None:
        blocks = self.blocks.get(name, [])
        return blocks[0] if blocks else None