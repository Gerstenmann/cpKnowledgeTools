"""Validate the deliberately closed repository CI shape, not arbitrary Actions."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from cp_knowledge_tools.template_generator.yaml_io import UniqueKeyLoader

ACTION_IDS = {"actions/checkout", "actions/setup-python", "astral-sh/setup-uv"}
BRANCH = "codex/source-to-knowledge-mvp"
COMMAND = "python -I -B scripts/ci/verify.py --host linux"


def expected_workflow(admission: dict) -> dict:
    """Only reviewed action identities can contribute immutable pins."""
    if (
        admission.get("schema_version") != 1
        or admission.get("role") != "repository_ci_action_admission"
        or admission.get("disposition") != "accepted_with_conditions"
        or set(admission.get("actions", {})) != ACTION_IDS
    ):
        raise ValueError("CI action admission is missing or unsupported")
    actions = admission["actions"]
    for identity, item in actions.items():
        if (
            item.get("upstream") != f"https://github.com/{identity}"
            or not re.fullmatch(r"[0-9a-f]{40}", item.get("commit", ""))
            or not re.fullmatch(r"v\d+\.\d+\.\d+", item.get("release", ""))
            or item.get("license_expression") != "MIT"
            or item.get("runtime") != "node24"
            or item.get("disposition") != "accepted_with_conditions"
        ):
            raise ValueError(f"Unadmitted action: {identity}")
    uv = admission["uv"]
    if (
        uv.get("version") != "0.12.7"
        or uv.get("platform") != "x86_64-unknown-linux-gnu"
        or not re.fullmatch(r"[0-9a-f]{64}", uv.get("archive_sha256", ""))
    ):
        raise ValueError("Unadmitted uv identity")

    def action(name: str, identity: str, inputs: dict) -> dict:
        return {
            "name": name,
            "uses": f"{identity}@{actions[identity]['commit']}",
            "with": inputs,
        }

    return {
        "name": "Repository CI",
        "on": {
            "push": {"branches": [BRANCH]},
            "pull_request": {"branches": [BRANCH]},
            "workflow_dispatch": None,
        },
        "permissions": {"contents": "read"},
        "jobs": {
            "verify": {
                "runs-on": "ubuntu-24.04",
                "timeout-minutes": 30,
                "env": {
                    "UV_PYTHON_DOWNLOADS": "never",
                    "UV_NO_MANAGED_PYTHON": "true",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                "defaults": {"run": {"shell": "bash"}},
                "steps": [
                    action(
                        "Checkout",
                        "actions/checkout",
                        {
                            "persist-credentials": False,
                            "fetch-depth": 1,
                            "submodules": False,
                            "lfs": False,
                        },
                    ),
                    action(
                        "Set up Python",
                        "actions/setup-python",
                        {
                            "python-version-file": ".python-version",
                            "architecture": "x64",
                            "check-latest": False,
                        },
                    ),
                    action(
                        "Set up uv",
                        "astral-sh/setup-uv",
                        {
                            "version": uv["version"],
                            "checksum": uv["archive_sha256"],
                            "enable-cache": False,
                            "cache-python": False,
                            "restore-cache": False,
                            "save-cache": False,
                            "activate-environment": False,
                            "download-from-astral-mirror": False,
                        },
                    ),
                    {"name": "Verify repository", "run": COMMAND},
                ],
            },
        },
    }


def validate(raw: str, admission: dict, python_pin: str) -> None:
    if not re.fullmatch(r"3\.14\.\d+\n?", python_pin):
        raise ValueError("An exact ordinary CPython 3.14 patch is required")
    workflow = yaml.load(raw, Loader=UniqueKeyLoader)
    # JSON comparison preserves scalar types (False must not equal integer 0).
    # Closed shape rejects extra jobs/steps/env/expressions and arbitrary shell;
    # no incomplete denylist or pretend shell interpreter is involved.
    if json.dumps(workflow, sort_keys=True) != json.dumps(
        expected_workflow(admission), sort_keys=True
    ):
        raise ValueError("Workflow differs from the reviewed closed CI contract")


def check(root: Path) -> None:
    directory = root / ".github/workflows"
    workflows = sorted(p.name for p in directory.iterdir())
    if workflows != ["ci.yml"]:
        raise ValueError("Exactly one canonical workflow, ci.yml, is permitted")
    paths = [directory / "ci.yml", root / "config/assurance/ci-actions.json"]
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Expected a regular CI contract file: {path.name}")
        if "/Users/" in path.read_text():
            raise ValueError("CI contract contains an Owner-local path")
    admission = json.loads(paths[1].read_text())
    local = json.loads((root / "config/assurance/development-tools.json").read_text())
    if admission["uv"]["version"] != local["tool"]["version"]:
        raise ValueError("CI and local uv version require a reviewed delta")
    validate(paths[0].read_text(), admission, (root / ".python-version").read_text())


if __name__ == "__main__":
    check(Path(__file__).resolve().parents[2])
    print("CI workflow contract passed")
