"""Text search for the read-only cpKnowledgeTools MCP server."""

from __future__ import annotations

from .errors import (
    RepositoryFileTooLargeError,
    UnsupportedFileTypeError,
)
from .models import SearchMatch
from .repository import Repository

MAX_RETURNED_LINE_LENGTH = 2_000


def truncate_line(line: str) -> str:
    """Limit unusually long lines in MCP responses."""

    if len(line) <= MAX_RETURNED_LINE_LENGTH:
        return line

    return line[:MAX_RETURNED_LINE_LENGTH] + "…"


def search_text(
    repository: Repository,
    query: str,
    *,
    path_prefix: str = "",
    case_sensitive: bool = False,
    context_lines: int = 1,
    max_results: int = 50,
) -> list[SearchMatch]:
    """Search UTF-8 text files inside the repository."""

    if not query:
        raise ValueError("query must not be empty.")

    if not 0 <= context_lines <= 10:
        raise ValueError("context_lines must be between 0 and 10.")

    if not 1 <= max_results <= 200:
        raise ValueError("max_results must be between 1 and 200.")

    normalized_query = query if case_sensitive else query.casefold()
    normalized_prefix = path_prefix.strip().replace("\\", "/").casefold()

    results: list[SearchMatch] = []

    for file_info in repository.list_files():
        if normalized_prefix and not file_info.relative_path.casefold().startswith(
            normalized_prefix
        ):
            continue

        try:
            document = repository.read_text_file(file_info.relative_path)
        except (
            RepositoryFileTooLargeError,
            UnsupportedFileTypeError,
        ):
            continue

        lines = document.content.splitlines()

        for index, line in enumerate(lines):
            searchable_line = line if case_sensitive else line.casefold()

            if normalized_query not in searchable_line:
                continue

            context_start = max(0, index - context_lines)
            context_end = min(len(lines), index + context_lines + 1)

            results.append(
                SearchMatch(
                    relative_path=document.relative_path,
                    line_number=index + 1,
                    line=truncate_line(line),
                    context_before=tuple(
                        truncate_line(value) for value in lines[context_start:index]
                    ),
                    context_after=tuple(
                        truncate_line(value) for value in lines[index + 1 : context_end]
                    ),
                )
            )

            if len(results) >= max_results:
                return results

    return results
