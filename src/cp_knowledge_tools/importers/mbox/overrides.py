from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cp_knowledge_tools.importers.mbox.models import Email


def load_overrides(path: Path) -> dict[str, Any]:
    """Load manual classification overrides from YAML."""
    if not path.exists():
        return {
            "by_message_id": {},
            "by_subject": {},
        }

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return {
        "by_message_id": data.get("by_message_id", {}),
        "by_subject": data.get("by_subject", {}),
    }


def apply_override(
    email: Email,
    overrides: dict[str, Any],
) -> Email:
    """Apply a manual override when one is available."""
    override = None

    if email.message_id:
        override = overrides["by_message_id"].get(email.message_id)

    if override is None and email.subject:
        override = overrides["by_subject"].get(email.subject)

    if override is None:
        return email

    email.classification = override.get(
        "classification",
        email.classification,
    )
    email.relevance_score = override.get(
        "relevance_score",
        email.relevance_score,
    )
    email.processing_decision = override.get(
        "processing_decision",
        email.processing_decision,
    )
    email.processing_reason = override.get(
        "processing_reason",
        "Manuell überschrieben.",
    )

    return email
