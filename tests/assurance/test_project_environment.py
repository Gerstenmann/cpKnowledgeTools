"""Failure-closed tool binding and fresh-environment provenance boundaries."""

import json
import subprocess
from pathlib import Path

import pytest

from cp_knowledge_tools.assurance import project_environment as module
from cp_knowledge_tools.assurance.execution import ProcessResult
from cp_knowledge_tools.assurance.repository import file_hash, repository_state
from cp_knowledge_tools.cli.cpks import main


@pytest.fixture
def context(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("artifacts/\n")
    (root / "AGENTS.md").write_text("foreign original\n")
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    # The adapter must not interpret or duplicate uv.lock's format.
    (root / "uv.lock").write_text("opaque official uv input\n")
    (root / ".python-version").write_text("3.14.6\n")
    binding = root / "config/assurance/development-tools.json"
    binding.parent.mkdir(parents=True)
    uv = tmp_path / "uv"
    uv.write_bytes(b"synthetic admitted executable")
    uv.chmod(0o700)
    python = tmp_path / "base-python"
    python.write_bytes(b"synthetic explicit interpreter")
    python.chmod(0o700)
    binding.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tool": {
                    "id": "uv",
                    "version": "0.12.7",
                    "platform": {"system": "Darwin", "machine": "arm64"},
                    "source_url": "https://github.com/astral-sh/uv",
                    "source_commit": "a" * 40,
                    "license_expression": "MIT OR Apache-2.0",
                    "archive": {
                        "url": "https://github.com/astral-sh/uv/releases/download/"
                        "0.12.7/uv-aarch64-apple-darwin.tar.gz",
                        "sha256": "b" * 64,
                    },
                    "executable_sha256": file_hash(uv),
                    "provenance": {
                        "method": "github-artifact-attestation",
                        "repository": "astral-sh/uv",
                        "evidence_ref": "artifacts/admission/attestation.json",
                    },
                    "assessment_ref": "config/assurance/project-environment.md",
                },
            }
        )
    )
    for arguments in (
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
        subprocess.run(
            ["git", "-C", str(root), *arguments], check=True, capture_output=True
        )
    (root / "AGENTS.md").write_text("foreign dirty change\n")
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    result = {
        "root": root,
        "uv": uv,
        "python": python,
        "environment": root / "artifacts/locking/environments/fresh",
        "cache_dir": root / "artifacts/locking/cache",
        "mode": "rebuild",
    }
    return result


class FakeProcesses:
    """Fixed protocol double; uv itself, not these tests, interprets lock contents."""

    def __init__(self, context):
        self.context = context
        self.calls = []
        self.version = b"uv 0.12.7 (61291a8ca 2026-08-27)\n"
        self.lock_code = 0
        self.sync_code = 0
        self.mutate_after_lock = None
        self.mutate_after_sync = None
        self.omit_creation = False
        self.base_overrides = {}
        self.target_overrides = {}

    def __call__(self, argv, root, timeout, *, environment, max_bytes):
        self.calls.append((argv, environment))
        ctx = self.context
        if "-c" in argv:
            target = argv[0] != str(ctx["python"])
            identity = {
                "implementation": "CPython",
                "version": "3.14.6",
                "executable": argv[0],
                "prefix": str(ctx["environment"]) if target else "/base-python",
                "base_prefix": "/base-python",
                "system": "Darwin",
                "machine": "arm64",
                "soabi": "cpython-314-darwin",
                "gil_disabled": False,
            }
            identity.update(self.target_overrides if target else self.base_overrides)
            return ProcessResult(0, json.dumps(identity).encode(), 0.01)
        if "--version" in argv:
            return ProcessResult(0, self.version, 0.01)
        if "lock" in argv:
            if self.mutate_after_lock:
                self.mutate_after_lock()
            return ProcessResult(self.lock_code, b"", 0.01)
        assert "sync" in argv
        if "--check" not in argv and not self.omit_creation:
            target = Path(environment["UV_PROJECT_ENVIRONMENT"])
            (target / "bin").mkdir(parents=True)
            (target / "bin/python").write_bytes(b"new environment python")
        if self.mutate_after_sync:
            self.mutate_after_sync()
        return ProcessResult(self.sync_code, b"", 0.01)


@pytest.fixture
def processes(context, monkeypatch):
    fake = FakeProcesses(context)
    monkeypatch.setattr(module, "execute", fake)
    return fake


def run(context, **changes):
    return module.project_environment(**(context | changes))


@pytest.mark.parametrize("name", ["uv.lock", ".python-version", "pyproject.toml"])
def test_missing_inputs_fail_before_any_execution(context, processes, name):
    (context["root"] / name).unlink()
    assert run(context).status == "failed"
    assert processes.calls == []
    assert not context["environment"].exists()


@pytest.mark.parametrize("problem", ["missing", "hash", "symlink"])
def test_wrong_tool_cannot_execute(context, processes, problem, tmp_path):
    uv = context["uv"]
    if problem == "missing":
        uv.unlink()
    elif problem == "hash":
        uv.write_bytes(b"unreviewed executable replacement")
    else:
        other = tmp_path / "copy"
        other.write_bytes(uv.read_bytes())
        other.chmod(0o700)
        uv.unlink()
        uv.symlink_to(other)
    assert run(context).status == "failed"
    assert processes.calls == []


def test_wrong_version_is_rejected_before_lock_or_sync(context, processes):
    processes.version = b"uv 0.12.8\n"
    assert run(context).status == "failed"
    assert not any("sync" in argv or "lock" in argv for argv, _ in processes.calls)


@pytest.mark.parametrize(
    "patch",
    [
        {"version": "3.14.5"},
        {"implementation": "PyPy"},
        {"prefix": "/a-venv"},
        {"machine": "x86_64"},
        {"executable": "/different/python"},
        {"gil_disabled": True},
    ],
)
def test_wrong_base_interpreter_fails_before_uv(context, processes, patch):
    processes.base_overrides = patch
    assert run(context).status == "failed"
    assert len(processes.calls) == 1


@pytest.mark.parametrize("pin", ["3.14", "3.14.6\n3.14.7", "3.13.6", "latest"])
def test_pin_requires_exact_reviewed_python_series(context, processes, pin):
    (context["root"] / ".python-version").write_text(pin)
    assert run(context).status == "failed"
    assert processes.calls == []


def test_stale_lock_and_pyproject_drift_are_delegated_to_uv(context, processes):
    (context["root"] / "pyproject.toml").write_text("changed project requirement")
    processes.lock_code = 1
    report = run(context)
    assert report.status == "failed"
    assert (
        next(check for check in report.checks if check["name"] == "lock_freshness")[
            "exit_code"
        ]
        == 1
    )
    assert not any("sync" in argv for argv, _ in processes.calls)


def test_fresh_rebuild_has_fixed_flags_and_sanitized_state(
    context, processes, monkeypatch
):
    for name in (
        "UV_INDEX",
        "PIP_INDEX_URL",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "AWS_SECRET_ACCESS_KEY",
    ):
        monkeypatch.setenv(name, "SECRET_SENTINEL")
    report = run(context, allow_network=True)
    assert report.status == "passed"
    assert report.scope["fresh_rebuild"] == "observed_absent_then_created"
    assert report.decision == "not_evaluated"
    assert context["environment"].is_dir()
    for argv, env in processes.calls:
        assert "SECRET_SENTINEL" not in str(env)
        assert env["PATH"] == "/usr/bin:/bin"
        assert env["UV_PROJECT_ENVIRONMENT"] == str(context["environment"])
        if "lock" in argv or "sync" in argv:
            for option in (
                "--no-config",
                "--no-python-downloads",
                "--no-managed-python",
            ):
                assert option in argv
            assert argv[argv.index("--python") + 1] == str(context["python"])
            assert "--offline" not in argv
        elif "-c" in argv:
            assert argv[1:3] == ["-I", "-B"]
    sync = next(argv for argv, _ in processes.calls if "sync" in argv)
    assert "--locked" in sync and "--no-build" in sync
    assert sync[sync.index("--extra") + 1] == "dev"


def test_offline_frozen_still_checks_freshness_first(context, processes):
    assert run(context, offline_frozen=True).status == "passed"
    lock, sync = [
        argv for argv, _ in processes.calls if "sync" in argv or "lock" in argv
    ]
    assert "lock" in lock and "--check" in lock and "--offline" in lock
    assert "--frozen" in sync and "--offline" in sync and "--locked" not in sync


@pytest.mark.parametrize("changes", [{"mode": "check"}, {"allow_network": True}])
def test_frozen_does_not_weaken_check_or_network_boundary(context, processes, changes):
    with pytest.raises(ValueError, match="offline rebuild"):
        run(context, offline_frozen=True, **changes)
    assert processes.calls == []


def test_check_is_nonmutating_and_cannot_claim_rebuild_freshness(context, processes):
    target = context["environment"]
    target.mkdir(parents=True)
    sentinel = target / "unchanged"
    sentinel.write_text("original")
    before = set(target.rglob("*"))
    report = run(context, mode="check")
    assert report.status == "incomplete" and report.exit_code == 2
    assert report.scope["fresh_rebuild"] == "unobserved"
    assert set(target.rglob("*")) == before and sentinel.read_text() == "original"
    assert (
        next(argv for argv, _ in processes.calls if "sync" in argv).count("--check")
        == 1
    )


def test_routine_check_is_nonmutating_without_freshness_requirement(context, processes):
    target = context["environment"]
    target.mkdir(parents=True)
    report = run(context, mode="routine_check")
    assert report.status == "passed"
    assert report.scope["fresh_rebuild"] == "not_applicable"
    assert (
        next(c for c in report.checks if c["name"] == "fresh_rebuild")["status"]
        == "not_applicable"
    )
    command = next(argv for argv, _ in processes.calls if "sync" in argv)
    assert "--check" in command and "--offline" in command and "--locked" in command
    assert list(target.iterdir()) == []


def test_routine_check_cannot_enable_network(context, processes):
    with pytest.raises(ValueError, match="network-off"):
        run(context, mode="routine_check", allow_network=True)
    assert processes.calls == []


@pytest.mark.parametrize(
    "path",
    [
        ".venv",
        "artifacts/assurance/scanner-tools/python",
        "elsewhere",
        "artifacts/locking/environments/a/b",
    ],
)
def test_unsafe_targets_are_rejected_without_execution(context, processes, path):
    target = context["root"] / path
    target.mkdir(parents=True)
    (target / "sentinel").write_text("preserve")
    assert run(context, environment=target).status == "failed"
    assert (target / "sentinel").read_text() == "preserve"
    assert processes.calls == []


def test_existing_and_symlink_target_are_preserved(context, processes, tmp_path):
    target = context["environment"]
    target.mkdir(parents=True)
    assert run(context).status == "failed"
    target.rmdir()
    target.symlink_to(tmp_path, target_is_directory=True)
    assert run(context).status == "failed"
    assert target.is_symlink()
    assert processes.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"prefix": "/old/.venv"},
        {"base_prefix": "/other-base"},
        {"soabi": "cpython-314t-darwin"},
        {"gil_disabled": True},
    ],
)
def test_target_identity_must_match_created_environment(context, processes, changes):
    processes.target_overrides = changes
    report = run(context)
    assert report.status == "failed"
    assert report.scope["fresh_rebuild"] == "unobserved"
    assert context["environment"].exists()  # Failed targets are retained for diagnosis.


