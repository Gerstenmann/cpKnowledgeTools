from cp_knowledge_tools.common.config import (
    load_classification_rules,
    load_project_config,
)
from cp_knowledge_tools.importers.mbox.classifier import (
    apply_classification,
    classify_email,
)
from cp_knowledge_tools.importers.mbox.models import Email


def get_rules():
    config = load_project_config()
    return load_classification_rules(config.rules_path)


def make_email(
    *,
    subject: str,
    body: str = "",
    sender: str = "Person <person@example.com>",
) -> Email:
    return Email(
        index=1,
        date="2026-01-01T12:00:00+01:00",
        date_short="2026-01-01",
        sender=sender,
        to=[],
        cc=[],
        bcc=[],
        subject=subject,
        body_clean=body,
    )


def test_calendar_email_is_discarded() -> None:
    email = make_email(subject="Abgelehnt: Python Coders")

    result = classify_email(email, get_rules())

    assert result.classification == "calendar"
    assert result.processing_decision == "discard"


def test_project_email_is_analyzed() -> None:
    email = make_email(
        subject="Gruppengröße und Honorar",
        body=(
            "Wir müssen die Gruppengröße und die Vergütung für den Coding Club klären."
        ),
    )

    result = classify_email(email, get_rules())

    assert result.classification == "project_communication"
    assert result.processing_decision == "analyze"


def test_automatic_sender_is_discarded() -> None:
    email = make_email(
        subject="System notification",
        sender="No Reply <no-reply@example.com>",
        body="This is an automatic system notification.",
    )

    result = classify_email(email, get_rules())

    assert result.classification == "system_notification"
    assert result.processing_decision == "discard"


def test_apply_classification_updates_email() -> None:
    email = make_email(
        subject="Vertrag JuniorCodingClub",
        body="Bitte prüfen Sie den Vertrag.",
    )

    updated_email = apply_classification(
        email,
        get_rules(),
    )

    assert updated_email.classification
    assert updated_email.relevance_score is not None
    assert updated_email.processing_decision == "analyze"
