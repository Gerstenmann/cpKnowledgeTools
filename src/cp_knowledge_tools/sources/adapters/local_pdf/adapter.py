"""Digital PDF reference adapter. No OCR, repair, rendering or remote I/O.

Native parser values live only inside _parse. Frozen technical nodes are the
private extraction cache; the public boundary is the existing Source contract.
"""

from __future__ import annotations

import math
import sys
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from io import BytesIO

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

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

EXTRACTION_RULE = "cpkt.local-pdf.extraction@1"
NORMALIZATION_RULE = "cpkt.local-pdf.normalization@1"
EVIDENCE_RULE = "cpkt.local-pdf.evidence@1"
DEFAULT_LIMITS = (20_000_000, 200, 500_000)


@dataclass(frozen=True, slots=True)
class _Node:
    path: str
    parent: str | None
    order: int
    kind: str
    text: str
    selector: Selector | None


@dataclass(frozen=True, slots=True)
class _Extraction:
    nodes: tuple[_Node, ...] = ()
    title: str = ""
    author: str | None = None
    source_time: str | None = None
    # (code, technical scope, severity); never parser exception text/source data.
    issues: tuple[tuple[str, str, str], ...] = ()


def _region(page: int, box, kind: str, ordinal: str) -> Selector:
    # Canonical PDF points, top-left origin, three decimal places. Never select
    # arbitrary approximate boxes: resolution matches an extracted region exactly.
    coords = tuple(float(v) for v in box)
    if (
        len(coords) != 4
        or not all(math.isfinite(v) for v in coords)
        or coords[0] >= coords[2]
        or coords[1] >= coords[3]
    ):
        raise ValueError("invalid PDF geometry")
    return Selector(
        "pdf_region", "1", (str(page), *(f"{v:.3f}" for v in coords), kind, ordinal)
    )


