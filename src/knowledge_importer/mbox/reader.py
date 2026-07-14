from __future__ import annotations

import mailbox
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Iterator

from knowledge_importer.common.utils import decode
from knowledge_importer.mbox.cleaner import extract_body
from knowledge_importer.mbox.models import Email


def parse_date(raw_date: str | None) -> tuple[str, str]:
    """
    Convert an email date header into:

    1. ISO datetime
    2. YYYY-MM-DD for filenames
    """
    if not raw_date:
        return "", "undated"

    try:
        parsed_date = parsedate_to_datetime(raw_date)
        return parsed_date.isoformat(), parsed_date.date().isoformat()
    except TypeError, ValueError, OverflowError:
        return raw_date, "undated"


def format_address(name: str, address: str) -> str:
    """Return a normalized display form for one email address."""
    name = decode(name).strip()
    address = address.strip()

    if name and address:
        return f"{name} <{address}>"

    return address or name


def parse_address_list(raw_value: str | None) -> list[str]:
    """
    Convert an email address header into a list.

    Example:
    'Alice <a@example.com>, Bob <b@example.com>'

    becomes:
    [
        'Alice <a@example.com>',
        'Bob <b@example.com>',
    ]
    """
    if not raw_value:
        return []

    decoded_value = decode(raw_value)

    return [
        format_address(name, address)
        for name, address in getaddresses([decoded_value])
        if name or address
    ]


def parse_references(raw_value: str | None) -> list[str]:
    """Convert the References header into individual message IDs."""
    if not raw_value:
        return []

    decoded_value = decode(raw_value)

    return [
        item.strip()
        for item in decoded_value.replace("\n", " ").split()
        if item.strip()
    ]


def get_attachments(message: Message) -> list[str]:
    """Return decoded attachment filenames."""
    attachments: list[str] = []

    for part in message.walk():
        filename = part.get_filename()

        if filename:
            attachments.append(decode(filename))

    return attachments


def read_mbox(input_path: Path) -> Iterator[Email]:
    """
    Read an MBOX file and yield one normalized Email object at a time.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"MBOX-Datei nicht gefunden: {input_path}")

    if not input_path.is_file():
        raise ValueError(f"Pfad ist keine Datei: {input_path}")

    mbox = mailbox.mbox(input_path, create=False)

    try:
        for index, message in enumerate(mbox, start=1):
            date, date_short = parse_date(message.get("date"))

            yield Email(
                index=index,
                date=date,
                date_short=date_short,
                sender=decode(message.get("from")),
                to=parse_address_list(message.get("to")),
                cc=parse_address_list(message.get("cc")),
                bcc=parse_address_list(message.get("bcc")),
                subject=decode(message.get("subject")),
                message_id=decode(message.get("message-id")),
                in_reply_to=decode(message.get("in-reply-to")),
                references=parse_references(message.get("references")),
                attachments=get_attachments(message),
                body_clean=extract_body(message),
                content_type=message.get_content_type(),
                source_file=input_path.name,
                source_folder=str(input_path.parent),
            )
    finally:
        mbox.close()
