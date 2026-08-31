from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version

from bs4 import BeautifulSoup, Tag

from cp_knowledge_tools.platform.hashing import (
    canonical_json_hash,
    sha256_text,
    stable_token,
)
from cp_knowledge_tools.sources.adapters.local_file import LocalFileAdapter
from cp_knowledge_tools.sources.models import (
    CapturedSource,
    Coverage,
    Diagnostic,
    EvidenceAddress,
    NormalizedRecord,
    NormalizedSourceRepresentation,
    Selector,
    SourceMapping,
    StructuredSegment,
    TransformationRun,
    fingerprint,
    normalization_fingerprint,
    representation_identity,
    source_binding_fingerprint,
    structure_fingerprint,
)

# These are technical implementation rules, not domain types or Policy grants.
EXTRACTION_RULE = "cpkt.local-html.extraction@1"
NORMALIZATION_RULE = "cpkt.text-structure.normalization@1"
EVIDENCE_RULE = "cpkt.local-html.evidence@1"
INTERNAL_MARKER = "cpkt.local-html.restriction:internal-note@1"
UNSUPPORTED = frozenset(
    {"img", "svg", "canvas", "audio", "video", "iframe", "object", "embed"}
)


@dataclass(frozen=True, slots=True)
class _Node:
    path: str
    parent_path: str | None
    order: int
    tag: str
    text_parts: tuple[str, ...]
    restricted: bool


@dataclass(frozen=True, slots=True)
class _Extraction:
    nodes: tuple[_Node, ...]
    title: str
    source_time: str | None
    creators: tuple[str, ...]
    recipients: tuple[str, ...]
    unsupported_paths: tuple[str, ...]
    excluded_paths: tuple[str, ...]
    failed: bool = False


