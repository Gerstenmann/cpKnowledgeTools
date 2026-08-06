"""Safe, read-only access to the local cp-wiki vault."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .errors import (
    UnsupportedFileTypeError,
    VaultFileNotFoundError,
    VaultPathError,
)
from .markdown import parse_markdown
from .models import MarkdownDocument

SUPPORTED_MARKDOWN_SUFFIXES = {".md", ".markdown"}


@dataclass(frozen=True, slots=True)
class VaultFile:
    """Metadata for a file inside the vault."""

    relative_path: str
    name: str
    suffix: str
    size_bytes: int


class Vault:
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

    """Read-only filesystem boundary around an Obsidian vault."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

        if not self._root.exists() or not self._root.is_dir():
            raise VaultPathError(f"Invalid vault root: {self._root}")

    @property
    def root(self) -> Path:
        """Return the resolved vault root."""

        return self._root

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

    def iter_markdown_files(self) -> Iterator[Path]:
        """Yield Markdown files contained inside the vault."""

        for path in self._root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in SUPPORTED_MARKDOWN_SUFFIXES:
                continue

            resolved = path.resolve()

            try:
                resolved.relative_to(self._root)
            except ValueError:
                continue

            yield resolved

    def list_markdown_files(self) -> list[VaultFile]:
        """Return sorted metadata for all Markdown files in the vault."""

        files = [
            VaultFile(
                relative_path=path.relative_to(self._root).as_posix(),
                name=path.name,
                suffix=path.suffix.lower(),
                size_bytes=path.stat().st_size,
            )
            for path in self.iter_markdown_files()
        ]

        return sorted(files, key=lambda item: item.relative_path.casefold())

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
