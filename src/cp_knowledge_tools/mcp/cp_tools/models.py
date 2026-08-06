"""Data models for the read-only cpKnowledgeTools MCP server."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepositoryFile:
    """Metadata for one file inside the repository."""

    relative_path: str
    name: str
    suffix: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class RepositoryDocument:
    """One UTF-8 text file or selected line range."""

    relative_path: str
    name: str
    suffix: str
    size_bytes: int
    total_lines: int
    start_line: int
    end_line: int
    content: str


@dataclass(frozen=True, slots=True)
class RepositoryTreeNode:
    """One file or directory in a repository tree."""

    name: str
    relative_path: str
    kind: str
    size_bytes: int | None
    children: tuple[RepositoryTreeNode, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryTree:
    """A bounded directory tree result."""

    root: RepositoryTreeNode
    entry_count: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class SearchMatch:
    """One matching line from a repository text search."""

    relative_path: str
    line_number: int
    line: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GitStatusEntry:
    """One changed path reported by Git."""

    path: str
    index_status: str
    worktree_status: str
    original_path: str | None = None


@dataclass(frozen=True, slots=True)
class GitStatus:
    """Structured Git working-tree status."""

    branch: str | None
    head: str
    clean: bool
    entries: tuple[GitStatusEntry, ...]
    omitted_entries: int


@dataclass(frozen=True, slots=True)
class GitDiff:
    """A bounded read-only Git diff."""

    staged: bool
    relative_path: str | None
    character_count: int
    truncated: bool
    content: str


@dataclass(frozen=True, slots=True)
class GitCommit:
    """Metadata for one Git commit."""

    commit: str
    short_commit: str
    author_name: str
    author_date: str
    subject: str
