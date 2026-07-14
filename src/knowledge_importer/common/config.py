from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Central application configuration."""

    project_name: str
    email_import_root: Path
    reports_dir_name: str
    markdown_dir_name: str
    sample_size: int
    preserve_all_jsonl_records: bool
    rules_path: Path
    overrides_path: Path


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    """One configurable email classification rule."""

    name: str
    decision: str
    relevance_score: float
    reason: str
    subject_patterns: tuple[str, ...]
    body_patterns: tuple[str, ...]
    sender_patterns: tuple[str, ...]


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one YAML file as a dictionary."""
    if not path.exists():
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Ungültige YAML-Struktur in: {path}")

    return data


def get_nested(
    data: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """Read a nested configuration value safely."""
    current: Any = data

    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default

        current = current[key]

    return current


def load_project_config(
    settings_path: Path | None = None,
) -> ProjectConfig:
    """Load and validate the central project configuration."""
    settings_path = settings_path or (CONFIG_DIR / "settings.yaml")
    settings = load_yaml(settings_path)

    configured_root = get_nested(
        settings,
        "paths",
        "email_import_root",
    )

    env_root = os.getenv("KNOWLEDGE_IMPORT_EMAIL_ROOT")

    if not env_root and not configured_root:
        raise ValueError(
            "Kein email_import_root in settings.yaml oder "
            "KNOWLEDGE_IMPORT_EMAIL_ROOT definiert."
        )

    email_import_root = Path(env_root or configured_root).expanduser()

    rules_file = get_nested(
        settings,
        "classification",
        "rules_file",
        default="classification_rules.yaml",
    )

    overrides_file = get_nested(
        settings,
        "classification",
        "overrides_file",
        default="classification_overrides.yaml",
    )

    return ProjectConfig(
        project_name=str(
            get_nested(
                settings,
                "project",
                "name",
                default="KnowledgeImporter",
            )
        ),
        email_import_root=email_import_root,
        reports_dir_name=str(
            get_nested(
                settings,
                "paths",
                "default_reports_dir_name",
                default="reports",
            )
        ),
        markdown_dir_name=str(
            get_nested(
                settings,
                "paths",
                "default_markdown_dir_name",
                default="markdown",
            )
        ),
        sample_size=int(
            get_nested(
                settings,
                "mbox",
                "sample_size",
                default=25,
            )
        ),
        preserve_all_jsonl_records=bool(
            get_nested(
                settings,
                "mbox",
                "preserve_all_jsonl_records",
                default=True,
            )
        ),
        rules_path=CONFIG_DIR / str(rules_file),
        overrides_path=CONFIG_DIR / str(overrides_file),
    )


def load_classification_rules(
    rules_path: Path,
) -> list[ClassificationRule]:
    """Load ordered email classification rules from YAML."""
    raw_rules = load_yaml(rules_path)
    rules: list[ClassificationRule] = []

    for rule_name, raw_rule in raw_rules.items():
        if not isinstance(raw_rule, dict):
            raise ValueError(f"Ungültige Regel {rule_name!r} in {rules_path}")

        rules.append(
            ClassificationRule(
                name=str(rule_name),
                decision=str(raw_rule.get("decision", "review")),
                relevance_score=float(raw_rule.get("relevance_score", 0.5)),
                reason=str(
                    raw_rule.get(
                        "reason",
                        "Regelbasierte Klassifikation.",
                    )
                ),
                subject_patterns=tuple(
                    str(item)
                    for item in raw_rule.get(
                        "subject_patterns",
                        [],
                    )
                ),
                body_patterns=tuple(
                    str(item)
                    for item in raw_rule.get(
                        "body_patterns",
                        [],
                    )
                ),
                sender_patterns=tuple(
                    str(item)
                    for item in raw_rule.get(
                        "sender_patterns",
                        [],
                    )
                ),
            )
        )

    return rules
