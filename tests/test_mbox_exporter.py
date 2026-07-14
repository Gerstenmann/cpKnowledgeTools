import json
from pathlib import Path

from cp_knowledge.importers.mbox.exporter import export_emails
from cp_knowledge.importers.mbox.models import Email


def test_export_emails(tmp_path: Path) -> None:
    email = Email(
        index=1,
        date="2026-03-10T10:41:57+01:00",
        date_short="2026-03-10",
        sender="Christoph <cp@codingclub.cc>",
        to=["Evgenii <evgenypermiakov@gmail.com>"],
        cc=[],
        bcc=[],
        subject="Capture the Flag Esports Map",
        message_id="<example@codingclub.cc>",
        in_reply_to="",
        references=[],
        attachments=[],
        body_clean="Hello Evgenii.",
        content_type="text/plain",
        source_file="codingclub_sent.mbox",
        source_folder="/example/input",
    )

    jsonl_path = tmp_path / "emails.jsonl"
    markdown_dir = tmp_path / "markdown"

    jsonl_count, markdown_count = export_emails(
        [email],
        jsonl_path,
        markdown_dir,
    )

    assert jsonl_count == 1
    assert markdown_count == 1
    assert jsonl_path.exists()

    json_record = json.loads(
        jsonl_path.read_text(encoding="utf-8").strip()
    )

    assert json_record["subject"] == "Capture the Flag Esports Map"
    assert json_record["to"] == [
        "Evgenii <evgenypermiakov@gmail.com>"
    ]

    markdown_files = list(markdown_dir.glob("*.md"))

    assert len(markdown_files) == 1

    markdown_text = markdown_files[0].read_text(
        encoding="utf-8"
    )

    assert "# Capture the Flag Esports Map" in markdown_text
    assert "Hello Evgenii." in markdown_text