@pytest.mark.parametrize(
    "name",
    [
        "uv.lock",
        "pyproject.toml",
        ".python-version",
        "config/assurance/development-tools.json",
    ],
)
def test_changed_inputs_during_sync_cannot_pass(context, processes, name):
    processes.mutate_after_sync = lambda: (context["root"] / name).write_text("changed")
    report = run(context)
    assert report.status == "failed"
    unchanged = next(
        check
        for check in report.checks
        if check["name"] == "environment_inputs_unchanged"
    )
    assert unchanged["status"] == "failed"


def test_generated_pylock_is_not_canonical_and_foreign_work_index_are_preserved(
    context, processes
):
    generated = context["root"] / "artifacts/locking/pylock.toml"
    generated.parent.mkdir(parents=True)
    generated.write_text("deliberately invalid export evidence")
    before = repository_state(context["root"])
    assert run(context).status == "passed"
    after = repository_state(context["root"])
    assert after["head"] == before["head"]
    assert after["index_fingerprint"] == before["index_fingerprint"]
    assert after["input_hashes"] == before["input_hashes"]
    assert generated.read_text() == "deliberately invalid export evidence"


def test_cli_requires_explicit_paths_and_reports_unobserved_freshness(
    context, processes, capsys
):
    context["environment"].mkdir(parents=True)
    arguments = ["assurance", "environment", "--no-evidence"]
    for option, key in (
        ("--repo-root", "root"),
        ("--uv", "uv"),
        ("--python", "python"),
        ("--environment", "environment"),
        ("--cache-dir", "cache_dir"),
    ):
        arguments.extend([option, str(context[key])])
    assert main(arguments) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["scope"]["fresh_rebuild"] == "unobserved"


