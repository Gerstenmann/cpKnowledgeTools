from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
CHECKER_PATH = REPOSITORY_ROOT / "scripts" / "renovate" / "check_config.py"
CONFIG_PATH = REPOSITORY_ROOT / ".github" / "renovate.jsonc"

SPEC = importlib.util.spec_from_file_location("renovate_contract", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def _base_config() -> dict:
    return CHECKER.load_jsonc(CONFIG_PATH)


def _write_repository(tmp_path: Path, config: dict) -> Path:
    config_path = tmp_path / ".github" / "renovate.jsonc"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return tmp_path


def _rule(config: dict, description: str) -> dict:
    return next(
        rule
        for rule in config["packageRules"]
        if rule["description"] == description
    )


def test_repository_config_passes_first_party_contract() -> None:
    assert CHECKER.validate_repository(REPOSITORY_ROOT) == []

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(CHECKER_PATH),
            "--repository-root",
            str(REPOSITORY_ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "Renovate repository contract passed"


def test_exactly_one_repository_config_is_required(tmp_path: Path) -> None:
    repository = _write_repository(tmp_path, _base_config())
    (repository / "renovate.json").write_text("{}\n", encoding="utf-8")

    errors = CHECKER.validate_repository(repository)

    assert any("exactly one Renovate config" in error for error in errors)


@pytest.mark.parametrize(
    ("key", "unsafe_value", "expected_error"),
    [
        ("baseBranchPatterns", ["main"], "baseBranchPatterns"),
        ("enabledManagers", ["pep621", "github-actions"], "enabledManagers"),
        ("constraints", {"python": "3.14.6", "uv": "0.12.8"}, "constraints"),
        ("automerge", True, "automerge"),
        ("prConcurrentLimit", 0, "prConcurrentLimit"),
        ("prHourlyLimit", 0, "prHourlyLimit"),
        ("dependencyDashboard", False, "dependencyDashboard"),
        ("osvVulnerabilityAlerts", True, "osvVulnerabilityAlerts"),
        ("customManagers", [{"customType": "regex"}], "customManagers"),
    ],
)
def test_unsafe_top_level_changes_are_rejected(
    tmp_path: Path, key: str, unsafe_value, expected_error: str
) -> None:
    config = _base_config()
    config[key] = unsafe_value

    errors = CHECKER.validate_repository(_write_repository(tmp_path, config))

    assert any(expected_error in error for error in errors)


def test_python_build_and_allowed_dependency_boundaries_are_enforced(
    tmp_path: Path,
) -> None:
    config = _base_config()
    _rule(config, "Keep Python runtime updates outside Renovate")["enabled"] = True
    _rule(config, "Keep build backend updates outside Renovate")["enabled"] = True
    _rule(config, "Enable direct runtime and optional dependencies")[
        "matchDepTypes"
    ].append("dependency-groups")

    errors = CHECKER.validate_repository(_write_repository(tmp_path, config))

    assert any(
        "requires-python must remain explicitly disabled" in error
        for error in errors
    )
    assert any(
        "build-system.requires must remain explicitly disabled" in error
        for error in errors
    )
    assert any("only project.dependencies" in error for error in errors)


def test_additional_package_rule_cannot_expand_the_contract(tmp_path: Path) -> None:
    config = _base_config()
    config["packageRules"].append(
        {
            "description": "Enable an unreviewed dependency type",
            "matchManagers": ["pep621"],
            "matchDepTypes": ["dependency-groups"],
            "enabled": True,
        }
    )

    errors = CHECKER.validate_repository(_write_repository(tmp_path, config))

    assert any("only the ordered bounded contract rules" in error for error in errors)


def test_dashboard_approval_and_release_age_boundaries_are_enforced(
    tmp_path: Path,
) -> None:
    config = _base_config()
    _rule(config, "Require Dependency Dashboard approval for major updates")[
        "dependencyDashboardApproval"
    ] = False
    lock_rule = _rule(
        config,
        "Lock file maintenance requires approval and cannot validate release age",
    )
    lock_rule["dependencyDashboardApproval"] = False
    lock_rule["minimumReleaseAge"] = "3 days"
    _rule(config, "Require three-day PyPI minimum release age")[
        "internalChecksFilter"
    ] = "none"

    errors = CHECKER.validate_repository(_write_repository(tmp_path, config))

    assert any(
        "major updates must require Dashboard approval" in error
        for error in errors
    )
    assert any(
        "lock file maintenance must require approval" in error
        for error in errors
    )
    assert any("strict three-day minimum release age" in error for error in errors)


def test_lock_file_maintenance_rule_is_datasource_agnostic(tmp_path: Path) -> None:
    config = _base_config()
    lock_rule = _rule(
        config,
        "Lock file maintenance requires approval and cannot validate release age",
    )
    lock_rule["matchDatasources"] = ["pypi"]

    errors = CHECKER.validate_repository(_write_repository(tmp_path, config))

    assert any(
        "lock file maintenance must require approval" in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("unsafe_key", "unsafe_value"),
    [
        ("postUpgradeTasks", {"commands": ["./publish.sh"]}),
        ("allowedCommands", [".*"]),
        ("hostRules", [{"matchHost": "example.invalid", "token": "secret"}]),
        ("automergeType", "pr"),
        ("platformAutomerge", True),
    ],
)
def test_command_credential_and_merge_surfaces_are_rejected(
    tmp_path: Path, unsafe_key: str, unsafe_value
) -> None:
    config = copy.deepcopy(_base_config())
    config[unsafe_key] = unsafe_value

    errors = CHECKER.validate_repository(_write_repository(tmp_path, config))

    assert any(unsafe_key in error for error in errors)


def test_owner_root_leakage_is_rejected(tmp_path: Path) -> None:
    config = _base_config()
    config["schedule"] = ["/Users/example/private"]

    errors = CHECKER.validate_repository(_write_repository(tmp_path, config))

    assert any("forbidden path or credential pattern" in error for error in errors)


def test_embedded_uri_credentials_are_rejected(tmp_path: Path) -> None:
    config = _base_config()
    _rule(config, "Require three-day PyPI minimum release age")[
        "registryUrls"
    ] = ["https://embedded-user:embedded-pass@example.invalid/simple"]

    errors = CHECKER.validate_repository(_write_repository(tmp_path, config))

    assert any("forbidden path or credential pattern" in error for error in errors)
