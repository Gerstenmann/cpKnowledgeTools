"""Restricted read-only Git access for the cpKnowledgeTools MCP server."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .errors import GitCommandError, GitRepositoryError
from .models import (
    GitCommit,
    GitDiff,
    GitStatus,
    GitStatusEntry,
)
from .repository import (
    DENIED_EXACT_FILE_NAMES,
    DENIED_FILE_SUFFIXES,
    EXCLUDED_DIRECTORY_NAMES,
    Repository,
    is_visible_relative_path,
)

MAX_GIT_OUTPUT_CHARACTERS = 200_000
GIT_TIMEOUT_SECONDS = 15


class GitReader:
    """Restricted wrapper around explicitly permitted Git read commands."""

    def __init__(self, repository: Repository) -> None:

        self._repository = repository
        self._root = repository.root

        top_level = Path(self._run(["rev-parse", "--show-toplevel"]).strip()).resolve()

        if top_level != self._root:
            raise GitRepositoryError(
                "Configured repository root is not the Git top-level "
                f"directory: {self._root}"
            )

    @property
    def root(self) -> Path:
        """Return the configured Git repository root."""

        return self._root

    def _run(self, arguments: list[str]) -> str:
        """Execute one predefined read-only Git invocation."""

        environment = os.environ.copy()
        environment.update(
            {
                "GIT_PAGER": "cat",
                "PAGER": "cat",
                "LC_ALL": "C",
            }
        )

        try:
            completed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._root),
                    "--no-pager",
                    *arguments,
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=GIT_TIMEOUT_SECONDS,
                env=environment,
            )
        except FileNotFoundError as exc:
            raise GitCommandError("The Git executable is not available.") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitCommandError(
                "The permitted Git command exceeded its timeout."
            ) from exc

        if completed.returncode != 0:
            message = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"Git exited with status {completed.returncode}."
            )
            raise GitCommandError(message)

        return completed.stdout

    def _validate_relative_path(
        self,
        relative_path: str,
    ) -> str | None:
        """Validate and normalize an optional repository path."""

        normalized = relative_path.strip()

        if not normalized:
            return None

        resolved = self._repository.resolve_path(normalized)

        return resolved.relative_to(self._root).as_posix()

    @staticmethod
    def _safe_diff_pathspecs() -> list[str]:
        """Return exclusions for common secret and generated paths."""

        exclusions = [
            f":(exclude,glob)**/{directory}/**"
            for directory in sorted(EXCLUDED_DIRECTORY_NAMES)
        ]

        exclusions.extend(
            f":(exclude,glob)**/{file_name}"
            for file_name in sorted(DENIED_EXACT_FILE_NAMES)
        )

        exclusions.extend(
            f":(exclude,glob)**/*{suffix}" for suffix in sorted(DENIED_FILE_SUFFIXES)
        )

        exclusions.append(":(exclude,glob)**/.env.*")

        return [".", *exclusions]

    def status(self) -> GitStatus:
        """Return structured Git status without exposing denied paths."""

        branch = self._run(["branch", "--show-current"]).strip() or None
        head = self._run(["rev-parse", "HEAD"]).strip()

        output = self._run(
            [
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ]
        )

        tokens = output.split("\0")
        entries: list[GitStatusEntry] = []
        raw_entry_count = 0
        index = 0

        while index < len(tokens):
            record = tokens[index]
            index += 1

            if not record:
                continue

            if len(record) < 4:
                continue

            raw_entry_count += 1

            index_status = record[0]
            worktree_status = record[1]
            path = record[3:]
            original_path: str | None = None

            if index_status in {"R", "C"} or worktree_status in {"R", "C"}:
                if index < len(tokens) and tokens[index]:
                    original_path = tokens[index]
                    index += 1

            path_visible = is_visible_relative_path(path)
            original_visible = original_path is None or is_visible_relative_path(
                original_path
            )

            if not path_visible or not original_visible:
                continue

            entries.append(
                GitStatusEntry(
                    path=path,
                    index_status=index_status,
                    worktree_status=worktree_status,
                    original_path=original_path,
                )
            )

        return GitStatus(
            branch=branch,
            head=head,
            clean=raw_entry_count == 0,
            entries=tuple(entries),
            omitted_entries=raw_entry_count - len(entries),
        )

    def diff(
        self,
        *,
        relative_path: str = "",
        staged: bool = False,
        context_lines: int = 3,
    ) -> GitDiff:
        """Return a bounded unstaged or staged Git diff."""

        if not 0 <= context_lines <= 20:
            raise ValueError("context_lines must be between 0 and 20.")

        normalized_path = self._validate_relative_path(relative_path)

        arguments = ["diff"]

        if staged:
            arguments.append("--cached")

        arguments.extend(
            [
                "--no-ext-diff",
                "--no-color",
                f"--unified={context_lines}",
                "--",
            ]
        )

        if normalized_path:
            arguments.append(normalized_path)
        else:
            arguments.extend(self._safe_diff_pathspecs())

        complete_content = self._run(arguments)
        character_count = len(complete_content)
        truncated = character_count > MAX_GIT_OUTPUT_CHARACTERS

        content = complete_content[:MAX_GIT_OUTPUT_CHARACTERS]

        if truncated:
            content += "\n\n[Output truncated by cp-tools read-only MCP server.]\n"

        return GitDiff(
            staged=staged,
            relative_path=normalized_path,
            character_count=character_count,
            truncated=truncated,
            content=content,
        )

    def log(
        self,
        *,
        relative_path: str = "",
        limit: int = 20,
    ) -> list[GitCommit]:
        """Return bounded commit metadata, optionally filtered by path."""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        normalized_path = self._validate_relative_path(relative_path)

        arguments = [
            "log",
            f"--max-count={limit}",
            "--date=iso-strict",
            "--format=%H%x1f%h%x1f%aI%x1f%an%x1f%s%x1e",
        ]

        if normalized_path:
            arguments.extend(["--", normalized_path])

        output = self._run(arguments)
        commits: list[GitCommit] = []

        for raw_record in output.split("\x1e"):
            record = raw_record.strip()

            if not record:
                continue

            fields = record.split("\x1f", maxsplit=4)

            if len(fields) != 5:
                continue

            commits.append(
                GitCommit(
                    commit=fields[0],
                    short_commit=fields[1],
                    author_date=fields[2],
                    author_name=fields[3],
                    subject=fields[4],
                )
            )

        return commits
