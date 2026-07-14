from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from knowledge_importer.mbox.models import Email


def safe_filename(text: str, max_length: int = 80) -> str:
    """Convert text into a filesystem-safe filename fragment."""
    cleaned = re.sub(r"[^\w\s.-]", "", text, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "-", cleaned.strip())
    return cleaned[:max_length] or "email"


def yaml_string(value: str) -> str:
    """Return a safely quoted YAML string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def format_list(values: list[str]) -> str:
    """Return a readable comma-separated list."""
    return ", ".join(values) if values else "–"


def build_markdown(email: Email) -> str:
    """Build one Markdown document from one Email object."""
    subject = email.subject or "(Ohne Betreff)"

    return f"""---
type: email
source: mbox
index: {email.index}
date: {yaml_string(email.date)}
from: {yaml_string(email.sender)}
to: {json.dumps(email.to, ensure_ascii=False)}
cc: {json.dumps(email.cc, ensure_ascii=False)}
bcc: {json.dumps(email.bcc, ensure_ascii=False)}
subject: {yaml_string(email.subject)}
message_id: {yaml_string(email.message_id)}
in_reply_to: {yaml_string(email.in_reply_to)}
references: {json.dumps(email.references, ensure_ascii=False)}
attachments: {json.dumps(email.attachments, ensure_ascii=False)}
content_type: {yaml_string(email.content_type)}
source_file: {yaml_string(email.source_file)}
source_folder: {yaml_string(email.source_folder)}
classification: {yaml_string(email.classification)}
relevance_score: {email.relevance_score if email.relevance_score is not None else "null"}
processing_decision: {yaml_string(email.processing_decision)}
processing_reason: {yaml_string(email.processing_reason)}
---

# {subject}

## Metadaten

- Datum: {email.date or "–"}
- Von: {email.sender or "–"}
- An: {format_list(email.to)}
- CC: {format_list(email.cc)}
- BCC: {format_list(email.bcc)}
- Anhänge: {format_list(email.attachments)}
- Inhaltstyp: {email.content_type or "–"}
- Quelldatei: {email.source_file or "–"}

## Bereinigter Inhalt

{email.body_clean}
"""


def markdown_filename(email: Email) -> str:
    """Return the filename for one email Markdown document."""
    subject = safe_filename(email.subject)
    return f"{email.date_short}_{subject}_{email.index:04d}.md"


def write_jsonl(
    emails: Iterable[Email],
    output_path: Path,
) -> int:
    """Write all emails to one JSONL file and return the count."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0

    with output_path.open("w", encoding="utf-8") as jsonl_file:
        for email in emails:
            jsonl_file.write(
                json.dumps(
                    email.to_dict(),
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1

    return count


def write_markdown_files(
    emails: Iterable[Email],
    output_dir: Path,
) -> int:
    """Write one Markdown file per email and return the count."""
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0

    for email in emails:
        output_path = output_dir / markdown_filename(email)
        output_path.write_text(
            build_markdown(email),
            encoding="utf-8",
        )
        count += 1

    return count


def export_emails(
    emails: Iterable[Email],
    jsonl_path: Path,
    markdown_dir: Path,
) -> tuple[int, int]:
    """
    Export emails to JSONL and Markdown.

    The iterable is materialized once because it must be processed twice.
    """
    email_list = list(emails)

    jsonl_count = write_jsonl(
        email_list,
        jsonl_path,
    )

    markdown_count = write_markdown_files(
        email_list,
        markdown_dir,
    )

    return jsonl_count, markdown_count