class LocalHtmlAdapter(LocalFileAdapter):
    """Local UTF-8 HTML capture and technical normalization.

    BeautifulSoup never leaves this adapter. The optional extraction cache holds
    immutable technical values and is keyed by bytes + actual tool + rule + config.
    Evidence creation/verify are trusted source-processing APIs, not access grants.
    Consumer content access uses resolve_content and an independent PolicyDecision.
    """

    media_type = "text/html"

    def __init__(
        self,
        *,
        text_separator: str = "\n",
        excluded_tags: tuple[str, ...] = ("script", "style", "template"),
    ):
        if text_separator not in {"\n", " "}:
            raise ValueError("unsupported normalization configuration")
        if (
            type(excluded_tags) is not tuple
            or any(type(t) is not str or not t.isalpha() for t in excluded_tags)
            or not {"script", "style", "template"} <= set(excluded_tags)
        ):
            raise ValueError("unsafe extraction configuration")
        self.text_separator = text_separator
        self.excluded_tags = tuple(sorted(set(excluded_tags)))
        self.parser_tool_ref = (
            f"beautifulsoup4@{version('beautifulsoup4')}"
            f"/soupsieve@{version('soupsieve')}"
            f"/html.parser@{sys.version.split()[0]}"
        )
        self.normalizer_tool_ref = "cpkt.source-normalizer@1"
        self._cache: dict[str, _Extraction] = {}

    @staticmethod
    def _header_values(article: Tag, label: str) -> tuple[str, ...]:
        values: list[str] = []
        for term in article.find_all("dt"):
            if " ".join(term.stripped_strings).casefold() != label.casefold():
                continue
            value = term.find_next_sibling("dd")
            if isinstance(value, Tag):
                text = " ".join(value.stripped_strings)
                values.extend(part.strip() for part in text.split(";") if part.strip())
        return tuple(values)

    def _extract(
        self, captured: CapturedSource
    ) -> tuple[_Extraction, TransformationRun]:
        captured.validate()
        if captured.record.media_type != self.media_type:
            raise ValueError("unsupported media type for HTML adapter")
        config = (
            ("excluded_tags", json.dumps(self.excluded_tags)),
            ("encoding", "utf-8"),
            ("media_type", captured.record.media_type),
        )
        inputs = (captured.raw_reference.fingerprint,)
        run_ref = stable_token(
            "EXTRACT",
            self.parser_tool_ref,
            EXTRACTION_RULE,
            canonical_json_hash(config),
            canonical_json_hash([asdict(f) for f in inputs]),
        )
        extracted = self._cache.get(run_ref)
        if extracted is None:
            try:
                soup = BeautifulSoup(
                    captured.raw_content.decode("utf-8"), "html.parser"
                )
            except UnicodeDecodeError:
                extracted = _Extraction((), "", None, (), (), (), (), True)
            else:
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                root = soup.find("body") or soup
                time = root.select_one("header time[datetime]") or soup.find(
                    "meta", attrs={"name": "source-time"}
                )
                source_time = (
                    str(time.get("datetime") or time.get("content") or "")
                    if time
                    else None
                )
                creators = self._header_values(root, "From")
                recipients = (
                    *self._header_values(root, "To"),
                    *self._header_values(root, "Cc"),
                )
                unsupported: list[str] = []
                excluded: list[str] = []
                nodes: list[_Node] = []

                def walk(
                    tag: Tag,
                    path: str,
                    parent: str | None,
                    order: int,
                    restricted: bool,
                ):
                    restricted = restricted or "internal-note" in (
                        tag.get("class") or []
                    )
                    if tag.name in {*self.excluded_tags, "head"}:
                        excluded.append(path)
                        return
                    if tag.name in UNSUPPORTED:
                        unsupported.append(path)
                        return
                    # Text uses the same explicit exclusions as the structural walk.
                    parts = tuple(
                        str(s).strip()
                        for s in tag.strings
                        if str(s).strip()
                        and not any(
                            a.name in {*self.excluded_tags, "head", *UNSUPPORTED}
                            for a in s.parents
                        )
                    )
                    nodes.append(
                        _Node(
                            path,
                            parent,
                            order,
                            "document" if tag is soup else tag.name,
                            parts,
                            restricted,
                        )
                    )
                    ordinal = 0
                    for index, child in enumerate(
                        c for c in tag.children if isinstance(c, Tag)
                    ):
                        walk(
                            child,
                            f"{path.rstrip('/')}/{index}",
                            path,
                            ordinal,
                            restricted,
                        )
                        if child.name not in {
                            *self.excluded_tags,
                            "head",
                            *UNSUPPORTED,
                        }:
                            ordinal += 1

                walk(soup, "/", None, 0, False)
                extracted = _Extraction(
                    tuple(nodes),
                    title,
                    source_time,
                    creators,
                    recipients,
                    tuple(unsupported),
                    tuple(excluded),
                )
            self._cache[run_ref] = extracted
        output = fingerprint("extracted_structure", asdict(extracted))
        return extracted, TransformationRun(
            run_ref,
            "extraction",
            self.parser_tool_ref,
            EXTRACTION_RULE,
            config,
            inputs,
            output,
        )

    def normalize(self, captured: CapturedSource) -> NormalizedSourceRepresentation:
        extraction, extraction_run = self._extract(captured)
        rec, raw, snap = captured.record, captured.raw_reference, captured.snapshot
        diagnostics: list[Diagnostic] = []

        def diagnose(code: str, severity: str, message: str):
            diagnostics.append(
                Diagnostic(
                    stable_token("DIAG", snap.snapshot_ref, code),
                    code,
                    "extraction",
                    "execution" if severity == "error" else "partial_result",
                    severity,
                    message,
                    (raw.raw_content_ref,),
                )
            )

        if extraction.failed:
            diagnose("decoding_failed", "error", "Input is not valid UTF-8.")
        if extraction.unsupported_paths:
            diagnose(
                "unsupported_content",
                "warning",
                "Non-text media extraction is unsupported in this adapter.",
            )
        content = (
            self.text_separator.join(extraction.nodes[0].text_parts)
            if extraction.nodes
            else ""
        )
        if not content and not extraction.failed:
            diagnose(
                "empty_extraction",
                "warning",
                "No extractable text in the declared scope.",
            )
        metadata = {
            "title": extraction.title,
            "source_time": extraction.source_time,
            "creator_label": extraction.creators[0] if extraction.creators else None,
            "recipient_labels": extraction.recipients,
        }
        metadata.update(dict(snap.metadata))
        metadata_fp = fingerprint("metadata", [metadata])
        config = (("text_separator", self.text_separator),)
        norm_inputs = (
            extraction_run.output_fingerprint,
            metadata_fp,
            source_binding_fingerprint((rec,), (raw,), snap.capture_coverage),
        )
        run_ref = stable_token(
            "NORM",
            NORMALIZATION_RULE,
            self.normalizer_tool_ref,
            canonical_json_hash(config),
            canonical_json_hash([asdict(f) for f in norm_inputs]),
            extraction_run.run_ref,
        )
        normalized_ref = stable_token("NREC", rec.record_ref, run_ref)

        def mapping(path: str) -> SourceMapping:
            return SourceMapping(
                rec.source_key,
                rec.source_ref,
                rec.snapshot_ref,
                rec.record_ref,
                raw.raw_content_ref,
                raw.fingerprint,
                Selector("html_dom_path", "1", (path,)),
                run_ref,
            )

        def policies(restricted: bool) -> tuple[str, ...]:
            return tuple(
                sorted(
                    set(
                        (*snap.policy_refs, *((INTERNAL_MARKER,) if restricted else ()))
                    )
                )
            )

        records = (
            (
                NormalizedRecord(
                    normalized_ref,
                    content,
                    (mapping("/"),),
                    title=metadata["title"],
                    source_time=metadata["source_time"],
                    creator_label=metadata["creator_label"],
                    recipient_labels=metadata["recipient_labels"],
                    policy_refs=policies(any(n.restricted for n in extraction.nodes)),
                ),
            )
            if content
            else ()
        )
        segments = (
            tuple(
                StructuredSegment(
                    stable_token("SEG", normalized_ref, n.path),
                    normalized_ref,
                    stable_token("SEG", normalized_ref, n.parent_path)
                    if n.parent_path
                    else None,
                    n.order,
                    self._segment_type(n.tag),
                    n.tag,
                    "text/plain",
                    " ".join(n.text_parts),
                    (mapping(n.path),),
                    policies(
                        n.restricted
                        or any(
                            other.restricted
                            and (n.path == "/" or other.path.startswith(n.path + "/"))
                            for other in extraction.nodes
                        )
                    ),
                )
                for n in extraction.nodes
            )
            if content
            else ()
        )
        diagnostic_refs = tuple(d.error_id for d in diagnostics)
        extraction_status = (
            "partial_error"
            if extraction.failed
            else "partial_expected"
            if diagnostics
            else "complete"
        )
        extract_coverage = Coverage(
            "extraction",
            extraction_status,
            ("document_text_structure",),
            ("extracted_text_structure",) if content else (),
            extraction.excluded_paths,
            extraction.unsupported_paths
            or (("document",) if extraction.failed else ()),
            diagnostic_refs,
        )
        normalize_coverage = Coverage(
            "normalization",
            "complete" if content else "unknown",
            ("extracted_text_structure",),
            ("normalized_text_structure",) if content else (),
            diagnostic_refs=diagnostic_refs if not content else (),
        )
        content_fp = fingerprint("normalized_content", [r.content for r in records])
        # Structural fingerprint excludes text, transient IDs, locator and timestamps.
        structure_fp = structure_fingerprint(segments)
        output = normalization_fingerprint(records, segments)
        norm_run = TransformationRun(
            run_ref,
            "normalization",
            self.normalizer_tool_ref,
            NORMALIZATION_RULE,
            config,
            norm_inputs,
            output,
        )
        rep = NormalizedSourceRepresentation(
            "pending",
            records,
            segments,
            (raw,),
            (rec,),
            (raw.fingerprint, metadata_fp, content_fp, structure_fp),
            snap.capture_coverage,
            extract_coverage,
            normalize_coverage,
            extraction_run,
            norm_run,
            tuple(diagnostics),
        )
        rep = replace(rep, representation_ref=representation_identity(rep))
        rep.validate()
        return rep

    @staticmethod
    def _segment_type(tag: str) -> str:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return "heading"
        return {
            "p": "paragraph",
            "ul": "list",
            "ol": "list",
            "li": "list_item",
            "blockquote": "quotation",
            "document": "document",
        }.get(tag, "container")

    def rebuild(
        self, captured: CapturedSource, previous: NormalizedSourceRepresentation
    ) -> NormalizedSourceRepresentation:
        if (
            previous.extraction_run.tool_ref != self.parser_tool_ref
            or previous.extraction_run.rule_ref != EXTRACTION_RULE
            or previous.normalization_run.tool_ref != self.normalizer_tool_ref
            or previous.normalization_run.rule_ref != NORMALIZATION_RULE
        ):
            raise ValueError("unresolved rebuild dependency/provenance")
        previous.validate()
        # Fresh parse: rebuild proves dependency availability independently of cache.
        fresh = LocalHtmlAdapter(
            text_separator=self.text_separator, excluded_tags=self.excluded_tags
        ).normalize(captured)
        if fresh != previous:
            raise ValueError("rebuild dependency/configuration or content mismatch")
        return fresh

    def _evidence_nodes(self, captured: CapturedSource) -> tuple[_Node, ...]:
        # Evidence v1 always uses its declared extraction profile, independent of
        # optional normalization profiles. Never reinterpret a prior selector.
        adapter = (
            self
            if self.excluded_tags == ("script", "style", "template")
            else LocalHtmlAdapter()
        )
        extracted, _ = adapter._extract(captured)
        if extracted.failed:
            raise ValueError("source decoding failed")
        return extracted.nodes

    def _address(
        self, captured: CapturedSource, node: _Node, selector: Selector
    ) -> EvidenceAddress:
        text = " ".join(node.text_parts)
        rec, raw = captured.record, captured.raw_reference
        restricted = node.restricted or any(
            other.restricted
            and (node.path == "/" or other.path.startswith(node.path + "/"))
            for other in self._evidence_nodes(captured)
        )
        policies = tuple(
            sorted(set((*raw.policy_refs, *((INTERNAL_MARKER,) if restricted else ()))))
        )
        address = EvidenceAddress(
            "pending",
            rec.source_key,
            rec.source_ref,
            rec.snapshot_ref,
            rec.record_ref,
            selector,
            sha256_text(text),
            text,
            restricted,
            raw.raw_content_ref,
            policies,
            EVIDENCE_RULE,
            self.parser_tool_ref,
        )
        payload = asdict(address)
        payload.pop("evidence_address_ref")
        return replace(
            address,
            evidence_address_ref=stable_token("EVA", canonical_json_hash(payload)),
        )

    def evidence_address(
        self, captured: CapturedSource, required_fragments: list[str]
    ) -> EvidenceAddress:
        selector = Selector("text_fragments", "1", tuple(required_fragments))
        nodes = self._evidence_nodes(captured)
        candidates = [
            n
            for n in nodes
            if n.text_parts
            and all(f in " ".join(n.text_parts) for f in required_fragments)
        ]
        # Collapse ancestors of the same passage, never disjoint matches.
        leaves = [
            n
            for n in candidates
            if not any(
                m.path != n.path and (n.path == "/" or m.path.startswith(n.path + "/"))
                for m in candidates
            )
        ]
        if not leaves:
            raise ValueError("no reproducible source passage")
        if len(leaves) != 1:
            raise ValueError("ambiguous source selector")
        return self._address(captured, leaves[0], selector)

    def passage_evidence_addresses(
        self, captured: CapturedSource
    ) -> tuple[EvidenceAddress, ...]:
        return tuple(
            self._address(captured, node, Selector("html_dom_path", "1", (node.path,)))
            for node in self._evidence_nodes(captured)
            if node.tag in {"p", "li", "dd", "blockquote"} and node.text_parts
        )

    def evidence_address_for_segment(
        self, captured: CapturedSource, segment: StructuredSegment
    ) -> EvidenceAddress:
        """An exact single source target is required for one Evidence Address.

        Multi-input segments retain their N:M lineage. They cannot be collapsed
        into one purportedly exact Source passage through this HTML operation.
        """
        if len(segment.inputs) != 1 or segment.inputs[0].mapping_kind != "exact":
            raise ValueError("one exact source input required for a passage address")
        mapping = segment.inputs[0]
        selector = mapping.selector
        raw = captured.raw_reference
        if (
            (
                mapping.source_ref,
                mapping.snapshot_ref,
                mapping.record_ref,
                mapping.raw_content_ref,
                mapping.raw_fingerprint,
            )
            != (
                raw.source_ref,
                raw.snapshot_ref,
                raw.record_ref,
                raw.raw_content_ref,
                raw.fingerprint,
            )
            or selector is None
            or selector.selector_type != "html_dom_path"
            or selector.selector_version != "1"
            or selector.target_type != "source_passage"
            or len(selector.selector_value) != 1
        ):
            raise ValueError("segment/source integrity mismatch")
        nodes = [
            n
            for n in self._evidence_nodes(captured)
            if n.path == selector.selector_value[0]
        ]
        if len(nodes) != 1 or " ".join(nodes[0].text_parts) != segment.content:
            raise ValueError("segment/source content integrity mismatch")
        return self._address(captured, nodes[0], selector)

    def resolve(self, captured: CapturedSource, address: EvidenceAddress) -> bool:
        """Trusted integrity check only; this boolean grants no content access."""
        try:
            selector = address.selector
            if (
                selector.selector_version != "1"
                or selector.target_type != "source_passage"
                or address.resolution_rule_ref != EVIDENCE_RULE
                or address.parser_tool_ref != self.parser_tool_ref
            ):
                return False
            if selector.selector_type == "text_fragments":
                rebuilt = self.evidence_address(captured, list(selector.selector_value))
            elif (
                selector.selector_type == "html_dom_path"
                and len(selector.selector_value) == 1
            ):
                nodes = [
                    n
                    for n in self._evidence_nodes(captured)
                    if n.path == selector.selector_value[0]
                ]
                if len(nodes) != 1 or not nodes[0].text_parts:
                    return False
                rebuilt = self._address(captured, nodes[0], selector)
            else:
                return False
            return rebuilt == address
        except ValueError, TypeError, AttributeError:
            return False
