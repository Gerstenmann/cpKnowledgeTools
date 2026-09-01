#!/usr/bin/env python3
"""Validate the bounded Renovate repository contract without third-party code."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(".github/renovate.jsonc")
CONFIG_NAMES = {"renovate.json", "renovate.jsonc", "renovate.json5"}
IGNORED_DIRECTORIES = {".git", ".venv", "artifacts", "node_modules"}

EXPECTED_TOP_LEVEL_KEYS = {
    "$schema",
    "automerge",
    "baseBranchPatterns",
    "configMigration",
    "constraints",
    "customManagers",
    "dependencyDashboard",
    "enabledManagers",
    "lockFileMaintenance",
    "osvVulnerabilityAlerts",
    "packageRules",
    "prConcurrentLimit",
    "prCreation",
    "prHourlyLimit",
    "schedule",
    "timezone",
    "useBaseBranchConfig",
    "vulnerabilityAlerts",
}
ALLOWED_DEP_TYPES = ["project.dependencies", "project.optional-dependencies"]
EXPECTED_RULE_DESCRIPTIONS = [
    "Default-deny all PEP 621 dependency types",
    "Enable direct runtime and optional dependencies",
    "Keep Python runtime updates outside Renovate",
    "Keep build backend updates outside Renovate",
    "Require Dependency Dashboard approval for major updates",
    "Require three-day PyPI minimum release age",
    "Lock file maintenance requires approval and cannot validate release age",
    "Package replacements cannot validate release age",
    "Package pins cannot validate release age",
    "Bump, lockfile, and rollback updates cannot validate release age",
]
FORBIDDEN_KEYS = {
    "allowedCommands",
    "allowedEnv",
    "automergeSchedule",
    "automergeStrategy",
    "automergeType",
    "encrypted",
    "hostRules",
    "platformAutomerge",
    "postUpgradeTasks",
    "token",
    "username",
    "password",
}
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"/Users/", re.IGNORECASE),
    re.compile(r"cpKS-control", re.IGNORECASE),
    re.compile(r"cp-wiki", re.IGNORECASE),
    re.compile(r"cp-sources", re.IGNORECASE),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]+\b"),
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s@]+@", re.IGNORECASE),
)


def strip_jsonc_comments(text: str) -> str:
    """Remove JSONC comments while preserving quoted strings and line numbers."""
    result: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(text) and text[index : index + 2] != "*/":
                if text[index] in "\r\n":
                    result.append(text[index])
                index += 1
            if index + 1 >= len(text):
                raise ValueError("unterminated JSONC block comment")
            index += 2
            continue

        result.append(char)
        index += 1

    if in_string:
        raise ValueError("unterminated JSON string")
    return "".join(result)


def load_jsonc(path: Path) -> dict[str, Any]:
    data = json.loads(strip_jsonc_comments(path.read_text(encoding="utf-8")))
    if not isinstance(data, dict):
        raise ValueError("Renovate config root must be an object")
    return data


def _is_ignored(path: Path, root: Path) -> bool:
    return any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts)


def find_config_surfaces(root: Path) -> list[str]:
    surfaces: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or _is_ignored(path, root):
            continue
        if path.name in CONFIG_NAMES or path.name.startswith(".renovaterc"):
            surfaces.append(path.relative_to(root).as_posix())
        if path.name == "package.json":
            try:
                package_data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(package_data, dict) and "renovate" in package_data:
                surfaces.append(f"{path.relative_to(root).as_posix()}#renovate")
    return sorted(surfaces)


def _rule_by_description(config: dict[str, Any], description: str) -> dict[str, Any]:
    rules = config.get("packageRules")
    if not isinstance(rules, list):
        return {}
    matches = [
        rule
        for rule in rules
        if isinstance(rule, dict) and rule.get("description") == description
    ]
    return matches[0] if len(matches) == 1 else {}


def _walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    surfaces = find_config_surfaces(root)
    if surfaces != [CONFIG_PATH.as_posix()]:
        errors.append(
            "exactly one Renovate config is required at "
            f"{CONFIG_PATH.as_posix()}; found {surfaces}"
        )
        return errors

    config_path = root / CONFIG_PATH
    raw_text = config_path.read_text(encoding="utf-8")
    try:
        config = load_jsonc(config_path)
    except (json.JSONDecodeError, ValueError) as exc:
        return [f"invalid Renovate JSONC: {exc}"]

    actual_keys = set(config)
    if actual_keys != EXPECTED_TOP_LEVEL_KEYS:
        errors.append(
            "top-level config keys differ from the bounded contract: "
            f"missing={sorted(EXPECTED_TOP_LEVEL_KEYS - actual_keys)}, "
            f"extra={sorted(actual_keys - EXPECTED_TOP_LEVEL_KEYS)}"
        )

    expected_values = {
        "baseBranchPatterns": ["codex/source-to-knowledge-mvp"],
        "useBaseBranchConfig": "none",
        "enabledManagers": ["pep621"],
        "customManagers": [],
        "configMigration": False,
        "constraints": {"python": "3.14.6", "uv": "0.12.7"},
        "timezone": "Europe/Berlin",
        "schedule": ["after 7am and before 11am every weekday"],
        "prConcurrentLimit": 2,
        "prHourlyLimit": 1,
        "prCreation": "immediate",
        "dependencyDashboard": True,
        "automerge": False,
        "osvVulnerabilityAlerts": False,
        "vulnerabilityAlerts": {"enabled": False},
        "lockFileMaintenance": {
            "enabled": True,
            "schedule": ["after 7am and before 11am on monday"],
            "automerge": False,
        },
    }
    for key, expected in expected_values.items():
        if config.get(key) != expected:
            errors.append(f"{key} must equal {expected!r}")

    rules = config.get("packageRules")
    rule_descriptions = (
        [rule.get("description") for rule in rules if isinstance(rule, dict)]
        if isinstance(rules, list)
        else []
    )
    if rule_descriptions != EXPECTED_RULE_DESCRIPTIONS:
        errors.append(
            "packageRules must contain only the ordered bounded contract rules"
        )

    default_deny = _rule_by_description(
        config, "Default-deny all PEP 621 dependency types"
    )
    expected_default_deny = {
        "description": "Default-deny all PEP 621 dependency types",
        "matchManagers": ["pep621"],
        "enabled": False,
    }
    if default_deny != expected_default_deny:
        errors.append(
            "PEP 621 package rules must begin from a manager-wide default deny"
        )

    allowed = _rule_by_description(
        config, "Enable direct runtime and optional dependencies"
    )
    if (
        allowed.get("matchManagers") != ["pep621"]
        or allowed.get("matchDepTypes") != ALLOWED_DEP_TYPES
        or allowed.get("enabled") is not True
    ):
        errors.append(
            "only project.dependencies and project.optional-dependencies may be enabled"
        )

    excluded_rules = {
        "Keep Python runtime updates outside Renovate": ["requires-python"],
        "Keep build backend updates outside Renovate": ["build-system.requires"],
    }
    for description, dep_types in excluded_rules.items():
        rule = _rule_by_description(config, description)
        if (
            rule.get("matchManagers") != ["pep621"]
            or rule.get("matchDepTypes") != dep_types
            or rule.get("enabled") is not False
        ):
            errors.append(f"{dep_types[0]} must remain explicitly disabled")

    major = _rule_by_description(
        config, "Require Dependency Dashboard approval for major updates"
    )
    if (
        major.get("matchManagers") != ["pep621"]
        or major.get("matchDepTypes") != ALLOWED_DEP_TYPES
        or major.get("matchUpdateTypes") != ["major"]
        or major.get("dependencyDashboardApproval") is not True
        or major.get("automerge") is not False
    ):
        errors.append(
            "major updates must require Dashboard approval and forbid automerge"
        )

    release_age = _rule_by_description(
        config, "Require three-day PyPI minimum release age"
    )
    if (
        release_age.get("matchManagers") != ["pep621"]
        or release_age.get("matchDatasources") != ["pypi"]
        or release_age.get("matchDepTypes") != ALLOWED_DEP_TYPES
        or release_age.get("minimumReleaseAge") != "3 days"
        or release_age.get("internalChecksFilter") != "strict"
    ):
        errors.append(
            "direct PyPI updates must use strict three-day minimum release age"
        )

    lock_rule = _rule_by_description(
        config,
        "Lock file maintenance requires approval and cannot validate release age",
    )
    lock_notes = lock_rule.get("prBodyNotes")
    if (
        lock_rule.get("matchManagers") != ["pep621"]
        or "matchDatasources" in lock_rule
        or lock_rule.get("matchUpdateTypes") != ["lockFileMaintenance"]
        or lock_rule.get("enabled") is not True
        or lock_rule.get("dependencyDashboardApproval") is not True
        or lock_rule.get("automerge") is not False
        or lock_rule.get("minimumReleaseAge", "missing") is not None
        or not isinstance(lock_notes, list)
        or len(lock_notes) != 1
        or "does not validate Minimum Release Age" not in lock_notes[0]
    ):
        errors.append(
            "lock file maintenance must require approval and disclose the "
            "release-age limit"
        )

    unsupported_age_rules = {
        "Package replacements cannot validate release age": ["replacement"],
        "Package pins cannot validate release age": ["pin"],
        "Bump, lockfile, and rollback updates cannot validate release age": [
            "bump",
            "lockfileUpdate",
            "rollback",
        ],
    }
    for description, update_types in unsupported_age_rules.items():
        rule = _rule_by_description(config, description)
        if (
            rule.get("matchManagers") != ["pep621"]
            or rule.get("matchDatasources") != ["pypi"]
            or rule.get("matchUpdateTypes") != update_types
            or rule.get("minimumReleaseAge", "missing") is not None
        ):
            errors.append(
                f"minimum release age exception is invalid for {update_types}"
            )

    for key, value in _walk(config):
        if key in FORBIDDEN_KEYS:
            errors.append(f"forbidden Renovate key present: {key}")
        if key == "automerge" and value is not False:
            errors.append("every automerge value must be false")
        if key == "matchManagers" and value != ["pep621"]:
            errors.append(f"unexpected manager match: {value!r}")

    for pattern in FORBIDDEN_VALUE_PATTERNS:
        if pattern.search(raw_text):
            errors.append(f"forbidden path or credential pattern: {pattern.pattern}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to validate (default: current directory)",
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    errors = validate_repository(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Renovate repository contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
