import pytest

from cp_knowledge_tools.mcp.markdown import (
    extract_markdown_title,
    parse_markdown,
    split_frontmatter,
)


def test_split_frontmatter() -> None:
    content = (
        "---\n"
        "title: Example\n"
        "status: active\n"
        "---\n"
        "# Heading\n"
    )

    frontmatter, body = split_frontmatter(content)

    assert frontmatter == {
        "title": "Example",
        "status": "active",
    }
    assert body == "# Heading\n"


def test_document_without_frontmatter() -> None:
    content = "# Example\nText\n"

    frontmatter, body = split_frontmatter(content)

    assert frontmatter == {}
    assert body == content


def test_unclosed_frontmatter_is_treated_as_body() -> None:
    content = "---\ntitle: Example\n"

    frontmatter, body = split_frontmatter(content)

    assert frontmatter == {}
    assert body == content


def test_reject_non_mapping_frontmatter() -> None:
    content = "---\n- one\n- two\n---\n"

    with pytest.raises(ValueError):
        split_frontmatter(content)


def test_title_from_frontmatter() -> None:
    title = extract_markdown_title(
        body="# Heading\n",
        frontmatter={"title": "Frontmatter title"},
    )

    assert title == "Frontmatter title"


def test_title_from_first_level_heading() -> None:
    title = extract_markdown_title(
        body="Text\n# Heading\n",
        frontmatter={},
    )

    assert title == "Heading"


def test_title_from_filename() -> None:
    title = extract_markdown_title(
        body="Text\n",
        frontmatter={},
        fallback_path="Knowledge/Example Note.md",
    )

    assert title == "Example Note"


def test_parse_markdown() -> None:
    document = parse_markdown(
        relative_path="Knowledge/Example.md",
        content="---\nstatus: active\n---\n# Example\n",
    )

    assert document.relative_path == "Knowledge/Example.md"
    assert document.frontmatter == {"status": "active"}
    assert document.body == "# Example\n"
    assert document.title == "Example"