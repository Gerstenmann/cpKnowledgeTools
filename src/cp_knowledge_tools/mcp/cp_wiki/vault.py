"""Safe, read-only access to the local cp-wiki vault."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import (
    InvalidJsonError,
    UnsupportedFileTypeError,
    VaultFileNotFoundError,
    VaultFileTooLargeError,
    VaultPathError,
)
from .markdown import parse_markdown
from .models import MarkdownDocument

SUPPORTED_MARKDOWN_SUFFIXES = {".md", ".markdown"}
SUPPORTED_JSON_SUFFIXES = {".json"}


@dataclass(frozen=True, slots=True)
class VaultFile:
    """Metadata for a file inside the vault."""

    relative_path: str
    name: str
    suffix: str
    size_bytes: int


class Vault:
    """Read-only filesystem boundary around an Obsidian vault."""

    def __init__(self, root: Path, max_json_bytes: int = 1_000_000) -> None:
        self._root = root.resolve()
        self._max_json_bytes = max_json_bytes

        if not self._root.exists() or not self._root.is_dir():
            raise VaultPathError(f"Invalid vault root: {self._root}")

    @property
    def root(self) -> Path:
        """Return the resolved vault root."""

        return self._root

    @property
    def max_json_bytes(self) -> int:
        """Return the maximum readable JSON file size."""

        return self._max_json_bytes

    def read_document(
        self,
        relative_path: str | Path,
    ) -> MarkdownDocument:
        """Read and parse one Markdown document."""

        normalized_path = Path(relative_path).as_posix()
        content = self.read_markdown(relative_path)

        return parse_markdown(
            relative_path=normalized_path,
            content=content,
        )

    def resolve_path(self, relative_path: str | Path) -> Path:
        """
        Resolve a vault-relative path safely.

        Absolute paths, parent traversal and symlink escapes are rejected.
        """

        requested = Path(relative_path)

        if requested.is_absolute():
            raise VaultPathError(
                "Absolute paths are not permitted; use a vault-relative path."
            )

        resolved = (self._root / requested).resolve()

        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise VaultPathError(
                f"Path escapes the configured vault: {relative_path}"
            ) from exc

        return resolved

    def _iter_files_with_suffixes(self, suffixes: set[str]) -> Iterator[Path]:
        """Yield safe files whose suffix is in the supplied set."""

        for path in self._root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in suffixes:
                continue

            resolved = path.resolve()

            try:
                resolved.relative_to(self._root)
            except ValueError:
                continue

            yield resolved

    def iter_markdown_files(self) -> Iterator[Path]:
        """Yield Markdown files contained inside the vault."""

        yield from self._iter_files_with_suffixes(SUPPORTED_MARKDOWN_SUFFIXES)

    def iter_json_files(self) -> Iterator[Path]:
        """Yield JSON files contained inside the vault."""

        yield from self._iter_files_with_suffixes(SUPPORTED_JSON_SUFFIXES)

    def _list_files_with_suffixes(self, suffixes: set[str]) -> list[VaultFile]:
        """Return sorted metadata for files with one of the supplied suffixes."""

        files = [
            VaultFile(
                relative_path=path.relative_to(self._root).as_posix(),
                name=path.name,
                suffix=path.suffix.lower(),
                size_bytes=path.stat().st_size,
            )
            for path in self._iter_files_with_suffixes(suffixes)
        ]

        return sorted(files, key=lambda item: item.relative_path.casefold())

    def list_markdown_files(self) -> list[VaultFile]:
        """Return sorted metadata for all Markdown files in the vault."""

        return self._list_files_with_suffixes(SUPPORTED_MARKDOWN_SUFFIXES)

    def list_json_files(self) -> list[VaultFile]:
        """Return sorted metadata for all JSON files in the vault."""

        return self._list_files_with_suffixes(SUPPORTED_JSON_SUFFIXES)

    def read_markdown(self, relative_path: str | Path) -> str:
        """Read one Markdown file as UTF-8 text."""

        path = self.resolve_path(relative_path)

        if not path.exists() or not path.is_file():
            raise VaultFileNotFoundError(f"Vault file does not exist: {relative_path}")

        if path.suffix.lower() not in SUPPORTED_MARKDOWN_SUFFIXES:
            raise UnsupportedFileTypeError(
                f"Only Markdown files may be read: {relative_path}"
            )

        return path.read_text(encoding="utf-8")

    def read_json(self, relative_path: str | Path) -> Any:
        """Read and parse one JSON file as structured data."""

        path = self.resolve_path(relative_path)

        if not path.exists() or not path.is_file():
            raise VaultFileNotFoundError(f"Vault file does not exist: {relative_path}")

        if path.suffix.lower() not in SUPPORTED_JSON_SUFFIXES:
            raise UnsupportedFileTypeError(
                f"Only JSON files may be read: {relative_path}"
            )

        size_bytes = path.stat().st_size

        if size_bytes > self._max_json_bytes:
            raise VaultFileTooLargeError(
                f"JSON file exceeds the maximum readable size of "
                f"{self._max_json_bytes} bytes: {relative_path}"
            )

        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidJsonError(
                f"JSON file is not valid UTF-8 text: {relative_path}"
            ) from exc

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidJsonError(
                f"Invalid JSON in {relative_path}: "
                f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
