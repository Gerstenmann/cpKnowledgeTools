"""Markdown and YAML frontmatter parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import MarkdownDocument

FRONTMATTER_DELIMITER = "---"


def split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Split YAML frontmatter from Markdown body.

    A frontmatter block is recognized only when the document starts with
    a line containing exactly `---`.
    """

    lines = content.splitlines(keepends=True)

    if not lines:
        return {}, ""

    if lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, content

    closing_index: int | None = None

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            closing_index = index
            break

    if closing_index is None:
        return {}, content

    raw_frontmatter = "".join(lines[1:closing_index])
    body = "".join(lines[closing_index + 1 :])

    parsed = yaml.safe_load(raw_frontmatter)

    if parsed is None:
        frontmatter: dict[str, Any] = {}
    elif isinstance(parsed, dict):
        frontmatter = parsed
    else:
        raise ValueError("YAML frontmatter must contain a mapping.")

    return frontmatter, body


def extract_markdown_title(
    body: str,
    frontmatter: dict[str, Any],
    fallback_path: str | Path | None = None,
) -> str | None:
    """Extract a display title from frontmatter, heading or filename."""

    frontmatter_title = frontmatter.get("title")

    if isinstance(frontmatter_title, str) and frontmatter_title.strip():
        return frontmatter_title.strip()

    for line in body.splitlines():
        stripped = line.strip()

        if stripped.startswith("# "):
            title = stripped[2:].strip()
            if title:
                return title

    if fallback_path is not None:
        return Path(fallback_path).stem

    return None


def parse_markdown(
    relative_path: str,
    content: str,
) -> MarkdownDocument:
    """Parse one Markdown document."""

    frontmatter, body = split_frontmatter(content)
    title = extract_markdown_title(
        body=body,
        frontmatter=frontmatter,
        fallback_path=relative_path,
    )

    return MarkdownDocument(
        relative_path=relative_path,
        frontmatter=frontmatter,
        body=body,
        title=title,
    )