class LocalPdfAdapter(LocalFileAdapter):
    """Bounded local reference use; limits are cooperative, not a hostile-PDF sandbox.

    Evidence @1 has a fixed extraction profile independent of optional normalize
    settings. Policy decisions come from the trusted host through resolve_content.
    """

    media_type = "application/pdf"

    def __init__(
        self,
        *,
        text_separator: str = "\n",
        max_bytes: int = DEFAULT_LIMITS[0],
        max_pages: int = DEFAULT_LIMITS[1],
        max_chars: int = DEFAULT_LIMITS[2],
    ):
        if text_separator not in {"\n", " "}:
            raise ValueError("unsupported normalization configuration")
        if any(
            type(n) is not int or not 0 < n <= maximum
            for n, maximum in zip(
                (max_bytes, max_pages, max_chars), DEFAULT_LIMITS, strict=True
            )
        ):
            raise ValueError("invalid PDF processing limits")
        self.text_separator = text_separator
        self.limits = (max_bytes, max_pages, max_chars)
        self.parser_tool_ref = (
            f"pdfplumber@{version('pdfplumber')}/pdfminer.six@{version('pdfminer.six')}"
            f"/charset-normalizer@{version('charset-normalizer')}"
            f"/python@{sys.version.split()[0]}"
        )
        self.normalizer_tool_ref = "cpkt.source-normalizer@1"
        self._cache: dict[str, _Extraction] = {}

    def _parse(self, raw: bytes) -> _Extraction:
        def failure(code):
            return _Extraction(issues=((code, "document", "error"),))

        if len(raw) > self.limits[0]:
            return failure("pdf_limit_exceeded")
        if not raw.startswith(b"%PDF-"):
            return failure("invalid_pdf")
        nodes: list[_Node] = []
        issues: list[tuple[str, str, str]] = []
        page_texts = []
        try:
            with pdfplumber.open(BytesIO(raw), strict_metadata=True) as pdf:
                # Even empty-user-password encryption is out of scope. No attempt
                # to bypass permissions or accept a decrypted native document.
                if pdf.doc.encryption:
                    return failure("encrypted_pdf")
                if len(pdf.pages) > self.limits[1]:
                    return failure("pdf_limit_exceeded")
                if not pdf.pages:
                    return failure("pdf_no_pages")
                count = 0
                for page in pdf.pages:
                    number = page.page_number
                    path = f"/page/{number}"
                    count += len(page.chars)
                    if count > self.limits[2]:
                        return failure("pdf_limit_exceeded")
                    lines = page.extract_text_lines(layout=False, return_chars=False)
                    text = "\n".join(
                        line["text"] for line in lines if line["text"].strip()
                    )
                    page_texts.append(text)
                    nodes.append(
                        _Node(
                            path,
                            "/",
                            number - 1,
                            "page",
                            text,
                            Selector("pdf_page", "1", (str(number),)),
                        )
                    )
                    if not text:
                        issues.append(("no_digital_text", path, "warning"))
                    if page.images or page.curves:
                        issues.append(("non_text_content", path, "warning"))
                    if page.annots:
                        issues.append(("annotations_excluded", path, "warning"))
                    if page.rotation or any(
                        not c.get("upright", True) for c in page.chars
                    ):
                        issues.append(("complex_text_layout", path, "warning"))
                    order = 0
                    for line in lines:
                        if not line["text"].strip():
                            continue
                        box = tuple(line[k] for k in ("x0", "top", "x1", "bottom"))
                        nodes.append(
                            _Node(
                                f"{path}/line/{order}",
                                path,
                                order,
                                "text_line",
                                line["text"],
                                _region(number, box, "text_line", str(order)),
                            )
                        )
                        order += 1
                    # Only explicit ruled rectangular grids are projected. Merged,
                    # incomplete matrices remain diagnostic, not exact. Geometric
                    # gap repair is disabled; this is not general layout validation.
                    tables = page.find_tables(
                        {
                            "vertical_strategy": "lines_strict",
                            "horizontal_strategy": "lines_strict",
                            "snap_tolerance": 0,
                            "join_tolerance": 0,
                            "intersection_tolerance": 0,
                        }
                    )
                    for ti, table in enumerate(tables):
                        rows = table.rows
                        matrix = table.extract()
                        if (
                            len(rows) < 2
                            or len(rows[0].cells) < 2
                            or any(
                                len(r.cells) != len(rows[0].cells)
                                or any(c is None for c in r.cells)
                                for r in rows
                            )
                        ):
                            issues.append(
                                ("table_structure_unresolved", path, "warning")
                            )
                            continue
                        tpath = f"{path}/table/{ti}"
                        table_nodes = []
                        for ri, row in enumerate(rows):
                            rpath = f"{tpath}/row/{ri}"
                            row_text = " | ".join(v or "" for v in matrix[ri])
                            table_nodes.append(
                                _Node(
                                    rpath,
                                    tpath,
                                    ri,
                                    "table_row",
                                    row_text,
                                    _region(
                                        number, row.bbox, "table_row", f"{ti}/{ri}"
                                    ),
                                )
                            )
                            for ci, box in enumerate(row.cells):
                                table_nodes.append(
                                    _Node(
                                        f"{rpath}/cell/{ci}",
                                        rpath,
                                        ci,
                                        "table_cell",
                                        matrix[ri][ci] or "",
                                        _region(
                                            number, box, "table_cell", f"{ti}/{ri}/{ci}"
                                        ),
                                    )
                                )
                        table_text = "\n".join(
                            n.text for n in table_nodes if n.kind == "table_row"
                        )
                        nodes.append(
                            _Node(
                                tpath,
                                path,
                                order,
                                "table",
                                table_text,
                                _region(number, table.bbox, "table", str(ti)),
                            )
                        )
                        nodes.extend(table_nodes)
                        order += 1
                    if (page.lines or page.rects) and not tables:
                        issues.append(("vector_structure_unresolved", path, "warning"))
                    page.close()
                metadata = pdf.metadata
                title = metadata.get("Title", "")
                author = metadata.get("Author")
                source_time = metadata.get("CreationDate")
                if not all(
                    v is None or isinstance(v, str)
                    for v in (title, author, source_time)
                ):
                    issues.append(("metadata_unresolved", "document", "warning"))
                # Raw PDF dates remain explicit source strings, never inferred
                # event times or currentness. Arbitrary native metadata is omitted.
                return _Extraction(
                    (
                        _Node(
                            "/",
                            None,
                            0,
                            "document",
                            "\n".join(t for t in page_texts if t),
                            None,
                        ),
                        *nodes,
                    ),
                    title if isinstance(title, str) else "",
                    author if isinstance(author, str) else None,
                    source_time if isinstance(source_time, str) else None,
                    tuple(issues),
                )
        except PDFPasswordIncorrect, PDFEncryptionError:
            return failure("encrypted_pdf")
        except PdfminerException as exc:
            if exc.args and isinstance(
                exc.args[0], (PDFPasswordIncorrect, PDFEncryptionError)
            ):
                return failure("encrypted_pdf")
            return failure("pdf_parse_failed")
        except Exception:
            # Parser/library failures may embed source bytes or arbitrary metadata.
            # Preserve a typed failure, never a repaired/empty successful document.
            return failure("pdf_parse_failed")

    def _extract(
        self, captured: CapturedSource
    ) -> tuple[_Extraction, TransformationRun]:
        captured.validate()
        if captured.record.media_type != self.media_type:
            raise ValueError("unsupported media type for PDF adapter")
        config = (
            ("max_bytes", str(self.limits[0])),
            ("max_pages", str(self.limits[1])),
            ("max_chars", str(self.limits[2])),
            ("layout", "positioned_lines"),
            ("tables", "ruled_rectangular_zero_tolerance"),
            ("ocr", "disabled"),
        )
        inputs = (captured.raw_reference.fingerprint,)
        ref = stable_token(
            "EXTRACT",
            self.parser_tool_ref,
            EXTRACTION_RULE,
            canonical_json_hash(config),
            canonical_json_hash([asdict(f) for f in inputs]),
        )
        extraction = self._cache.get(ref)
        if extraction is None:
            extraction = self._parse(captured.raw_content)
            # A small bounded cache; it contains technical values, never native pages.
            if len(self._cache) >= 8:
                self._cache.pop(next(iter(self._cache)))
            self._cache[ref] = extraction
        return extraction, TransformationRun(
            ref,
            "extraction",
            self.parser_tool_ref,
            EXTRACTION_RULE,
            config,
            inputs,
            fingerprint("extracted_structure", asdict(extraction)),
        )

    def normalize(self, captured: CapturedSource) -> NormalizedSourceRepresentation:
        extracted, extraction_run = self._extract(captured)
        rec, raw, snap = captured.record, captured.raw_reference, captured.snapshot
        diagnostics = tuple(
            Diagnostic(
                stable_token("DIAG", snap.snapshot_ref, code, scope),
                code,
                "extraction",
                "execution" if severity == "error" else "partial_result",
                severity,
                f"PDF extraction: {code} ({scope}).",
                (raw.raw_content_ref,),
                source_context="local_pdf",
            )
            for code, scope, severity in extracted.issues
        )
        content = self.text_separator.join(
            n.text.replace("\n", self.text_separator)
            for n in extracted.nodes
            if n.kind == "page" and n.text
        )
        metadata = {
            "title": extracted.title,
            "source_time": extracted.source_time,
            "creator_label": extracted.author,
            "recipient_labels": (),
        }
        metadata.update(dict(snap.metadata))
        metadata_fp = fingerprint("metadata", [metadata])
        config = (("text_separator", self.text_separator),)
        inputs = (
            extraction_run.output_fingerprint,
            metadata_fp,
            source_binding_fingerprint((rec,), (raw,), snap.capture_coverage),
        )
        run_ref = stable_token(
            "NORM",
            NORMALIZATION_RULE,
            self.normalizer_tool_ref,
            canonical_json_hash(config),
            canonical_json_hash([asdict(f) for f in inputs]),
            extraction_run.run_ref,
        )
        record_ref = stable_token("NREC", rec.record_ref, run_ref)

        def mapping(selector):
            return SourceMapping(
                rec.source_key,
                rec.source_ref,
                rec.snapshot_ref,
                rec.record_ref,
                raw.raw_content_ref,
                raw.fingerprint,
                selector,
                run_ref,
            )

        page_inputs = tuple(
            mapping(n.selector) for n in extracted.nodes if n.kind == "page"
        )
        records = (
            (
                NormalizedRecord(
                    record_ref,
                    content,
                    page_inputs,
                    title=metadata["title"],
                    source_time=metadata["source_time"],
                    creator_label=metadata["creator_label"],
                    policy_refs=snap.policy_refs,
                ),
            )
            if content
            else ()
        )
        segments = (
            tuple(
                StructuredSegment(
                    stable_token("SEG", record_ref, n.path),
                    record_ref,
                    stable_token("SEG", record_ref, n.parent) if n.parent else None,
                    n.order,
                    "paragraph" if n.kind == "text_line" else n.kind,
                    n.kind,
                    "text/plain",
                    n.text,
                    (mapping(n.selector),) if n.selector else page_inputs,
                    snap.policy_refs,
                )
                for n in extracted.nodes
            )
            if content
            else ()
        )
        diag_refs = tuple(d.error_id for d in diagnostics)
        failed = tuple(
            scope for _, scope, severity in extracted.issues if severity == "error"
        )
        excluded = tuple(
            scope + ":" + code
            for code, scope, severity in extracted.issues
            if severity != "error"
        )
        extraction_coverage = Coverage(
            "extraction",
            "partial_error"
            if failed
            else "partial_expected"
            if diagnostics
            else "complete",
            ("digital_text_pages_regions", "ruled_rectangular_tables"),
            tuple(n.path for n in extracted.nodes if n.kind == "page" and n.text),
            ("ocr", "logical_reading_order", "embedded_files", *excluded),
            failed,
            diag_refs,
        )
        normalization_coverage = Coverage(
            "normalization",
            "complete" if content else "unknown",
            ("extracted_technical_structure",),
            ("neutral_records_segments",) if content else (),
            diagnostic_refs=diag_refs if not content else (),
        )
        run = TransformationRun(
            run_ref,
            "normalization",
            self.normalizer_tool_ref,
            NORMALIZATION_RULE,
            config,
            inputs,
            normalization_fingerprint(records, segments),
        )
        rep = NormalizedSourceRepresentation(
            "pending",
            records,
            segments,
            (raw,),
            (rec,),
            (
                raw.fingerprint,
                metadata_fp,
                fingerprint("normalized_content", [r.content for r in records]),
                structure_fingerprint(segments),
            ),
            snap.capture_coverage,
            extraction_coverage,
            normalization_coverage,
            extraction_run,
            run,
            diagnostics,
        )
        rep = replace(rep, representation_ref=representation_identity(rep))
        rep.validate()
        return rep

    def rebuild(
        self, captured: CapturedSource, previous: NormalizedSourceRepresentation
    ) -> NormalizedSourceRepresentation:
        previous.validate()
        fresh = LocalPdfAdapter(
            text_separator=self.text_separator,
            max_bytes=self.limits[0],
            max_pages=self.limits[1],
            max_chars=self.limits[2],
        ).normalize(captured)
        if fresh != previous:
            raise ValueError("rebuild dependency/configuration or content mismatch")
        return fresh

    def _evidence_nodes(self, captured: CapturedSource) -> tuple[_Node, ...]:
        # Fixed extraction semantics do not override the caller's resource budget.
        # Budgets change availability, never the meaning of an allowed selector.
        extraction, _ = self._extract(captured)
        if any(severity == "error" for _, _, severity in extraction.issues):
            raise ValueError("PDF extraction unavailable")
        return extraction.nodes

    def _address(
        self, captured: CapturedSource, node: _Node, selector: Selector
    ) -> EvidenceAddress:
        rec, raw = captured.record, captured.raw_reference
        address = EvidenceAddress(
            "pending",
            rec.source_key,
            rec.source_ref,
            rec.snapshot_ref,
            rec.record_ref,
            selector,
            sha256_text(node.text),
            node.text,
            False,
            raw.raw_content_ref,
            raw.policy_refs,
            EVIDENCE_RULE,
            self.parser_tool_ref,
        )
        payload = asdict(address)
        payload.pop("evidence_address_ref")
        return replace(
            address,
            evidence_address_ref=stable_token("EVA", canonical_json_hash(payload)),
        )

    def _selected_node(self, captured: CapturedSource, selector: Selector) -> _Node:
        if selector.selector_version != "1" or selector.target_type != "source_passage":
            raise ValueError("unsupported PDF selector")
        nodes = self._evidence_nodes(captured)
        if selector.selector_type == "pdf_text":
            # Text selectors refer to one positioned line, not heuristic collapse
            # of table/page/document representations of the same passage.
            selected = [
                n
                for n in nodes
                if n.kind == "text_line"
                and n.text
                and all(fragment in n.text for fragment in selector.selector_value)
            ]
        elif selector.selector_type in {"pdf_page", "pdf_region"}:
            selected = [n for n in nodes if n.selector == selector and n.text]
        else:
            raise ValueError("unsupported PDF selector")
        if len(selected) != 1:
            raise ValueError(
                "ambiguous source selector"
                if selected
                else "no reproducible source passage"
            )
        return selected[0]

    def evidence_address(
        self, captured: CapturedSource, required_fragments: list[str]
    ) -> EvidenceAddress:
        selector = Selector("pdf_text", "1", tuple(required_fragments))
        return self._address(
            captured, self._selected_node(captured, selector), selector
        )

    def passage_evidence_addresses(
        self, captured: CapturedSource
    ) -> tuple[EvidenceAddress, ...]:
        return tuple(
            self._address(captured, n, n.selector)
            for n in self._evidence_nodes(captured)
            if n.kind == "text_line" and n.text and n.selector is not None
        )

    def evidence_address_for_segment(
        self, captured: CapturedSource, segment: StructuredSegment
    ) -> EvidenceAddress:
        if len(segment.inputs) != 1 or segment.inputs[0].mapping_kind != "exact":
            raise ValueError("one exact source input required for a passage address")
        m, raw = segment.inputs[0], captured.raw_reference
        if (
            m.source_key,
            m.source_ref,
            m.snapshot_ref,
            m.record_ref,
            m.raw_content_ref,
            m.raw_fingerprint,
        ) != (
            captured.record.source_key,
            raw.source_ref,
            raw.snapshot_ref,
            raw.record_ref,
            raw.raw_content_ref,
            raw.fingerprint,
        ) or m.selector is None:
            raise ValueError("segment/source integrity mismatch")
        node = self._selected_node(captured, m.selector)
        if node.text != segment.content or segment.policy_refs != raw.policy_refs:
            raise ValueError("segment/source content or policy mismatch")
        return self._address(captured, node, m.selector)

    def resolve(self, captured: CapturedSource, address: EvidenceAddress) -> bool:
        try:
            if (
                address.resolution_rule_ref != EVIDENCE_RULE
                or address.parser_tool_ref != self.parser_tool_ref
            ):
                return False
            node = self._selected_node(captured, address.selector)
            return self._address(captured, node, address.selector) == address
        except ValueError, TypeError, AttributeError:
            return False
