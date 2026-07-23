"""Data models for declarative template contexts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SectionSpec:
    heading: str
    level: int
    instruction: str
    example: str
    starter: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DirectorySpec:
    path: Path
    purpose: str
    example: str


@dataclass(frozen=True)
class DocumentSpec:
    path: Path
    purpose: str
    example: str
    frontmatter: dict[str, Any]
    sections: list[SectionSpec]


@dataclass(frozen=True)
class ContextSpec:
    context_id: str
    title: str
    version: str
    description: str
    output_root: Path
    directories: list[DirectorySpec]
    documents: list[DocumentSpec]
