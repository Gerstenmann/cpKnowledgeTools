"""Safe, read-only access to the local cpKnowledgeTools repository."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from .errors import (
    RepositoryAccessDeniedError,
    RepositoryFileNotFoundError,
    RepositoryFileTooLargeError,
    RepositoryPathError,
    UnsupportedFileTypeError,
)
from .models import (
    RepositoryDocument,
    RepositoryFile,
    RepositoryTree,
    RepositoryTreeNode,
)

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".idea",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "venv",
    }
)

DENIED_EXACT_FILE_NAMES = frozenset(
    {
        ".env",
        ".netrc",
        "credentials.json",
        "id_dsa",
        "id_ed25519",
        "id_ecdsa",
        "id_rsa",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
    }
)

ALLOWED_ENV_TEMPLATE_NAMES = frozenset(
    {
        ".env.example",
        ".env.sample",
        ".env.template",
    }
)

DENIED_FILE_SUFFIXES = frozenset(
    {
        ".der",
        ".jks",
        ".key",
        ".keystore",
        ".p12",
        ".pem",
        ".pfx",
    }
)


def is_denied_file_name(file_name: str) -> bool:
    """Return whether a file name is intentionally blocked."""

    normalized = file_name.casefold()

    if normalized in ALLOWED_ENV_TEMPLATE_NAMES:
        return False

    if normalized in DENIED_EXACT_FILE_NAMES:
        return True

    if normalized.startswith(".env."):
        return True

    return Path(normalized).suffix in DENIED_FILE_SUFFIXES


def is_visible_relative_path(
    relative_path: str | Path,
    *,
    path_is_directory: bool = False,
) -> bool:
    """Return whether a relative repository path may be exposed."""

    path = Path(relative_path)

    if path.is_absolute() or ".." in path.parts:
        return False

    directory_parts = path.parts if path_is_directory else path.parts[:-1]

    if any(part.casefold() in EXCLUDED_DIRECTORY_NAMES for part in directory_parts):
        return False

    if not path_is_directory and is_denied_file_name(path.name):
        return False

    return True


class Repository:
    """Read-only filesystem boundary around a source-code repository."""

    def __init__(self, root: Path, max_file_bytes: int) -> None:
        self._root = root.resolve()
        self._max_file_bytes = max_file_bytes

        if not self._root.exists() or not self._root.is_dir():
            raise RepositoryPathError(f"Invalid repository root: {self._root}")

    @property
    def root(self) -> Path:
        """Return the resolved repository root."""

        return self._root

    @property
    def max_file_bytes(self) -> int:
        """Return the maximum readable file size."""

        return self._max_file_bytes

    def resolve_path(self, relative_path: str | Path) -> Path:
        """Resolve and validate a repository-relative path."""

        requested = Path(relative_path)

        if requested.is_absolute():
            raise RepositoryPathError(
                "Absolute paths are not permitted; use a repository-relative path."
            )

        if ".." in requested.parts:
            raise RepositoryPathError("Parent-directory references are not permitted.")

        current = self._root

        for part in requested.parts:
            if part in {"", "."}:
                continue

            current = current / part

            if current.is_symlink():
                raise RepositoryAccessDeniedError(
                    f"Symbolic links may not be accessed: {relative_path}"
                )

        unresolved = self._root / requested
        resolved = unresolved.resolve()

        try:
            relative = resolved.relative_to(self._root)
        except ValueError as exc:
            raise RepositoryPathError(
                f"Path escapes the configured repository: {relative_path}"
            ) from exc

        path_is_directory = resolved.exists() and resolved.is_dir()

        if not is_visible_relative_path(
            relative,
            path_is_directory=path_is_directory,
        ):
            raise RepositoryAccessDeniedError(
                f"Access to this repository path is denied: {relative_path}"
            )

        return resolved

    def iter_files(self) -> Iterator[Path]:
        """Yield safe regular files contained inside the repository."""

        for current_root, directory_names, file_names in os.walk(
            self._root,
            topdown=True,
            followlinks=False,
        ):
            current_path = Path(current_root)

            directory_names[:] = sorted(
                (
                    name
                    for name in directory_names
                    if name.casefold() not in EXCLUDED_DIRECTORY_NAMES
                    and not (current_path / name).is_symlink()
                ),
                key=str.casefold,
            )

            for file_name in sorted(file_names, key=str.casefold):
                if is_denied_file_name(file_name):
                    continue

                candidate = current_path / file_name

                if candidate.is_symlink() or not candidate.is_file():
                    continue

                resolved = candidate.resolve()

                try:
                    relative = resolved.relative_to(self._root)
                except ValueError:
                    continue

                if not is_visible_relative_path(relative):
                    continue

                yield resolved

    def list_files(self) -> list[RepositoryFile]:
        """Return sorted metadata for safe repository files."""

        files = [
            RepositoryFile(
                relative_path=path.relative_to(self._root).as_posix(),
                name=path.name,
                suffix=path.suffix.casefold(),
                size_bytes=path.stat().st_size,
            )
            for path in self.iter_files()
        ]

        return sorted(
            files,
            key=lambda item: item.relative_path.casefold(),
        )

    def find_files(
        self,
        query: str,
        *,
        path_prefix: str = "",
        suffix: str = "",
        case_sensitive: bool = False,
        limit: int = 100,
    ) -> list[RepositoryFile]:
        """Find files by file name or repository-relative path."""

        if not query:
            raise ValueError("query must not be empty.")

        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000.")

        prefix = path_prefix.strip().replace("\\", "/")

        if prefix:
            prefix_path = Path(prefix)

            if prefix_path.is_absolute() or ".." in prefix_path.parts:
                raise RepositoryPathError("path_prefix must be repository-relative.")

        normalized_suffix = suffix.strip().casefold()

        if normalized_suffix and not normalized_suffix.startswith("."):
            normalized_suffix = "." + normalized_suffix

        normalized_prefix = prefix.casefold()
        normalized_query = query if case_sensitive else query.casefold()

        results: list[RepositoryFile] = []

        for file_info in self.list_files():
            candidate_path = (
                file_info.relative_path
                if case_sensitive
                else file_info.relative_path.casefold()
            )
            candidate_name = (
                file_info.name if case_sensitive else file_info.name.casefold()
            )

            if normalized_prefix and not file_info.relative_path.casefold().startswith(
                normalized_prefix
            ):
                continue

            if normalized_suffix and file_info.suffix != normalized_suffix:
                continue

            if (
                normalized_query not in candidate_path
                and normalized_query not in candidate_name
            ):
                continue

            results.append(file_info)

            if len(results) >= limit:
                break

        return results

    def read_text_file(
        self,
        relative_path: str | Path,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> RepositoryDocument:
        """Read one safe UTF-8 file or a selected line range."""

        if start_line is not None and start_line < 1:
            raise ValueError("start_line must be at least 1.")

        if end_line is not None and end_line < 1:
            raise ValueError("end_line must be at least 1.")

        if start_line is not None and end_line is not None and end_line < start_line:
            raise ValueError("end_line must be greater than or equal to start_line.")

        path = self.resolve_path(relative_path)

        if not path.exists() or not path.is_file():
            raise RepositoryFileNotFoundError(
                f"Repository file does not exist: {relative_path}"
            )

        size_bytes = path.stat().st_size

        if size_bytes > self._max_file_bytes:
            raise RepositoryFileTooLargeError(
                f"File exceeds the maximum readable size of "
                f"{self._max_file_bytes} bytes: {relative_path}"
            )

        raw_content = path.read_bytes()

        if b"\x00" in raw_content:
            raise UnsupportedFileTypeError(
                f"Binary files may not be read: {relative_path}"
            )

        try:
            complete_content = raw_content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsupportedFileTypeError(
                f"File is not valid UTF-8 text: {relative_path}"
            ) from exc

        lines = complete_content.splitlines(keepends=True)
        total_lines = len(lines)

        if total_lines == 0:
            selected_content = ""
            effective_start = 0
            effective_end = 0
        else:
            effective_start = start_line or 1

            if effective_start > total_lines:
                raise ValueError(
                    f"start_line exceeds the file length of {total_lines} lines."
                )

            effective_end = min(end_line or total_lines, total_lines)

            selected_content = "".join(lines[effective_start - 1 : effective_end])

        return RepositoryDocument(
            relative_path=path.relative_to(self._root).as_posix(),
            name=path.name,
            suffix=path.suffix.casefold(),
            size_bytes=size_bytes,
            total_lines=total_lines,
            start_line=effective_start,
            end_line=effective_end,
            content=selected_content,
        )

    def build_tree(
        self,
        relative_path: str = "",
        *,
        max_depth: int = 4,
        include_files: bool = True,
        max_entries: int = 1000,
    ) -> RepositoryTree:
        """Build a bounded repository directory tree."""

        if not 0 <= max_depth <= 20:
            raise ValueError("max_depth must be between 0 and 20.")

        if not 1 <= max_entries <= 5000:
            raise ValueError("max_entries must be between 1 and 5000.")

        target = self.resolve_path(relative_path)

        if not target.exists() or not target.is_dir():
            raise RepositoryFileNotFoundError(
                f"Repository directory does not exist: {relative_path}"
            )

        entry_count = 0
        truncated = False

        def create_node(
            path: Path,
            depth: int,
        ) -> RepositoryTreeNode:
            nonlocal entry_count
            nonlocal truncated

            relative = path.relative_to(self._root)
            entry_count += 1

            children: list[RepositoryTreeNode] = []

            if path.is_dir() and depth < max_depth:
                candidates = sorted(
                    path.iterdir(),
                    key=lambda item: (
                        not item.is_dir(),
                        item.name.casefold(),
                    ),
                )

                for child in candidates:
                    if entry_count >= max_entries:
                        truncated = True
                        break

                    if child.is_symlink():
                        continue

                    child_relative = child.relative_to(self._root)

                    if child.is_dir():
                        if not is_visible_relative_path(
                            child_relative,
                            path_is_directory=True,
                        ):
                            continue

                        children.append(create_node(child, depth + 1))
                        continue

                    if not include_files or not child.is_file():
                        continue

                    if not is_visible_relative_path(child_relative):
                        continue

                    children.append(create_node(child, depth + 1))

            return RepositoryTreeNode(
                name=path.name if relative.parts else ".",
                relative_path=(relative.as_posix() if relative.parts else "."),
                kind="directory" if path.is_dir() else "file",
                size_bytes=None if path.is_dir() else path.stat().st_size,
                children=tuple(children),
            )

        root = create_node(target, 0)

        return RepositoryTree(
            root=root,
            entry_count=entry_count,
            truncated=truncated,
        )
