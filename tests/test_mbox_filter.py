from knowledge_importer.mbox.filter import partition_emails
from knowledge_importer.mbox.models import Email


def make_email(
    index: int,
    decision: str,
) -> Email:
    return Email(
        index=index,
        date="2026-01-01T12:00:00+01:00",
        date_short="2026-01-01",
        sender="Person <person@example.com>",
        subject=f"Test {index}",
        processing_decision=decision,
    )


def test_partition_emails() -> None:
    emails = [
        make_email(1, "analyze"),
        make_email(2, "review"),
        make_email(3, "archive_only"),
        make_email(4, "discard"),
        make_email(5, "analyze"),
    ]

    buckets = partition_emails(emails)

    assert buckets.total_count == 5
    assert len(buckets.analyze) == 2
    assert len(buckets.review) == 1
    assert len(buckets.archive_only) == 1
    assert len(buckets.discard) == 1
    assert len(buckets.knowledge_candidates()) == 3