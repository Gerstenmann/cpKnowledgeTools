from pathlib import Path

import pytest

from cp_knowledge_tools.mcp.errors import (
    UnsupportedFileTypeError,
    VaultFileNotFoundError,
    VaultPathError,
)
from cp_knowledge_tools.mcp.vault import Vault


def test_list_markdown_files(tmp_path: Path) -> None:
    (tmp_path / "Knowledge").mkdir()
    (tmp_path / "Knowledge" / "Example.md").write_text(
        "# Example\n",
        encoding="utf-8",
    )
    (tmp_path / "ignored.txt").write_text("ignored", encoding="utf-8")

    vault = Vault(tmp_path)

    files = vault.list_markdown_files()

    assert len(files) == 1
    assert files[0].relative_path == "Knowledge/Example.md"


def test_read_markdown(tmp_path: Path) -> None:
    note = tmp_path / "Note.md"
    note.write_text("# Test\n", encoding="utf-8")

    vault = Vault(tmp_path)

    assert vault.read_markdown("Note.md") == "# Test\n"


def test_reject_absolute_path(tmp_path: Path) -> None:
    vault = Vault(tmp_path)

    with pytest.raises(VaultPathError):
        vault.resolve_path("/etc/passwd")


def test_reject_parent_traversal(tmp_path: Path) -> None:
    vault = Vault(tmp_path)

    with pytest.raises(VaultPathError):
        vault.resolve_path("../outside.md")


def test_missing_file(tmp_path: Path) -> None:
    vault = Vault(tmp_path)

    with pytest.raises(VaultFileNotFoundError):
        vault.read_markdown("missing.md")


def test_reject_non_markdown_file(tmp_path: Path) -> None:
    file_path = tmp_path / "data.json"
    file_path.write_text("{}", encoding="utf-8")

    vault = Vault(tmp_path)

    with pytest.raises(UnsupportedFileTypeError):
        vault.read_markdown("data.json")
