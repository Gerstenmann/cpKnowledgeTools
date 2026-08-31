# Local Source engine

This package implements the deterministic Local-HTML reference path through the
Source/Semantic boundary. It follows the live `CPKS-SPEC-SRC` and
`CPKT-SPEC-ARCH`; this README explains the implementation, not governance.

## Interfaces and boundaries

```python
from cp_knowledge_tools.sources.adapters.local_html import LocalHtmlAdapter
from cp_knowledge_tools.sources.storage import SourceStore

adapter = LocalHtmlAdapter()
captured = adapter.capture(registered_source_key, local_html_path)
representation = adapter.normalize(captured)
store = SourceStore(authorized_source_state_root)
store.put_capture(captured)
store.put_representation(representation)
# Existing semantic consumers receive representation.records, plus verified
# EvidenceAddresses. They never receive captured bytes or a BeautifulSoup tree.
```

| Role | Implementation |
| --- | --- |
| Adapter input | Explicit stable source key and local locator; this does not implement a registration authority/service |
| Snapshot | `SourceSnapshot`: capture time, scope/coverage, source binding, policy refs, capture rule and metadata |
| Raw reference | `RawContentReference`: snapshot/record binding, media type, byte fingerprint, locator and capture/policy refs |
| Captured state | `CapturedSource`: separate snapshot, record, raw reference and immutable bytes; validated before processing |
| Source unit | `SourceRecord`: source/snapshot/record identity, native media type and raw references; no raw or normalized content |
| Normalized state | `NormalizedSourceRepresentation`: records, segments, inputs, transformations, scoped fingerprints, stage coverage and diagnostics |
| Normalized record | `NormalizedRecord`: technical text and source-explicit title/time/creator/recipient labels, plus source mappings |
| Segment | `StructuredSegment`: technical type, text, parent, sibling order, policy refs and forward lineage |
| Evidence | `EvidenceAddress` and immutable `Selector`: a separate source passage identity, independently reproducible against captured bytes |

Every record and segment carries a tuple of `SourceMapping` inputs, allowing N:M
lineage. Reverse lineage is derived by grouping these inputs, not maintained as a
second truth. The HTML adapter emits one normalized document and many segments.
The existing semantic document consumers explicitly reject ambiguous multi-source
identity projections; they do not silently select one source from N:M inputs.

Mappings can be exact, approximate or unresolved. `evidence_address_for_segment`
requires one exact input and matching source content; it cannot promote an
approximation or multiple source fragments into one exact passage address.
Normalizing structure creates no claims, events, entities, evidence roles,
perspectives, currentness or domain relationships. Arbitrary HTML attributes such
as `data-claim` are not copied into the neutral contract. BeautifulSoup objects
remain inside the adapter.

## Determinism, fingerprints and reuse

The implementation-local `cpkt.raw-bytes@1` rule hashes exact captured bytes with
SHA-256. `cpkt.source.json@1` hashes UTF-8 JSON using sorted object keys, compact
separators and unescaped Unicode; arrays retain order and strings retain their
Unicode codepoints. These models use strings, integers, booleans, null and
immutable tuples/dataclasses, with strict JSON decoding. No float, mutable/native
parser object or arbitrary JSON field is part of the contract. These rules are
technical reference-engine rules, not newly approved system-wide canonicalization
Profiles or a production cryptographic conformance claim.

Raw bytes, source metadata, normalized text and technical structure have separate
fingerprints. Structure fingerprints omit text and generated IDs. Representation
identity binds the complete technical state. Snapshot identity also binds the
capture instant, metadata, media type, coverage and source policies; a new capture
is a new observation, while rebuilding an existing snapshot is deterministic.
The locator is provenance, never the source identity or a parser dependency.

Extraction reuse is scoped to one adapter instance. Its key binds the verified
raw fingerprint, media type, explicit `html.parser`, BeautifulSoup/SoupSieve/Python
versions, extraction rule and configuration. Metadata-only changes reuse that
extraction. Normalization additionally binds extraction output/run, metadata,
source/snapshot/record/policy/coverage and the normalization rule/tool/config.
Changing text separation preserves extraction; changing exclusion rules invalidates
extraction and normalization. Semantic processing is not an upstream dependency.

`rebuild(captured, previous)` checks available rule/tool versions, runs a fresh
parse independently of the cache and compares the complete representation,
including configuration, mappings, coverage and fingerprints. Unknown historical
rules/tools or unavailable source inputs fail; there is no guessed migration.
Algorithm changes require a new local rule/tool version. Stored state is
self-checking, not signed evidence of authenticity against a hostile store owner.

