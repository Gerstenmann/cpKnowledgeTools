from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from knowledge_importer.common.config import ClassificationRule
from knowledge_importer.mbox.models import Email


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Result of classifying one email."""

    classification: str
    relevance_score: float
    processing_decision: str
    processing_reason: str


def normalize_for_matching(value: str) -> str:
    """Normalize text for rule-based matching."""
    return re.sub(r"\s+", " ", value).strip().lower()


def matches_patterns(
    text: str,
    patterns: Iterable[str],
) -> bool:
    """Return True if one regular expression matches."""
    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


def rule_matches_email(
    email: Email,
    rule: ClassificationRule,
) -> bool:
    """Return whether one configured rule matches an email."""
    subject = normalize_for_matching(email.subject)
    body = normalize_for_matching(email.body_clean)
    sender = normalize_for_matching(email.sender)

    subject_matches = bool(rule.subject_patterns) and matches_patterns(
        subject, rule.subject_patterns
    )

    body_matches = bool(rule.body_patterns) and matches_patterns(
        body, rule.body_patterns
    )

    sender_matches = bool(rule.sender_patterns) and matches_patterns(
        sender, rule.sender_patterns
    )

    return subject_matches or body_matches or sender_matches


def body_has_substantive_content(body: str) -> bool:
    """Estimate whether the body contains meaningful content."""
    normalized = normalize_for_matching(body)

    if len(normalized) < 40:
        return False

    return len(normalized.split()) >= 8


def classify_email(
    email: Email,
    rules: Iterable[ClassificationRule],
) -> ClassificationResult:
    """Classify one email using ordered configurable rules."""
    for rule in rules:
        if rule_matches_email(email, rule):
            return ClassificationResult(
                classification=rule.name,
                relevance_score=rule.relevance_score,
                processing_decision=rule.decision,
                processing_reason=rule.reason,
            )

    if not body_has_substantive_content(email.body_clean):
        return ClassificationResult(
            classification="low_content",
            relevance_score=0.20,
            processing_decision="review",
            processing_reason=(
                "Sehr kurzer oder leerer Inhalt; automatische Einordnung ist unsicher."
            ),
        )

    return ClassificationResult(
        classification="general_communication",
        relevance_score=0.60,
        processing_decision="review",
        processing_reason=(
            "Normale Kommunikation ohne eindeutig erkannte "
            "System- oder Projektmerkmale."
        ),
    )


def apply_classification(
    email: Email,
    rules: Iterable[ClassificationRule],
) -> Email:
    """Classify an email and update its classification fields."""
    result = classify_email(email, rules)

    email.classification = result.classification
    email.relevance_score = result.relevance_score
    email.processing_decision = result.processing_decision
    email.processing_reason = result.processing_reason

    return email
