from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_key: str
    path: Path
    source_ref: str
    snapshot_ref: str
    record_ref: str
    source_time: str | None
    media_type: str
    title: str
    raw_sha256: str
    raw_html: str
    normalized_text: str
    captured_at: str


@dataclass(frozen=True, slots=True)
class EvidenceAddress:
    evidence_address_ref: str
    source_key: str
    source_ref: str
    snapshot_ref: str
    record_ref: str
    selector: dict[str, Any]
    content_hash: str
    text: str
    restricted: bool