@pytest.mark.parametrize("changed", ["uv", "python", "pyproject.toml"])
def test_dependency_or_input_replacement_stops_before_sync(context, processes, changed):
    path = context.get(changed, context["root"] / changed)
    processes.mutate_after_lock = lambda: path.write_bytes(b"replaced during check")
    assert run(context).status == "failed"
    assert not any("sync" in argv for argv, _ in processes.calls)


def test_uv_success_without_target_creation_does_not_prove_freshness(
    context, processes
):
    processes.omit_creation = True
    report = run(context)
    assert report.status == "failed"
    assert report.scope["fresh_rebuild"] == "unobserved"
    assert not any(
        "-c" in argv and argv[0] != str(context["python"])
        for argv, _ in processes.calls
    )


@pytest.mark.parametrize(
    "path",
    [".venv", "artifacts/assurance/scanner-tools", "artifacts/locking/cache/child"],
)
def test_cache_cannot_select_unreviewed_write_scope(context, processes, path):
    assert run(context, cache_dir=context["root"] / path).status == "failed"
    assert processes.calls == []


def test_parent_symlink_is_not_a_fresh_environment_boundary(
    context, processes, tmp_path
):
    parent = context["environment"].parent
    parent.parent.mkdir(parents=True)
    parent.symlink_to(tmp_path, target_is_directory=True)
    assert run(context).status == "failed"
    assert processes.calls == []
    assert not (tmp_path / context["environment"].name).exists()


