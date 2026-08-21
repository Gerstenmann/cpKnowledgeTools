from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from cp_knowledge_tools.platform.hashing import sha256_bytes, sha256_text, stable_token
from cp_knowledge_tools.sources.models import EvidenceAddress, SourceRecord


class LocalHtmlAdapter:
    """Deterministic local UTF-8 HTML reference adapter.

    The adapter owns HTML parsing only. It does not assign Evidence roles,
    Claims, Events, epistemic status, or Publication state.
    """

    media_type = "text/html"

    def capture(self, source_key: str, path: Path) -> SourceRecord:
        raw_bytes = path.read_bytes()
        raw_html = raw_bytes.decode("utf-8")
        soup = BeautifulSoup(raw_html, "html.parser")
        article = soup.find("article") or soup.find("body") or soup

        title_node = soup.find("title")
        title = title_node.get_text(" ", strip=True) if title_node else path.name
        time_node = (
            article.select_one("header time[datetime]")
            if isinstance(article, Tag)
            else None
        )
        source_time = time_node.get("datetime") if time_node else None
        if source_time is None:
            source_time_node = soup.find("meta", attrs={"name": "source-time"})
            if isinstance(source_time_node, Tag):
                source_time = source_time_node.get("content")
        normalized_text = "\n".join(article.stripped_strings)

        raw_hash = sha256_bytes(raw_bytes)
        source_ref = stable_token("SRC", source_key)
        snapshot_ref = stable_token("SNAP", source_ref, raw_hash)
        record_ref = stable_token("REC", snapshot_ref, "document")

        return SourceRecord(
            source_key=source_key,
            path=path,
            source_ref=source_ref,
            snapshot_ref=snapshot_ref,
            record_ref=record_ref,
            source_time=source_time,
            media_type=self.media_type,
            title=title,
            raw_sha256=raw_hash,
            raw_html=raw_html,
            normalized_text=normalized_text,
            captured_at=datetime.now().astimezone().isoformat(),
        )

    def capture_many(self, bindings: Iterable[tuple[str, Path]]) -> list[SourceRecord]:
        return [self.capture(source_key, path) for source_key, path in bindings]

    def passage_evidence_addresses(
        self,
        record: SourceRecord,
    ) -> tuple[EvidenceAddress, ...]:
        """Address natural block passages without scenario semantic annotations."""

        soup = BeautifulSoup(record.raw_html, "html.parser")
        article = soup.find("article") or soup.find("main") or soup.find("body") or soup
        seen: set[str] = set()
        addresses: list[EvidenceAddress] = []
        for tag in article.find_all(("p", "li", "dd", "blockquote")):
            text = " ".join(tag.stripped_strings)
            if not text or text in seen:
                continue
            seen.add(text)
            addresses.append(self.evidence_address(record, [text]))
        return tuple(addresses)

    def evidence_address(
        self,
        record: SourceRecord,
        required_fragments: list[str],
    ) -> EvidenceAddress:
        soup = BeautifulSoup(record.raw_html, "html.parser")
        article = soup.find("article") or soup.find("body") or soup

        candidates: list[tuple[int, Tag, str]] = []
        for tag in article.find_all(True):
            text = " ".join(tag.stripped_strings)
            if text and all(fragment in text for fragment in required_fragments):
                candidates.append((len(text), tag, text))

        if not candidates:
            raise ValueError(
                f"No reproducible passage in {record.source_key} contains all "
                f"fragments: {required_fragments!r}"
            )

        _, tag, text = min(candidates, key=lambda item: item[0])
        restricted = any(
            "internal-note" in (ancestor.get("class") or [])
            for ancestor in [tag, *tag.parents]
            if isinstance(ancestor, Tag)
        )
        content_hash = sha256_text(text)
        selector = {
            "selector_type": "text_fragments",
            "selector_version": "0.1",
            "selector_value": list(required_fragments),
            "target_type": "source_passage",
        }
        evidence_ref = stable_token(
            "EVA",
            record.snapshot_ref,
            record.record_ref,
            "|".join(required_fragments),
            content_hash,
        )
        return EvidenceAddress(
            evidence_address_ref=evidence_ref,
            source_key=record.source_key,
            source_ref=record.source_ref,
            snapshot_ref=record.snapshot_ref,
            record_ref=record.record_ref,
            selector=selector,
            content_hash=content_hash,
            text=text,
            restricted=restricted,
        )

    def resolve(self, record: SourceRecord, address: EvidenceAddress) -> bool:
        if (
            record.snapshot_ref != address.snapshot_ref
            or record.record_ref != address.record_ref
        ):
            return False
        try:
            rebuilt = self.evidence_address(
                record,
                list(address.selector["selector_value"]),
            )
        except ValueError:
            return False
        return (
            rebuilt.content_hash == address.content_hash
            and rebuilt.evidence_address_ref == address.evidence_address_ref
        )
