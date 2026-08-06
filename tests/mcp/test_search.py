from pathlib import Path

from cp_knowledge_tools.mcp.cp_wiki.search import (
    normalize_wikilink_target,
    resolve_wikilink,
    search_frontmatter,
    search_text,
)
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault


def test_search_text(tmp_path: Path) -> None:
    note = tmp_path / "Knowledge" / "Example.md"
    note.parent.mkdir()
    note.write_text(
        "# Example\nFirst line\nImportant architecture decision\nLast line\n",
        encoding="utf-8",
    )

    vault = Vault(tmp_path)

    results = search_text(
        vault,
        "architecture",
        context_lines=1,
    )

    assert len(results) == 1
    assert results[0].relative_path == "Knowledge/Example.md"
    assert results[0].line_number == 3
    assert results[0].context_before == ["First line"]
    assert results[0].context_after == ["Last line"]


def test_search_text_case_insensitive(tmp_path: Path) -> None:
    note = tmp_path / "Example.md"
    note.write_text("Governance Framework\n", encoding="utf-8")

    vault = Vault(tmp_path)

    results = search_text(vault, "governance")

    assert len(results) == 1


def test_search_frontmatter_string(tmp_path: Path) -> None:
    note = tmp_path / "Example.md"
    note.write_text(
        "---\nstatus: active\ntype: specification\n---\n# Example\n",
        encoding="utf-8",
    )

    vault = Vault(tmp_path)

    results = search_frontmatter(
        vault,
        field="status",
        expected="active",
    )

    assert len(results) == 1
    assert results[0].relative_path == "Example.md"
    assert results[0].value == "active"


def test_search_frontmatter_list(tmp_path: Path) -> None:
    note = tmp_path / "Example.md"
    note.write_text(
        "---\ntags:\n  - governance\n  - architecture\n---\n",
        encoding="utf-8",
    )

    vault = Vault(tmp_path)

    results = search_frontmatter(
        vault,
        field="tags",
        expected="architecture",
    )

    assert len(results) == 1


def test_normalize_wikilink_target() -> None:
    assert (
        normalize_wikilink_target("[[Systems/Architecture#Scope|Architecture]]")
        == "Systems/Architecture"
    )


def test_resolve_wikilink_exact_path(tmp_path: Path) -> None:
    note = tmp_path / "Systems" / "Architecture.md"
    note.parent.mkdir()
    note.write_text("# Architecture\n", encoding="utf-8")

    vault = Vault(tmp_path)

    result = resolve_wikilink(
        vault,
        "Systems/Architecture",
    )

    assert result.resolved_paths == ["Systems/Architecture.md"]
    assert result.ambiguous is False


def test_resolve_wikilink_by_filename(tmp_path: Path) -> None:
    first = tmp_path / "Systems" / "Architecture.md"
    second = tmp_path / "Projects" / "Architecture.md"

    first.parent.mkdir()
    second.parent.mkdir()

    first.write_text("# System Architecture\n", encoding="utf-8")
    second.write_text("# Project Architecture\n", encoding="utf-8")

    vault = Vault(tmp_path)

    result = resolve_wikilink(vault, "Architecture")

    assert result.resolved_paths == [
        "Projects/Architecture.md",
        "Systems/Architecture.md",
    ]
    assert result.ambiguous is True
