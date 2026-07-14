from __future__ import annotations

import re
from email.message import Message

from bs4 import BeautifulSoup


def decode_payload(part: Message) -> str:
    """Decode the textual payload of one MIME part."""
    payload = part.get_payload(decode=True)

    if payload is None:
        raw_payload = part.get_payload()
        return raw_payload if isinstance(raw_payload, str) else ""

    charset = part.get_content_charset() or "utf-8"

    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        # Falls die Mail einen unbekannten oder falschen Zeichensatz angibt.
        return payload.decode("utf-8", errors="replace")


def normalize_whitespace(text: str) -> str:
    """Normalize line endings, spaces and excessive blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_quoted_lines(text: str) -> str:
    """Remove conventional quoted lines beginning with >."""
    lines = [
        line.rstrip() for line in text.splitlines() if not line.lstrip().startswith(">")
    ]
    return "\n".join(lines)


def remove_quoted_message_blocks(text: str) -> str:
    """
    Remove common Outlook, Apple Mail and Gmail quoted-message sections.

    This is deliberately conservative: only the first matching separator
    and everything after it are removed.
    """
    patterns = [
        # Standard-Signaturtrenner
        r"\n--\s*\n",
        # Deutsche Outlook-Weiterleitung / Antwort
        r"\nVon:\s.*?\nGesendet:\s.*",
        r"\nVon:\s.*?\nDatum:\s.*",
        # Englische Outlook-Weiterleitung / Antwort
        r"\nFrom:\s.*?\nSent:\s.*",
        r"\nFrom:\s.*?\nDate:\s.*",
        # Apple Mail / deutsche Antworten
        r"\nAm .+? schrieb .+?:\s*$",
        # Englische Antworten
        r"\nOn .+? wrote:\s*$",
        # Weiterleitungsmarker
        r"\n-{2,}\s*Weitergeleitete Nachricht\s*-{2,}",
        r"\n-{2,}\s*Forwarded message\s*-{2,}",
        # Lange Unterstrich-Trenner
        r"\n_{10,}",
    ]

    for pattern in patterns:
        parts = re.split(
            pattern,
            text,
            maxsplit=1,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )

        if len(parts) > 1:
            return parts[0].strip()

    return text


def clean_text(text: str) -> str:
    """Clean extracted plain text without changing its substantive content."""
    if not text:
        return ""

    text = normalize_whitespace(text)
    text = remove_quoted_lines(text)
    text = remove_quoted_message_blocks(text)
    text = normalize_whitespace(text)

    return text


def html_to_text(html: str) -> str:
    """Convert HTML email content into readable plain text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(
        [
            "script",
            "style",
            "head",
            "title",
            "meta",
            "noscript",
        ]
    ):
        tag.decompose()

    # Strukturierende HTML-Elemente durch Zeilenumbrüche verständlich machen.
    for tag in soup.find_all(["br", "p", "div", "li", "tr"]):
        tag.append("\n")

    text = soup.get_text(separator="")
    return clean_text(text)


def extract_body(message: Message) -> str:
    """
    Extract and clean the message body.

    Preference:
    1. text/plain
    2. text/html converted to plain text
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []

    parts = message.walk() if message.is_multipart() else [message]

    for part in parts:
        content_type = part.get_content_type()
        disposition = str(part.get("Content-Disposition", "")).lower()

        if "attachment" in disposition:
            continue

        if content_type == "text/plain":
            content = decode_payload(part)

            if content.strip():
                plain_parts.append(content)

        elif content_type == "text/html":
            content = decode_payload(part)

            if content.strip():
                html_parts.append(content)

    if plain_parts:
        return clean_text("\n\n".join(plain_parts))

    if html_parts:
        return html_to_text("\n\n".join(html_parts))

    return ""
