#!/usr/bin/env python3

import re
from email.header import decode_header, make_header

from bs4 import BeautifulSoup


def decode(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def clean_text(text):
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Outlook / Apple Mail Signaturen
    text = re.split(r"\n--\s*\n", text)[0]
    text = re.split(r"\nVon: .*Gesendet:", text)[0]
    text = re.split(r"\nFrom: .*Sent:", text)[0]
    text = re.split(r"\nAm .* schrieb .*:", text)[0]
    text = re.split(r"\nOn .* wrote:", text)[0]
    # Outlook Trenner
    text = re.split(r"_{10,}", text)[0]
    # Zitatzeilen entfernen
    lines = []
    for line in text.split("\n"):
        if line.strip().startswith(">"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_text(html):
    """Konvertiert HTML in lesbaren Text."""
    soup = BeautifulSoup(html, "html.parser")
    # Unerwünschte Elemente entfernen
    for tag in soup(["script", "style", "head", "title", "meta"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return clean_text(text)
