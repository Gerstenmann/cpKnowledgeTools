"""Immutable technical Source contracts; no parser objects or Knowledge semantics.

The @1 representation rules are implementation-local deterministic rules for the
local reference engine, not newly approved CPKS Profiles. See sources/README.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass

from cp_knowledge_tools.platform.hashing import (
    canonical_json_hash,
    sha256_bytes,
    stable_token,
)


def _neutral(value: object) -> None:
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            _neutral(getattr(value, field.name))
    elif type(value) is tuple:
        for child in value:
            _neutral(child)
    elif type(value) not in (str, int, bool, type(None)):
        raise ValueError(
            "source-neutral content must contain immutable technical values"
        )


def _required(**values: str) -> None:
    for name, value in values.items():
        if type(value) is not str or not value.strip():
            raise ValueError(f"missing {name}")


@dataclass(frozen=True, slots=True)
class Fingerprint:
    hash_scope: str
    value: str
    algorithm: str = "sha256"
    canonicalization_profile: str = "cpkt.source.json@1"

    def __post_init__(self):
        _required(scope=self.hash_scope, profile=self.canonicalization_profile)
        if (
            self.algorithm != "sha256"
            or len(self.value) != 64
            or any(c not in "0123456789abcdef" for c in self.value)
        ):
            raise ValueError("unsupported fingerprint or invalid digest")


def fingerprint(scope: str, value: object) -> Fingerprint:
    return Fingerprint(scope, canonical_json_hash(value))


@dataclass(frozen=True, slots=True)
class Coverage:
    stage: str
    status: str
    declared_scope: tuple[str, ...]
    successful_scope: tuple[str, ...] = ()
    excluded_scope: tuple[str, ...] = ()
    failed_scope: tuple[str, ...] = ()
    diagnostic_refs: tuple[str, ...] = ()

    def __post_init__(self):
        _neutral(self)
        if self.stage not in {
            "capture",
            "extraction",
            "normalization",
        } or self.status not in {
            "complete",
            "partial_expected",
            "partial_error",
            "unknown",
        }:
            raise ValueError("unknown coverage stage or status")
        if not self.declared_scope or (self.status == "complete" and self.failed_scope):
            raise ValueError("coverage scope inconsistent")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    error_id: str
    error_code: str
    stage: str
    category: str
    severity: str
    message: str
    subject_refs: tuple[str, ...]
    retryability: str = "not_retryable"
    contract_name: str = "Normalized Source Representation Contract"
    contract_version: str = "0.2"
    rule_source: str = "CPKS-SPEC-SRC"
    source_context: str = "local_html"


@dataclass(frozen=True, slots=True)
class Selector:
    selector_type: str
    selector_version: str
    selector_value: tuple[str, ...]
    target_type: str = "source_passage"

    def __post_init__(self):
        _neutral(self)
        _required(
            selector_type=self.selector_type,
            selector_version=self.selector_version,
            target_type=self.target_type,
        )
        if (
            type(self.selector_value) is not tuple
            or not self.selector_value
            or any(type(v) is not str or not v for v in self.selector_value)
        ):
            raise ValueError("invalid selector payload")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RawContentReference:
    raw_content_ref: str
    source_ref: str
    snapshot_ref: str
    record_ref: str
    locator: str
    media_type: str
    fingerprint: Fingerprint
    policy_refs: tuple[str, ...]
    capture_ref: str

    def __post_init__(self):
        _neutral(self)
        _required(
            raw_content_ref=self.raw_content_ref,
            source_ref=self.source_ref,
            snapshot_ref=self.snapshot_ref,
            record_ref=self.record_ref,
            locator=self.locator,
            capture_ref=self.capture_ref,
        )
        if self.fingerprint.hash_scope != "raw_content":
            raise ValueError("raw content fingerprint scope mismatch")


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_key: str
    source_ref: str
    snapshot_ref: str
    record_ref: str
    media_type: str
    raw_content_refs: tuple[str, ...]

    def __post_init__(self):
        _neutral(self)
        _required(
            source_key=self.source_key,
            source_ref=self.source_ref,
            snapshot_ref=self.snapshot_ref,
            record_ref=self.record_ref,
        )
        if not self.raw_content_refs:
            raise ValueError("missing raw content reference")


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    snapshot_ref: str
    source_ref: str
    captured_at: str
    capture_ref: str
    capture_coverage: Coverage
    policy_refs: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    capture_rule_ref: str = "cpkt.local-file.capture@1"

    def __post_init__(self):
        _neutral(self)
        _required(
            snapshot_ref=self.snapshot_ref,
            source_ref=self.source_ref,
            capture_ref=self.capture_ref,
            captured_at=self.captured_at,
        )


def snapshot_identity(snapshot: SourceSnapshot, raw: RawContentReference) -> str:
    return stable_token(
        "SNAP",
        snapshot.source_ref,
        raw.fingerprint.value,
        canonical_json_hash(snapshot.metadata),
        snapshot.captured_at,
        canonical_json_hash(snapshot.policy_refs),
        raw.media_type,
        canonical_json_hash(asdict(snapshot.capture_coverage)),
    )


@dataclass(frozen=True, slots=True)
class CapturedSource:
    snapshot: SourceSnapshot
    record: SourceRecord
    raw_reference: RawContentReference
    raw_content: bytes

    def validate(self) -> None:
        raw, snap, rec = self.raw_reference, self.snapshot, self.record
        _neutral(snap)
        expected = snapshot_identity(snap, raw)
        if (
            type(self.raw_content) is not bytes
            or raw.fingerprint
            != Fingerprint(
                "raw_content",
                sha256_bytes(self.raw_content),
                canonicalization_profile="cpkt.raw-bytes@1",
            )
            or rec.source_ref != stable_token("SRC", rec.source_key)
            or raw.source_ref != rec.source_ref
            or snap.source_ref != rec.source_ref
            or raw.snapshot_ref != expected
            or snap.snapshot_ref != expected
            or rec.snapshot_ref != expected
            or rec.record_ref != stable_token("REC", expected, "document")
            or raw.record_ref != rec.record_ref
            or raw.raw_content_ref
            != stable_token("RAW", expected, raw.fingerprint.value)
            or rec.raw_content_refs != (raw.raw_content_ref,)
            or raw.media_type != rec.media_type
            or raw.capture_ref != snap.capture_ref
            or raw.policy_refs != snap.policy_refs
            or snap.capture_ref != stable_token("CAP", expected, snap.capture_rule_ref)
            or snap.capture_rule_ref != "cpkt.local-file.capture@1"
            or snap.capture_coverage.stage != "capture"
        ):
            raise ValueError("snapshot/raw integrity mismatch")
        if len(dict(snap.metadata)) != len(snap.metadata) or any(
            key not in {"title", "source_time"} or type(value) is not str
            for key, value in snap.metadata
        ):
            raise ValueError("unsupported capture metadata")


@dataclass(frozen=True, slots=True)
class SourceMapping:
    source_key: str
    source_ref: str
    snapshot_ref: str
    record_ref: str
    raw_content_ref: str
    raw_fingerprint: Fingerprint
    selector: Selector | None
    stage_ref: str
    mapping_kind: str = "exact"
    diagnostic_refs: tuple[str, ...] = ()

    def __post_init__(self):
        _neutral(self)
        _required(
            source_ref=self.source_ref,
            snapshot_ref=self.snapshot_ref,
            record_ref=self.record_ref,
            raw_content_ref=self.raw_content_ref,
            stage_ref=self.stage_ref,
        )
        if self.mapping_kind not in {"exact", "approximate", "unresolved"}:
            raise ValueError("unknown lineage mapping kind")
        if self.mapping_kind == "exact" and not isinstance(self.selector, Selector):
            raise ValueError("exact lineage requires a selector")


@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    normalized_record_ref: str
    content: str
    inputs: tuple[SourceMapping, ...]
    media_type: str = "text/plain"
    title: str = ""
    source_time: str | None = None
    creator_label: str | None = None
    recipient_labels: tuple[str, ...] = ()
    policy_refs: tuple[str, ...] = ()

    def __post_init__(self):
        _neutral(self)
        if type(self.content) is not str:
            raise ValueError("content must be source-neutral text")
        if not self.inputs or any(
            not isinstance(i, SourceMapping) for i in self.inputs
        ):
            raise ValueError("normalized record requires source lineage")

    def _single_source_value(self, field: str):
        """Existing document consumers cannot silently choose from N:M inputs."""
        values = {getattr(i, field) for i in self.inputs}
        if len(values) != 1:
            raise ValueError("consumer requires a single source document")
        return values.pop()

    @property
    def source_key(self) -> str:
        return self._single_source_value("source_key")

    @property
    def source_ref(self) -> str:
        return self._single_source_value("source_ref")

    @property
    def snapshot_ref(self) -> str:
        return self._single_source_value("snapshot_ref")

    @property
    def record_ref(self) -> str:
        return self._single_source_value("record_ref")

    @property
    def raw_sha256(self) -> str:
        return self._single_source_value("raw_fingerprint").value


@dataclass(frozen=True, slots=True)
class StructuredSegment:
    segment_ref: str
    normalized_record_ref: str
    parent_ref: str | None
    order: int
    segment_type: str
    structure_type: str
    media_type: str
    content: str
    inputs: tuple[SourceMapping, ...]
    policy_refs: tuple[str, ...] = ()

    def __post_init__(self):
        _neutral(self)
        if type(self.content) is not str:
            raise ValueError("segment content must be source-neutral text")
        if not self.inputs or any(
            not isinstance(i, SourceMapping) for i in self.inputs
        ):
            raise ValueError("segment requires source lineage")
        if type(self.order) is not int or self.order < 0:
            raise ValueError("invalid technical order")


@dataclass(frozen=True, slots=True)
class TransformationRun:
    run_ref: str
    stage: str
    tool_ref: str
    rule_ref: str
    config: tuple[tuple[str, str], ...]
    input_fingerprints: tuple[Fingerprint, ...]
    output_fingerprint: Fingerprint

    def __post_init__(self):
        _neutral(self)
        _required(run_ref=self.run_ref, tool_ref=self.tool_ref, rule_ref=self.rule_ref)


@dataclass(frozen=True, slots=True)
class NormalizedSourceRepresentation:
    representation_ref: str
    records: tuple[NormalizedRecord, ...]
    segments: tuple[StructuredSegment, ...]
    raw_references: tuple[RawContentReference, ...]
    source_records: tuple[SourceRecord, ...]
    fingerprints: tuple[Fingerprint, ...]
    capture_coverage: Coverage
    extraction_coverage: Coverage
    normalization_coverage: Coverage
    extraction_run: TransformationRun
    normalization_run: TransformationRun
    diagnostics: tuple[Diagnostic, ...]
    contract_version: str = "0.2"

    def __post_init__(self):
        _neutral(self)
        if self.contract_version != "0.2":
            raise ValueError("unknown normalized representation version")

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> None:
        _neutral(self)
        if self.representation_ref != representation_identity(self):
            raise ValueError("representation integrity mismatch")
        raw = {r.raw_content_ref: r for r in self.raw_references}
        source_records = {r.record_ref: r for r in self.source_records}
        if not raw or not source_records:
            raise ValueError("missing raw/source-record lineage")
        records = {r.normalized_record_ref for r in self.records}
        segments = {s.segment_ref: s for s in self.segments}
        if len(segments) != len(self.segments) or len(records) != len(self.records):
            raise ValueError("duplicate normalized identity")
        for output in (*self.records, *self.segments):
            for mapping in output.inputs:
                ref = raw.get(mapping.raw_content_ref)
                source_record = source_records.get(mapping.record_ref)
                if (
                    not source_record
                    or source_record.source_key != mapping.source_key
                    or source_record.source_ref != mapping.source_ref
                    or source_record.snapshot_ref != mapping.snapshot_ref
                    or mapping.raw_content_ref not in source_record.raw_content_refs
                    or mapping.stage_ref != self.normalization_run.run_ref
                ):
                    raise ValueError("unresolved source-record/stage lineage")
                if not ref or (
                    mapping.source_ref,
                    mapping.snapshot_ref,
                    mapping.record_ref,
                    mapping.raw_fingerprint,
                ) != (
                    ref.source_ref,
                    ref.snapshot_ref,
                    ref.record_ref,
                    ref.fingerprint,
                ):
                    raise ValueError("unresolved source/snapshot lineage")
        seen: set[str] = set()
        orders: set[tuple[str, str | None, int]] = set()
        for segment in self.segments:
            key = (segment.normalized_record_ref, segment.parent_ref, segment.order)
            if (
                segment.normalized_record_ref not in records
                or segment.parent_ref is not None
                and segment.parent_ref not in seen
                or segment.parent_ref in segments
                and segments[segment.parent_ref].normalized_record_ref
                != segment.normalized_record_ref
                or key in orders
            ):
                raise ValueError("invalid parent/order structure")
            seen.add(segment.segment_ref)
            orders.add(key)
        if {f.hash_scope for f in self.fingerprints} != {
            "raw_content",
            "metadata",
            "normalized_content",
            "structure",
        }:
            raise ValueError("missing scoped fingerprints")
        by_scope = {f.hash_scope: f for f in self.fingerprints}
        if any(
            sum(f.hash_scope == scope for f in self.fingerprints) != 1
            for scope in ("metadata", "normalized_content", "structure")
        ):
            raise ValueError("duplicate fingerprint scope")
        raw_inputs = {r.fingerprint for r in raw.values()}
        if (
            self.extraction_run.stage != "extraction"
            or self.normalization_run.stage != "normalization"
            or set(self.extraction_run.input_fingerprints) != raw_inputs
            or self.extraction_run.output_fingerprint
            not in self.normalization_run.input_fingerprints
            or by_scope["metadata"] not in self.normalization_run.input_fingerprints
            or source_binding_fingerprint(
                self.source_records, self.raw_references, self.capture_coverage
            )
            not in self.normalization_run.input_fingerprints
        ):
            raise ValueError("stage input fingerprint/provenance mismatch")
        if (
            by_scope["normalized_content"]
            != fingerprint("normalized_content", [r.content for r in self.records])
            or by_scope["structure"] != structure_fingerprint(self.segments)
            or self.normalization_run.output_fingerprint
            != normalization_fingerprint(self.records, self.segments)
            or {r.fingerprint for r in raw.values()}
            != {f for f in self.fingerprints if f.hash_scope == "raw_content"}
        ):
            raise ValueError(
                "normalized/structure/output fingerprint integrity mismatch"
            )
        if self.records and by_scope["metadata"] != fingerprint(
            "metadata",
            [
                {
                    "title": r.title,
                    "source_time": r.source_time,
                    "creator_label": r.creator_label,
                    "recipient_labels": r.recipient_labels,
                }
                for r in self.records
            ],
        ):
            raise ValueError("metadata fingerprint integrity mismatch")
        for coverage, stage in (
            (self.capture_coverage, "capture"),
            (self.extraction_coverage, "extraction"),
            (self.normalization_coverage, "normalization"),
        ):
            if coverage.stage != stage or not set(coverage.diagnostic_refs) <= {
                d.error_id for d in self.diagnostics
            }:
                raise ValueError("coverage/diagnostic mismatch")
        if not self.records and self.normalization_coverage.status == "complete":
            raise ValueError("empty extraction is not normalization success")


def structure_fingerprint(segments: tuple[StructuredSegment, ...]) -> Fingerprint:
    indices = {s.segment_ref: index for index, s in enumerate(segments)}
    return fingerprint(
        "structure",
        [
            (
                indices.get(s.parent_ref),
                s.order,
                s.segment_type,
                s.structure_type,
                s.media_type,
            )
            for s in segments
        ],
    )


def source_binding_fingerprint(
    records: tuple[SourceRecord, ...],
    raw: tuple[RawContentReference, ...],
    coverage: Coverage,
) -> Fingerprint:
    return fingerprint(
        "source_binding",
        {
            "records": [asdict(r) for r in records],
            "policies": sorted({policy for r in raw for policy in r.policy_refs}),
            "coverage": asdict(coverage),
        },
    )


def normalization_fingerprint(
    records: tuple[NormalizedRecord, ...], segments: tuple[StructuredSegment, ...]
) -> Fingerprint:
    return fingerprint(
        "normalization_output",
        {
            "records": [asdict(r) for r in records],
            "segments": [asdict(s) for s in segments],
        },
    )


def representation_identity(rep: NormalizedSourceRepresentation) -> str:
    payload = asdict(rep)
    payload.pop("representation_ref")
    return stable_token("NSR", canonical_json_hash(payload))


@dataclass(frozen=True, slots=True)
class EvidenceAddress:
    evidence_address_ref: str
    source_key: str
    source_ref: str
    snapshot_ref: str
    record_ref: str
    selector: Selector
    content_hash: str
    text: str
    restricted: bool
    raw_content_ref: str = ""
    policy_refs: tuple[str, ...] = ()
    resolution_rule_ref: str = "cpkt.local-html.evidence@1"
    parser_tool_ref: str = ""

    def __post_init__(self):
        _neutral(self)
        if not isinstance(self.selector, Selector):
            raise ValueError("typed selector required")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    status: str
    content: str | None = None
    diagnostic_code: str | None = None
