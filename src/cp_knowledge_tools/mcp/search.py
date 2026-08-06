"""Read-only search operations for cp-wiki Markdown files."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import (
    FrontmatterSearchMatch,
    TextSearchMatch,
    WikilinkResolution,
)
from .vault import Vault


def search_text(
    vault: Vault,
    query: str,
    *,
    case_sensitive: bool = False,
    context_lines: int = 1,
    max_results: int = 50,
) -> list[TextSearchMatch]:
    """Search Markdown files line by line."""

    normalized_query = query if case_sensitive else query.casefold()
    results: list[TextSearchMatch] = []

    if not query:
        return results

    if context_lines < 0:
        raise ValueError("context_lines must not be negative.")

    if max_results < 1:
        raise ValueError("max_results must be at least 1.")

    for file_info in vault.list_markdown_files():
        content = vault.read_markdown(file_info.relative_path)
        lines = content.splitlines()

        for index, line in enumerate(lines):
            haystack = line if case_sensitive else line.casefold()

            if normalized_query not in haystack:
                continue

            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)

            results.append(
                TextSearchMatch(
                    relative_path=file_info.relative_path,
                    line_number=index + 1,
                    line=line,
                    context_before=lines[start:index],
                    context_after=lines[index + 1 : end],
                )
            )

            if len(results) >= max_results:
                return results

    return results


def _value_matches(
    value: Any,
    expected: Any,
    *,
    case_sensitive: bool,
) -> bool:
    """Compare a frontmatter value with a requested value."""

    if isinstance(value, list):
        return any(
            _value_matches(
                item,
                expected,
                case_sensitive=case_sensitive,
            )
            for item in value
        )

    if isinstance(value, dict):
        return any(
            _value_matches(
                item,
                expected,
                case_sensitive=case_sensitive,
            )
            for item in value.values()
        )

    if isinstance(value, str) and isinstance(expected, str):
        if case_sensitive:
            return expected in value

        return expected.casefold() in value.casefold()

    return value == expected


def search_frontmatter(
    vault: Vault,
    field: str,
    expected: Any,
    *,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> list[FrontmatterSearchMatch]:
    """Search one top-level YAML frontmatter field."""

    if not field.strip():
        raise ValueError("field must not be empty.")

    if max_results < 1:
        raise ValueError("max_results must be at least 1.")

    results: list[FrontmatterSearchMatch] = []

    for file_info in vault.list_markdown_files():
        document = vault.read_document(file_info.relative_path)

        if field not in document.frontmatter:
            continue

        value = document.frontmatter[field]

        if not _value_matches(
            value,
            expected,
            case_sensitive=case_sensitive,
        ):
            continue

        results.append(
            FrontmatterSearchMatch(
                relative_path=file_info.relative_path,
                field=field,
                value=value,
            )
        )

        if len(results) >= max_results:
            break

    return results


def normalize_wikilink_target(target: str) -> str:
    """
    Normalize an Obsidian wikilink target.

    Removes aliases, heading references and block references.
    """

    normalized = target.strip()

    if normalized.startswith("[[") and normalized.endswith("]]"):
        normalized = normalized[2:-2]

    normalized = normalized.split("|", maxsplit=1)[0]
    normalized = normalized.split("#", maxsplit=1)[0]
    normalized = normalized.split("^", maxsplit=1)[0]

    return normalized.strip()


def resolve_wikilink(
    vault: Vault,
    target: str,
) -> WikilinkResolution:
    """Resolve a wikilink target against Markdown files in the vault."""

    normalized = normalize_wikilink_target(target)

    if not normalized:
        return WikilinkResolution(
            target=target,
            resolved_paths=[],
            ambiguous=False,
        )

    normalized_without_suffix = normalized.removesuffix(".md")
    normalized_casefold = normalized_without_suffix.casefold()

    exact_path_matches: list[str] = []
    stem_matches: list[str] = []

    for file_info in vault.list_markdown_files():
        relative_without_suffix = file_info.relative_path.removesuffix(".md")

        if relative_without_suffix.casefold() == normalized_casefold:
            exact_path_matches.append(file_info.relative_path)
            continue

        if file_info.name.removesuffix(".md").casefold() == normalized_casefold:
            stem_matches.append(file_info.relative_path)

    matches = exact_path_matches or stem_matches

    return WikilinkResolution(
        target=target,
        resolved_paths=sorted(matches, key=str.casefold),
        ambiguous=len(matches) > 1,
    )


def serialize_dataclasses(
    items: Iterable[object],
) -> list[dict[str, Any]]:
    """Convert slot-based dataclasses into JSON-compatible dictionaries."""

    from dataclasses import asdict

    return [asdict(item) for item in items]
