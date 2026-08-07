from pathlib import Path

import pytest

from cp_knowledge_tools.mcp.cp_wiki.errors import (
    InvalidJsonError,
    UnsupportedFileTypeError,
    VaultFileNotFoundError,
    VaultFileTooLargeError,
    VaultPathError,
)
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault


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


def test_list_json_files(tmp_path: Path) -> None:
    generated = tmp_path / "Generated"
    generated.mkdir()
    (generated / "report.json").write_text(
        '{"status": "ok"}',
        encoding="utf-8",
    )
    (generated / "ignored.md").write_text("# Ignored\n", encoding="utf-8")

    vault = Vault(tmp_path)

    files = vault.list_json_files()

    assert len(files) == 1
    assert files[0].relative_path == "Generated/report.json"
    assert files[0].suffix == ".json"


def test_read_markdown(tmp_path: Path) -> None:
    note = tmp_path / "Note.md"
    note.write_text("# Test\n", encoding="utf-8")

    vault = Vault(tmp_path)

    assert vault.read_markdown("Note.md") == "# Test\n"


def test_read_json(tmp_path: Path) -> None:
    data = tmp_path / "data.json"
    data.write_text(
        '{"status": "ok", "items": [1, 2, {"name": "example"}]}',
        encoding="utf-8",
    )

    vault = Vault(tmp_path)

    assert vault.read_json("data.json") == {
        "status": "ok",
        "items": [1, 2, {"name": "example"}],
    }


def test_read_json_accepts_utf8_bom(tmp_path: Path) -> None:
    data = tmp_path / "data.json"
    data.write_text('\ufeff{"status": "ok"}', encoding="utf-8")

    vault = Vault(tmp_path)

    assert vault.read_json("data.json") == {"status": "ok"}


def test_reject_invalid_json(tmp_path: Path) -> None:
    data = tmp_path / "invalid.json"
    data.write_text('{"status":', encoding="utf-8")

    vault = Vault(tmp_path)

    with pytest.raises(InvalidJsonError):
        vault.read_json("invalid.json")


def test_reject_oversized_json(tmp_path: Path) -> None:
    data = tmp_path / "large.json"
    data.write_text('{"value": "1234567890"}', encoding="utf-8")

    vault = Vault(tmp_path, max_json_bytes=5)

    with pytest.raises(VaultFileTooLargeError):
        vault.read_json("large.json")


def test_reject_non_json_for_json_reader(tmp_path: Path) -> None:
    note = tmp_path / "Note.md"
    note.write_text("# Test\n", encoding="utf-8")

    vault = Vault(tmp_path)

    with pytest.raises(UnsupportedFileTypeError):
        vault.read_json("Note.md")


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


def test_missing_json_file(tmp_path: Path) -> None:
    vault = Vault(tmp_path)

    with pytest.raises(VaultFileNotFoundError):
        vault.read_json("missing.json")


def test_reject_non_markdown_file(tmp_path: Path) -> None:
    file_path = tmp_path / "data.json"
    file_path.write_text("{}", encoding="utf-8")

    vault = Vault(tmp_path)

    with pytest.raises(UnsupportedFileTypeError):
        vault.read_markdown("data.json")
