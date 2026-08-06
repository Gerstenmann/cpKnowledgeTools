from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cp_knowledge_tools.mcp.cp_tools.git import GitReader
from cp_knowledge_tools.mcp.cp_tools.repository import Repository

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="Git executable is unavailable.",
)


def run_git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def git_reader(tmp_path: Path) -> GitReader:
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "config", "user.name", "Test User")
    run_git(tmp_path, "config", "user.email", "test@example.invalid")

    source = tmp_path / "src"
    source.mkdir()

    (source / "app.py").write_text(
        "print('initial')\n",
        encoding="utf-8",
    )

    run_git(tmp_path, "add", ".")
    run_git(
        tmp_path,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "Initial commit",
    )

    repository = Repository(
        tmp_path,
        max_file_bytes=1_000_000,
    )

    return GitReader(repository)


def test_git_status_filters_denied_file_names(
    git_reader: GitReader,
) -> None:
    root = git_reader.root

    (root / "src" / "app.py").write_text(
        "print('changed')\n",
        encoding="utf-8",
    )
    (root / ".env").write_text(
        "TOKEN=secret\n",
        encoding="utf-8",
    )

    status = git_reader.status()

    assert status.clean is False
    assert any(entry.path == "src/app.py" for entry in status.entries)
    assert all(entry.path != ".env" for entry in status.entries)
    assert status.omitted_entries == 1


def test_git_diff_returns_worktree_diff(
    git_reader: GitReader,
) -> None:
    root = git_reader.root

    (root / "src" / "app.py").write_text(
        "print('changed')\n",
        encoding="utf-8",
    )

    result = git_reader.diff(
        relative_path="src/app.py",
        context_lines=1,
    )

    assert result.staged is False
    assert result.relative_path == "src/app.py"
    assert "print('changed')" in result.content
    assert result.truncated is False


def test_git_log_returns_commit_metadata(
    git_reader: GitReader,
) -> None:
    commits = git_reader.log(limit=5)

    assert len(commits) == 1
    assert commits[0].subject == "Initial commit"
    assert commits[0].author_name == "Test User"
