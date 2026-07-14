from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Email:
    """Normalized representation of one imported email."""

    index: int

    date: str
    date_short: str

    sender: str
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)

    subject: str = ""

    message_id: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)

    attachments: list[str] = field(default_factory=list)

    body_clean: str = ""
    content_type: str = ""

    source_file: str = ""
    source_folder: str = ""

    classification: str = ""
    relevance_score: float | None = None
    processing_decision: str = ""
    processing_reason: str = ""

    def to_dict(self, *, include_internal: bool = False) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        data = asdict(self)

        if not include_internal:
            data.pop("date_short", None)

        return data
