"""Observable assurance behavior and negative trust-boundary cases."""

import json
import subprocess
import sys

import pytest

from cp_knowledge_tools.assurance.report import Report, persist
from cp_knowledge_tools.assurance.repository import repository_state
from cp_knowledge_tools.assurance.supply import supply_chain
from cp_knowledge_tools.assurance.verify import run_check, verify
from cp_knowledge_tools.cli.cpks import main


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("artifacts/\n__pycache__/\n")
    (root / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="0.1"\ndependencies=[]\n'
    )
    (root / "tests").mkdir()
    (root / "tests/test_contract.py").write_text(
        "def test_contract():\n    assert 2 + 2 == 4\n"
    )
    for args in (
        ["init", "-b", "test"],
        ["add", "."],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def test_preflight_json_no_write_and_legacy_cli(repo, capsys):
    before = repository_state(repo)
    assert (
        main(["assurance", "preflight", "--repo-root", str(repo), "--no-evidence"]) == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["repository_state"]["head"] == before["head"]
    assert report["commit_state"] == "not_performed"
    assert not (repo / "artifacts").exists()
    assert main(["--version"]) == 0
    assert "cpks" in capsys.readouterr().out


def test_report_persistence_is_unique_and_rejects_symlink(repo, tmp_path):
    report = Report({}, repository_state(repo))
    first = persist(report, repo)
    original = first.read_bytes()
    second = persist(Report({}, repository_state(repo)), repo)
    assert first != second
    assert first.read_bytes() == original
    assert first.stat().st_mode & 0o077 == 0
    other = tmp_path / "other"
    other.mkdir()
    (other / "artifacts").symlink_to(repo / "artifacts", target_is_directory=True)
    with pytest.raises(OSError):
        persist(report, other)


def test_fingerprints_include_untracked_staged_and_deleted(repo):
    initial = repository_state(repo)
    (repo / "new.txt").write_text("new")
    (repo / "pyproject.toml").write_text("changed")
    subprocess.run(["git", "-C", str(repo), "add", "pyproject.toml"], check=True)
    (repo / "tests/test_contract.py").unlink()
    state = repository_state(repo)
    assert set(state["changed_paths"]) == {
        "new.txt",
        "pyproject.toml",
        "tests/test_contract.py",
    }
    assert state["input_hashes"]["tests/test_contract.py"] == "deleted"
    assert state["index_fingerprint"] != initial["index_fingerprint"]


def test_unknown_scope_and_symlinks_fail_closed(repo, tmp_path):
    with pytest.raises(ValueError):
        verify(repo, paths=("missing.py",))
    with pytest.raises(ValueError):
        verify(repo, paths=("../outside.py",))
    (repo / "link.py").symlink_to(tmp_path / "secret")
    with pytest.raises(ValueError):
        repository_state(repo)


def test_fast_scope_executes_real_tests_and_preserves_inputs(repo):
    test = repo / "tests/test_contract.py"
    test.write_text(
        "def test_contract():\n    assert False, 'expected failing contract'\n"
    )
    before = test.read_bytes()
    report = verify(repo, paths=("tests",), timeout=30)
    assert report.status == "failed"
    assert any(c["name"] == "pytest" and c["exit_code"] == 1 for c in report.checks)
    assert test.read_bytes() == before


def test_empty_scope_and_absent_tools_cannot_pass(repo):
    assert verify(repo).status == "incomplete"
    report = supply_chain(repo, profile="admission")
    assert report.status == "incomplete"
    assert report.checks[0]["inventory"]["acceptance"] == "not_evaluated"
    assert report.checks[0]["inventory"]["vulnerabilities"] == "not_checked"


def test_dependency_delta_binds_previous_to_repository(repo):
    first = persist(supply_chain(repo, profile="research"), repo)
    relative = str(first.relative_to(repo))
    same = supply_chain(repo, profile="delta", previous=relative)
    assert (
        next(c for c in same.checks if c["name"] == "dependency_delta")[
            "changed_dimensions"
        ]
        == []
    )
    document = json.loads(first.read_text())
    document["repository_state"]["root"] = "/different/repository"
    first.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="another repository"):
        supply_chain(repo, profile="delta", previous=relative)


def test_process_failure_timeout_and_raw_output_not_persisted(repo):
    report = Report({}, repository_state(repo))
    run_check(
        report,
        "failure",
        [sys.executable, "-c", "print('SENSITIVE_SENTINEL'); raise SystemExit(3)"],
        repo,
        10,
    )
    assert report.status == "failed"
    assert "SENSITIVE_SENTINEL" not in json.dumps(report.checks[0].get("output_policy"))
    timeout = Report({}, repository_state(repo))
    run_check(
        timeout,
        "timeout",
        [sys.executable, "-c", "import time; time.sleep(30)"],
        repo,
        1,
    )
    assert timeout.status == "incomplete"
    assert timeout.checks[0]["reason"] == "timeout"


def test_mixed_python_scope_reports_unmapped_sources(repo):
    (repo / "unmapped.py").write_text("answer = 1 / 0\n")
    report = verify(repo, paths=("unmapped.py", "tests/test_contract.py"))
    assert report.status == "incomplete"
    assert next(c for c in report.checks if c["name"] == "test_impact_mapping")[
        "paths"
    ] == ["unmapped.py"]


@pytest.mark.parametrize(
    "name,content",
    [("bad.json", "{ invalid"), ("bad.yaml", "a: ["), ("bad.toml", "invalid=")],
)
def test_malformed_structured_input_fails(repo, name, content):
    (repo / name).write_text(content)
    assert verify(repo, paths=(name,)).status == "failed"


def test_malformed_previous_and_missing_vault_have_stable_exit(repo, capsys):
    path = persist(Report({}, repository_state(repo)), repo)
    path.write_text(
        json.dumps({"schema_version": "cpks.assurance/1", "repository_state": []})
    )
    assert (
        main(
            [
                "assurance",
                "supply-chain",
                "--profile",
                "delta",
                "--repo-root",
                str(repo),
                "--previous",
                str(path.relative_to(repo)),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["disposition"] == "blocked"
    assert (
        main(
            [
                "drift",
                "audit",
                "--repo-root",
                str(repo),
                "--vault-root",
                str(repo / "missing"),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["disposition"] == "blocked"


def test_text_reports_findings_and_missing_checks(repo, capsys):
    path = persist(Report({}, repository_state(repo)), repo)
    (repo / "new.txt").write_text("changed")
    code = main(
        [
            "drift",
            "audit",
            "--repo-root",
            str(repo),
            "--previous",
            str(path.relative_to(repo)),
            "--format",
            "text",
            "--no-evidence",
        ]
    )
    assert code == 2
    output = capsys.readouterr().out
    assert "repository_input_hashes_changed" in output
    assert "--vault-root required" in output
