from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from cp_knowledge_tools.importers.mbox.models import Email


def _safe_text(value: str) -> str:
    """Normalize one-line text for Markdown tables."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _sample_emails(
    emails: list[Email],
    limit: int,
) -> list[Email]:
    """Return a deterministic sample from the beginning of a list."""
    return emails[:limit]


def build_summary_report(emails: Iterable[Email]) -> str:
    """Build a Markdown summary of all classifications and decisions."""
    email_list = list(emails)

    decision_counts = Counter(
        email.processing_decision or "unclassified" for email in email_list
    )

    classification_counts = Counter(
        email.classification or "unclassified" for email in email_list
    )

    lines = [
        "# Classification Summary",
        "",
        f"- Gesamtzahl E-Mails: {len(email_list)}",
        "",
        "## Verarbeitungsentscheidungen",
        "",
        "| Entscheidung | Anzahl |",
        "|---|---:|",
    ]

    for decision, count in sorted(decision_counts.items()):
        lines.append(f"| {decision} | {count} |")

    lines.extend(
        [
            "",
            "## Klassifikationen",
            "",
            "| Klassifikation | Anzahl |",
            "|---|---:|",
        ]
    )

    for classification, count in sorted(classification_counts.items()):
        lines.append(f"| {classification} | {count} |")

    lines.extend(
        [
            "",
            "## Plausibilitätsprüfung",
            "",
            "Die Klassifikation ist regelbasiert und muss vor der "
            "Wissensextraktion stichprobenartig geprüft werden.",
            "",
        ]
    )

    return "\n".join(lines)


def build_sample_report(
    title: str,
    emails: list[Email],
    limit: int = 25,
) -> str:
    """Build a Markdown sample report for one processing decision."""
    sample = _sample_emails(emails, limit)

    lines = [
        f"# {title}",
        "",
        f"- Gesamtzahl in dieser Gruppe: {len(emails)}",
        f"- Gezeigte Stichprobe: {len(sample)}",
        "",
        "| Index | Datum | Klassifikation | Relevanz | Betreff | Grund |",
        "|---:|---|---|---:|---|---|",
    ]

    for email in sample:
        score = (
            f"{email.relevance_score:.2f}" if email.relevance_score is not None else "–"
        )

        lines.append(
            "| "
            f"{email.index} | "
            f"{_safe_text(email.date_short)} | "
            f"{_safe_text(email.classification)} | "
            f"{score} | "
            f"{_safe_text(email.subject)} | "
            f"{_safe_text(email.processing_reason)} |"
        )

    lines.append("")
    return "\n".join(lines)


def write_reports(
    emails: Iterable[Email],
    reports_dir: Path,
    sample_size: int = 25,
) -> None:
    """Write classification summary and decision-specific samples."""
    email_list = list(emails)
    reports_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[Email]] = defaultdict(list)

    for email in email_list:
        decision = email.processing_decision or "unclassified"
        grouped[decision].append(email)

    summary_path = reports_dir / "classification-summary.md"
    summary_path.write_text(
        build_summary_report(email_list),
        encoding="utf-8",
    )

    report_specs = {
        "analyze": "Analyze Sample",
        "review": "Review Sample",
        "archive_only": "Archive Only Sample",
        "discard": "Discard Sample",
    }

    for decision, title in report_specs.items():
        path = reports_dir / f"{decision.replace('_', '-')}-sample.md"
        path.write_text(
            build_sample_report(
                title=title,
                emails=grouped.get(decision, []),
                limit=sample_size,
            ),
            encoding="utf-8",
        )
