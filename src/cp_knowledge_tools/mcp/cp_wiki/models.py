"""Data models used by the read-only cp-wiki MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """Parsed Markdown document."""

    relative_path: str
    frontmatter: dict[str, Any]
    body: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class TextSearchMatch:
    """One text-search result inside a Markdown file."""

    relative_path: str
    line_number: int
    line: str
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FrontmatterSearchMatch:
    """One frontmatter-search result."""

    relative_path: str
    field: str
    value: Any


@dataclass(frozen=True, slots=True)
class WikilinkResolution:
    """Result of resolving one Obsidian wikilink."""

    target: str
    resolved_paths: list[str]
    ambiguous: bool