@pytest.mark.parametrize(
    "problem", ["unknown_command", "schema", "source", "license", "reference"]
)
def test_malformed_binding_cannot_grant_execution(context, processes, problem):
    path = context["root"] / "config/assurance/development-tools.json"
    binding = json.loads(path.read_text())
    if problem == "unknown_command":
        binding["tool"]["command"] = ["arbitrary", "shell"]
    elif problem == "schema":
        binding["schema_version"] = True
    elif problem == "source":
        binding["tool"]["source_url"] = "https://unreviewed.invalid/uv"
    elif problem == "license":
        binding["tool"]["license_expression"] = "unknown"
    else:
        binding["tool"]["assessment_ref"] = "../outside.md"
    path.write_text(json.dumps(binding))
    assert run(context).status == "failed"
    assert processes.calls == []


def test_native_tool_hash_budget_supports_binary_larger_than_default(
    context, processes
):
    with context["uv"].open("r+b") as stream:
        stream.truncate(10_000_001)
    path = context["root"] / "config/assurance/development-tools.json"
    binding = json.loads(path.read_text())
    binding["tool"]["executable_sha256"] = file_hash(
        context["uv"], max_bytes=100_000_000
    )
    path.write_text(json.dumps(binding))
    assert run(context).status == "passed"


def test_api_cannot_treat_text_as_network_authorization(context, processes):
    with pytest.raises(ValueError):
        run(context, allow_network="false")
    assert processes.calls == []
