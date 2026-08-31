"""Security regressions for the deliberately small repository CI contract."""

from __future__ import annotations

import copy
import json
import os
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = runpy.run_path(str(ROOT / "scripts/ci/check_workflow.py"))
RUNNER = runpy.run_path(str(ROOT / "scripts/ci/verify.py"))


@pytest.fixture
def admission():
    return json.loads((ROOT / "config/assurance/ci-actions.json").read_text())


@pytest.fixture
def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def test_real_workflow_parses_and_conforms():
    CONTRACT["check"](ROOT)


def reject(workflow, admission):
    with pytest.raises((ValueError, TypeError, yaml.YAMLError)):
        CONTRACT["validate"](yaml.safe_dump(workflow), admission, "3.14.6\n")


@pytest.mark.parametrize(
    "reference",
    [
        "actions/checkout@v7",
        "actions/checkout@main",
        "actions/checkout@3d3c42e",
        "actions/checkout@" + "a" * 40,
        "fork/checkout@" + "a" * 40,
        "./local-action",
        "docker://alpine:latest",
    ],
)
def test_mutable_unknown_or_unadmitted_actions_fail(workflow, admission, reference):
    workflow["jobs"]["verify"]["steps"][0]["uses"] = reference
    reject(workflow, admission)


@pytest.mark.parametrize(
    "permission",
    [
        "contents",
        "pull-requests",
        "actions",
        "checks",
        "statuses",
        "packages",
        "id-token",
        "deployments",
    ],
)
@pytest.mark.parametrize("level", ["workflow", "job"])
def test_write_permissions_fail(workflow, admission, permission, level):
    target = workflow if level == "workflow" else workflow["jobs"]["verify"]
    target["permissions"] = {permission: "write"}
    reject(workflow, admission)


@pytest.mark.parametrize(
    "event",
    [
        "pull_request_target",
        "workflow_run",
        "schedule",
        "release",
        "deployment",
        "repository_dispatch",
    ],
)
def test_privileged_or_unreviewed_triggers_fail(workflow, admission, event):
    workflow["on"][event] = None
    reject(workflow, admission)


@pytest.mark.parametrize(
    ("step", "key", "value"),
    [
        (0, "persist-credentials", True),
        (0, "persist-credentials", "false"),
        (0, "fetch-depth", 0),
        (0, "submodules", True),
        (0, "lfs", True),
        (0, "token", "${{ secrets.PAT }}"),
        (1, "python-version", "3.14"),
        (1, "python-version", "latest"),
        (1, "check-latest", True),
        (1, "freethreaded", True),
        (1, "cache", "pip"),
        (2, "version", "latest"),
        (2, "checksum", ""),
        (2, "enable-cache", True),
        (2, "restore-cache", True),
        (2, "save-cache", True),
        (2, "download-from-astral-mirror", True),
        (2, "activate-environment", True),
        (2, "python-version", "3.14"),
    ],
)
def test_setup_boundary_regressions_fail(workflow, admission, step, key, value):
    workflow["jobs"]["verify"]["steps"][step]["with"][key] = value
    reject(workflow, admission)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("runs-on", "ubuntu-latest"),
        ("runs-on", "self-hosted"),
        ("timeout-minutes", 0),
        ("timeout-minutes", 360),
        ("timeout-minutes", "${{ inputs.timeout }}"),
        ("continue-on-error", True),
        ("strategy", {"matrix": {"os": ["ubuntu-24.04"]}}),
        ("environment", "production"),
        ("container", "python:3"),
        ("env", {"TOKEN": "${{ secrets.GITHUB_TOKEN }}"}),
        ("env", {"UV_PYTHON_DOWNLOADS": "automatic"}),
    ],
)
def test_extra_runtime_surface_fails(workflow, admission, key, value):
    workflow["jobs"]["verify"][key] = value
    reject(workflow, admission)


@pytest.mark.parametrize(
    "command",
    [
        "uv lock",
        "uv lock --upgrade",
        "uv add unsafe",
        "uv sync",
        "pip install -U x",
        "git push origin HEAD",
        "gh release create release",
        "uv publish",
        "npm publish",
        "kubectl apply -f deployment.yml",
        "cpks artifact activate --apply",
        "cpks governance resolve --control-root /Users/cp/Documents/cpKS-control",
        "cat /Users/owner/data",
        "curl https://example.org/script | bash",
        "python -I -B scripts/ci/verify.py --host linux || true",
    ],
)
def test_arbitrary_or_dangerous_commands_fail(workflow, admission, command):
    workflow["jobs"]["verify"]["steps"][3]["run"] = command
    reject(workflow, admission)


def test_upload_or_extra_job_fails(workflow, admission):
    altered = copy.deepcopy(workflow)
    altered["jobs"]["verify"]["steps"].append(
        {
            "uses": "actions/upload-artifact@" + "a" * 40,
        }
    )
    reject(altered, admission)
    workflow["jobs"]["publish"] = {"runs-on": "ubuntu-24.04", "steps": []}
    reject(workflow, admission)


