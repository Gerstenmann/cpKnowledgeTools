# Digital PDF reference adapter

`LocalPdfAdapter` uses the existing captured source, snapshot, raw/source record,
normalized representation, mappings, storage and Evidence Address models. There
is no PDF-specific public model or downstream branch. The shared
`LocalFileAdapter` contains the unchanged local capture and independent consumer
Policy gate extracted from HTML.

```python
from pathlib import Path
from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter

adapter = LocalPdfAdapter()
captured = adapter.capture("registered-document-key", Path("document.pdf"))
representation = adapter.normalize(captured)
address = adapter.evidence_address(captured, ["a unique line fragment"])
assert adapter.resolve(captured, address)  # integrity only, never an access grant
```

The trusted host authorizes acquisition and processing. Consumer content access
uses `resolve_content` with independently evaluated Policy input/decision.
Denials do not inspect Source integrity or disclose existence. Snapshot Policy
anchors propagate to every output; no adapter-generated access grants exist.

## Representation and rebuild

pdfplumber/pdfminer open captured bytes through `BytesIO`; a replaced locator
cannot affect a snapshot. Native PDF/Page/character/table objects are closed
and discarded before returning. A bounded cache contains frozen technical nodes.
Its key includes bytes, parser/Python versions, rule and byte/page/character
limits. Capture metadata changes normalization/source binding, not extraction.

One normalized document contains pages in physical order. Document/page segments
contain positioned text lines and detected ruled table regions/rows/cells. Each
page lists positioned lines first, then tables in detector order; rows/cells
retain their grid order. This is not inferred logical reading order. Table output
is additional structure without duplicating text in the normalized document.
Document mappings retain every page input; N:M lineage is never silently reduced
to one Evidence passage. Only Title, Author and literal CreationDate project to
existing technical metadata fields. No semantic time, Claim, Entity, Evidence
Role or Knowledge interpretation occurs here.

The four fingerprint scopes remain raw bytes, metadata, normalized text and
hierarchy/order/types. Geometry is bound by selectors and extraction/normalization
output hashes, not added to the existing hierarchy fingerprint. `SourceStore`
round-trips the unchanged contract. `rebuild` freshly parses and requires equality
with the whole historical representation; missing parser/rule/config versions
fail instead of reinterpreting old state.

## Implementation-local selectors, version 1

These use the existing CPKS-SPEC-SRC typed extension point, not a new norm.

| Type | Value tuple | Exact target |
| --- | --- | --- |
| `pdf_page` | canonical one-based page number | Extracted text of that page |
| `pdf_region` | page, x0, top, x1, bottom, kind, ordinal | One extracted line/table/row/cell |
| `pdf_text` | nonempty fragments | Exactly one positioned line containing every fragment |

Coordinates are PDF points in pdfplumber's top-left coordinate space, formatted
to three decimals. Negative origins can exist in a PDF MediaBox. Ordinals retain
distinct technical regions with identical boxes. A region must match extraction
exactly; no fuzzy bbox, nearest-page or version fallback exists. Repeated text is
ambiguous. Text spanning lines needs a page/region mapping instead of a guessed
document match. Empty pages/cells provide no textual Evidence. Segment IDs and
Evidence Address IDs are separate.

Evidence @1 uses fixed extraction semantics, independent of optional normalization
settings, while retaining the caller's lowered resource budgets. The full binding,
including source/snapshot/record/raw references, selector,
text hash, parser/rule provenance and policies must equal a reconstructed address.
Segment addressing requires one exact input, matching content and policies.

## Limits and failure scope

This in-process local reference path is for controlled inputs, **not a sandbox
for arbitrary hostile PDF uploads**. Defaults are 20 MB, 200 pages and 500,000
characters; callers may only lower them. Checks are cooperative: capture reads
bytes before extraction checks, and parsing may decompress streams/materialize
pages before count checks. Host resource/process isolation for hostile workloads
is separate; this cycle introduces no ingestion service.

Capture, extraction and normalization coverage stay distinct. Unparseable,
encrypted (also empty-password), over-limit and failed parsing produce typed
errors, never successful empty records. This adapter is not a strict PDF
conformance validator; pdfminer can tolerate some malformed inputs. Missing digital text gives partial
extraction and unknown normalization. Mixed documents preserve digital text with
explicit omissions. Images, curves, annotations, unusual orientation and
unresolved vector/table structure are diagnosed. Logical order, attachments and
OCR are excluded. Complete normalization covers only extracted technical content.

No OCR, rendering, repair/Ghostscript, JavaScript, models, VLM, remote URL fetch,
credentials or Office support is enabled. Returned diagnostics contain sanitized
codes, not native exception text. Dependency evidence is in
`config/sources/pdf-dependency-admission.md`.
