from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from knowledge_importer.mbox.models import Email


VALID_PROCESSING_DECISIONS = {
    "analyze",
    "review",
    "archive_only",
    "discard",
}


@dataclass(slots=True)
class EmailBuckets:
    """Emails grouped by their processing decision."""

    analyze: list[Email] = field(default_factory=list)
    review: list[Email] = field(default_factory=list)
    archive_only: list[Email] = field(default_factory=list)
    discard: list[Email] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Return the total number of classified emails."""
        return (
            len(self.analyze)
            + len(self.review)
            + len(self.archive_only)
            + len(self.discard)
        )

    def knowledge_candidates(self) -> list[Email]:
        """
        Return emails that may enter the knowledge pipeline.

        This includes:
        - emails classified for analysis
        - emails requiring manual review
        """
        return [*self.analyze, *self.review]


def partition_emails(emails: Iterable[Email]) -> EmailBuckets:
    """Group emails according to their processing decision."""
    buckets = EmailBuckets()

    for email in emails:
        decision = email.processing_decision

        if decision not in VALID_PROCESSING_DECISIONS:
            raise ValueError(
                "Ungültige oder fehlende processing_decision "
                f"bei E-Mail {email.index}: {decision!r}"
            )

        if decision == "analyze":
            buckets.analyze.append(email)

        elif decision == "review":
            buckets.review.append(email)

        elif decision == "archive_only":
            buckets.archive_only.append(email)

        elif decision == "discard":
            buckets.discard.append(email)

    return buckets
