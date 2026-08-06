from pathlib import Path

import pytest

from cp_knowledge_tools.mcp.cp_tools.repository import Repository


def create_repository(root: Path) -> Repository:
    return Repository(root, max_file_bytes=1_000_000)


def test_read_selected_line_range(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text(
        "line 1\nline 2\nline 3\nline 4\n",
        encoding="utf-8",
    )

    document = create_repository(tmp_path).read_text_file(
        "example.py",
        start_line=2,
        end_line=3,
    )

    assert document.total_lines == 4
    assert document.start_line == 2
    assert document.end_line == 3
    assert document.content == "line 2\nline 3\n"


def test_reject_invalid_line_range(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text("line 1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        create_repository(tmp_path).read_text_file(
            "example.py",
            start_line=2,
        )


def test_find_repository_files(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()

    (source / "server.py").write_text("", encoding="utf-8")
    (source / "models.py").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("", encoding="utf-8")

    results = create_repository(tmp_path).find_files(
        "server",
        suffix=".py",
    )

    assert [result.relative_path for result in results] == ["src/server.py"]


def test_repository_tree_excludes_sensitive_paths(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "app.py").write_text("", encoding="utf-8")

    virtual_environment = tmp_path / ".venv"
    virtual_environment.mkdir()
    (virtual_environment / "secret.py").write_text("", encoding="utf-8")

    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")

    tree = create_repository(tmp_path).build_tree(max_depth=3)

    child_names = {child.name for child in tree.root.children}

    assert "src" in child_names
    assert ".venv" not in child_names
    assert ".env" not in child_names