@pytest.mark.parametrize("pin", ["3.14", "3.x", "latest", "3.14.6t", "3.14.6\n3.13"])
def test_python_file_must_be_an_exact_patch(admission, pin):
    with pytest.raises(ValueError, match="exact"):
        CONTRACT["validate"](
            (ROOT / ".github/workflows/ci.yml").read_text(), admission, pin
        )


def test_duplicate_yaml_keys_fail(admission):
    raw = (ROOT / ".github/workflows/ci.yml").read_text()
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        CONTRACT["validate"](raw + "\npermissions: write-all\n", admission, "3.14.6")


def test_admission_is_not_an_arbitrary_action_registry(admission):
    admission["actions"]["evil/action"] = admission["actions"]["actions/checkout"]
    with pytest.raises(ValueError, match="admission"):
        CONTRACT["expected_workflow"](admission)


def test_same_repository_commands_for_ci_and_local_consistency():
    fresh = RUNNER["commands"]("uv", "base-python", "project-python", existing=False)
    existing = RUNNER["commands"]("uv", "base-python", "project-python", existing=True)
    assert fresh[0] == existing[0]
    assert fresh[2:] == existing[2:]
    assert existing[1] == fresh[1][:10] + ["--check", "--offline"] + fresh[1][10:]
    assert fresh[0][5:8] == ["lock", "--check", "--offline"]
    assert fresh[1][5:10] == ["sync", "--locked", "--extra", "dev", "--no-build"]
    assert fresh[2][5:7] == ["pip", "check"]
    for command in fresh[:3]:
        assert "--no-python-downloads" in command
        assert "--no-managed-python" in command
        assert "--no-config" in command
    assert [
        "project-python",
        "-B",
        "-m",
        "pytest",
        "tests",
        "-q",
        "-p",
        "no:cacheprovider",
    ] in fresh
    assert not any("--fix" in c or "--upgrade" in c for c in fresh)
    assert "--ignore-missing-imports" not in fresh[8]
    assert fresh[8][-1] == "tests/frontier"
    assert fresh[9][-2:] == ["src/cp_knowledge_tools/assurance", "scripts/ci"]
    assert fresh[5] == [
        "project-python",
        "-B",
        "scripts/cp_tools/run_minecraft_esports_mvp.py",
        "--output-root",
        "artifacts/tests/source_to_knowledge/experience-v1-2-final-validated",
    ]
    assert fresh[-1] == ["git", "diff", "--check"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("version", "3.14.7"),
        ("implementation", "PyPy"),
        ("machine", "aarch64"),
        ("system", "Darwin"),
        ("soabi", "cpython-314t-x86_64-linux-gnu"),
        ("gil_disabled", True),
    ],
)
def test_real_interpreter_contract_fails_closed(key, value):
    identity = {
        "version": "3.14.6",
        "implementation": "CPython",
        "machine": "x86_64",
        "system": "Linux",
        "soabi": "cpython-314-x86_64-linux-gnu",
        "gil_disabled": False,
    }
    RUNNER["verify_identity"](identity, "3.14.6", "linux")
    identity[key] = value
    with pytest.raises(ValueError, match="mismatch"):
        RUNNER["verify_identity"](identity, "3.14.6", "linux")


def test_documented_reproduction_uses_actual_entrypoint():
    guide = (ROOT / "config/assurance/ci.md").read_text()
    assert "scripts/ci/verify.py --host local" in guide
    assert CONTRACT["COMMAND"] in guide
    assert "--existing" in guide


def test_snapshot_covers_detached_head_dirty_bytes_modes_and_untracked(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("initial")
    git("add", "tracked.txt")
    git(
        "-c",
        "user.name=CI Test",
        "-c",
        "user.email=ci@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    git("checkout", "--detach", "-q")
    tracked.write_text("already dirty")
    before = RUNNER["snapshot"](tmp_path, dict(os.environ))
    assert before["status"]
    tracked.chmod(0o755)
    assert RUNNER["snapshot"](tmp_path, dict(os.environ)) != before
    changed = RUNNER["snapshot"](tmp_path, dict(os.environ))
    tracked.write_text("further mutation")
    assert RUNNER["snapshot"](tmp_path, dict(os.environ)) != changed
    changed = RUNNER["snapshot"](tmp_path, dict(os.environ))
    (tmp_path / "new-input.txt").write_text("new")
    assert RUNNER["snapshot"](tmp_path, dict(os.environ)) != changed


def test_missing_required_workflow_fields_do_not_fall_back(workflow, admission):
    for key in ["permissions", "on"]:
        changed = copy.deepcopy(workflow)
        del changed[key]
        reject(changed, admission)
    for key in ["runs-on", "timeout-minutes", "env"]:
        changed = copy.deepcopy(workflow)
        del changed["jobs"]["verify"][key]
        reject(changed, admission)


def test_forked_admission_source_is_rejected(admission):
    admission["actions"]["actions/checkout"]["upstream"] = (
        "https://github.com/fork/checkout"
    )
    with pytest.raises(ValueError, match="Unadmitted"):
        CONTRACT["expected_workflow"](admission)