## HTML scope, coverage and errors

The parser preserves document/body/article boundaries, headings, paragraphs,
lists/items, blockquotes, other technical containers, sibling order and parents.
Its deterministic text extraction uses the captured document, including multiple
articles, without a scenario-specific root or semantic annotation. Source-explicit
metadata extraction remains technical. It does not execute scripts, access remote
URLs, render CSS or infer visual layout.

Capture covers the local file bytes. Extraction covers document text/structure,
with excluded head/script/style/template paths recorded. Images, embedded pages,
SVG/canvas, audio/video and objects are unsupported and produce diagnostics and
partial coverage. Empty text is not success; invalid UTF-8 produces an explicit
extraction failure. Normalization may be complete for an extracted subset, while
upstream partial coverage stays visible. HTML syntax repair follows the pinned
Python parser behavior; `complete` is not a claim of browser rendering fidelity.

## Evidence and policy

Supported selectors are `text_fragments@1` and `html_dom_path@1`, both targeting
`source_passage`. Paths address tag-child indices in the captured parser tree.
Disjoint fragment matches are ambiguous. Occurrences with identical text retain
separate path addresses. Unknown selector types, versions, targets, changed
bindings, text, policy flags, hashes and parser/rule references fail closed.
Evidence IDs bind the full typed address. They are never segment IDs.

`evidence_address`, passage enumeration and boolean `resolve` are trusted local
source-processing/verification APIs. Their return values are not consumer permits.
They may contain restricted text already admitted into the processing context.
The `internal-note` HTML marker is preserved as a restriction anchor and inherited
by containing passages; it grants no authority. Source policies survive capture,
normalization and addressing. The host must independently authorize acquisition
and processing; this reference adapter does not create an acquisition policy.

`resolve_content` checks an independently evaluated `PolicyDecision` against its
exact `PolicyEvaluationInput`, consumer, purpose, mode, policy anchors and concrete
Evidence/Snapshot subjects (local version `1`, context `Source and Evidence`).
Content requires `resolve_evidence` plus `read_content`; metadata-only requires
`read_metadata` and returns no text. Denied discovery reveals no existence,
structure or content. Unsupported modes, stale decisions and conditions requiring
unimplemented redaction deny access. Successful technical resolution creates no
Evidence Role. The Python host/evaluator is trusted; arbitrary callers cannot
supply their own permits across an exposed service boundary.

## Storage, migration and recovery

`SourceStore` writes raw bytes, snapshot manifests and normalized representations
separately. JSON has a strict versioned envelope. Publication uses a complete
fsynced temporary file plus no-clobber creation; identical retries succeed and
conflicting writes fail without overwriting history. Reads validate IDs, content
integrity, lineage and source dependencies. Evidence manifests use
`EvidenceAddress.to_dict` and `evidence_address_from_dict`, followed by adapter
resolution; decoding alone grants no trust.

The storage root must be selected and access-controlled by the trusted local host.
This is not a general filesystem sandbox, a durable multi-file transaction or a
retention service. A crash may leave an unreferenced raw blob or temporary file;
existing referenced history is never replaced. Source bytes and normalized text
remain subject to the same storage/access policy. Synthetic runner outputs stay
under their selected run directory and are not canonical Knowledge or Golden data.

Both Minecraft runners use this store and pass only normalized records to semantic
processing. The only downstream changes are type/content access and explicit
pipeline reporting. Existing scenario expectations and Golden fixture bytes are
preserved; the previous overloaded `SourceRecord` constructor is intentionally
replaced, without maintaining a second raw/normalized API.

## Reuse and limits

The required DEV-P06 assessment chose WRAP/REFACTOR of the existing BeautifulSoup
integration and USE of internal hashing/serialization patterns. Building another
HTML parser or adding a dependency would not improve this scope. No library was
added, updated, installed or copied. The installed parser dependencies are
recorded in each transformation; no CVE or broad upstream maintenance audit is
claimed. Technical parsing rationale follows the
[official BeautifulSoup documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/index.html).

The Standard Operation Registry was inspected: its governance/artifact/incident
operations do not implement Source storage, normalization or reuse-assessment
serialization. This bounded component therefore implements its own domain
operations and uses the existing reuse core directly, without expanding the kernel.

Focused tests live in `tests/sources/test_source_engine_contract.py` and
`test_source_engine_resolution.py`; existing Source, Semantic, Policy and Minecraft
E2E regressions remain applicable. PDF, OCR, STT, Vision, Office/new mail adapters,
federation, LLM generation and new Knowledge/publication semantics are outside this
checkpoint. A later PDF cycle requires its own candidate decision.
