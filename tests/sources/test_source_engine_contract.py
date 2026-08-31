"""Phase 1 contract tests derived from SRC, not the former HTML implementation."""

from __future__ import annotations

import json
from dataclasses import asdict, fields, replace

import pytest
from bs4 import BeautifulSoup

from cp_knowledge_tools.sources import models
from cp_knowledge_tools.sources.adapters.local_html import LocalHtmlAdapter

HTML = """<!doctype html><html><head><title>Fixture</title></head><body><article>
<header><h1>Heading</h1><dl><dt>From</dt><dd>Ada</dd></dl></header>
<p>First <b>technical</b> paragraph.</p><ul><li>One</li><li>Two</li></ul>
<blockquote>Quoted text</blockquote><aside class="internal-note"><p>Secret</p></aside>
</article></body></html>"""


def capture(tmp_path, html=HTML, **kwargs):
    path = tmp_path / "input.html"
    path.write_text(html, encoding="utf-8")
    return LocalHtmlAdapter().capture(
        "fixture", path, captured_at="2026-08-31T10:00:00+02:00", **kwargs
    )


def test_c1_explicit_roles_lineage_fingerprints_and_coverage(tmp_path):
    assert hasattr(models, "RawContentReference"), "missing snapshot-bound raw role"
    captured = capture(tmp_path)
    representation = LocalHtmlAdapter().normalize(captured)
    record = representation.records[0]
    assert isinstance(captured.record, models.SourceRecord)
    assert isinstance(record, models.NormalizedRecord)
    assert not hasattr(captured.record, "raw_html")
    assert not hasattr(captured.record, "normalized_text")
    raw = captured.raw_reference
    assert raw.snapshot_ref == captured.snapshot.snapshot_ref
    assert raw.record_ref == captured.record.record_ref
    assert raw.raw_content_ref != raw.locator != raw.source_ref
    assert raw.fingerprint.hash_scope == "raw_content"
    moved = replace(raw, locator="/other/location.html")
    assert moved.source_ref == raw.source_ref
    with pytest.raises(ValueError, match="snapshot"):
        replace(raw, snapshot_ref="")
    assert set(fp.hash_scope for fp in representation.fingerprints) == {
        "raw_content",
        "metadata",
        "normalized_content",
        "structure",
    }
    assert representation.capture_coverage.stage == "capture"
    assert representation.extraction_coverage.stage == "extraction"
    assert representation.normalization_coverage.stage == "normalization"
    first, second = representation.segments[:2]
    # N outputs may retain M inputs; no scalar-only lineage shortcut.
    merged = replace(first, inputs=(*first.inputs, *second.inputs))
    split = replace(second, inputs=merged.inputs)
    assert len(merged.inputs) == len(split.inputs) == 2
    assert merged.inputs[0].raw_content_ref == raw.raw_content_ref
    approximate = replace(first.inputs[0], mapping_kind="approximate")
    assert approximate.mapping_kind == "approximate"
    with pytest.raises(ValueError, match="lineage"):
        replace(first, inputs=())


def test_c2_html_structure_and_evidence_roundtrip(tmp_path):
    assert hasattr(LocalHtmlAdapter, "normalize"), "missing normalization stage"
    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    rep = adapter.normalize(captured)
    by_kind = {segment.structure_type: segment for segment in rep.segments}
    assert {"document", "body", "article", "h1", "p", "ul", "li", "blockquote"} <= set(
        by_kind
    )
    assert by_kind["article"].parent_ref == by_kind["body"].segment_ref
    assert by_kind["li"].parent_ref == by_kind["ul"].segment_ref
    assert [s.content for s in rep.segments if s.structure_type == "li"] == [
        "One",
        "Two",
    ]
    assert [s.order for s in rep.segments if s.structure_type == "li"] == [0, 1]
    assert rep.records[0].creator_label == "Ada"
    evidence = adapter.evidence_address(captured, ["technical", "paragraph"])
    assert evidence.selector.selector_type == "text_fragments"
    assert evidence.selector.selector_version == "1"
    assert adapter.resolve(captured, evidence)
    assert evidence.evidence_address_ref not in {s.segment_ref for s in rep.segments}
    assert all(
        adapter.resolve(captured, e)
        for e in adapter.passage_evidence_addresses(captured)
    )
    assert (
        "Secret" in rep.records[0].content
    )  # policy preserved, not silently discarded
    assert by_kind["aside"].policy_refs


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_key", "other"),
        ("source_ref", "SRC-other"),
        ("snapshot_ref", "SNAP-other"),
        ("record_ref", "REC-other"),
        ("content_hash", "0" * 64),
        ("text", "forged"),
        ("restricted", True),
        ("evidence_address_ref", "EVA-invented"),
    ],
)
def test_c3_resolution_rejects_forged_binding_or_payload(tmp_path, field, value):
    adapter = LocalHtmlAdapter()
    captured = adapter.capture("fixture", _write(tmp_path, HTML))
    evidence = adapter.evidence_address(captured, ["technical"])
    assert not adapter.resolve(captured, replace(evidence, **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("selector_type", "unknown"),
        ("selector_version", "999"),
        ("target_type", "claim"),
    ],
)
def test_c3_unknown_selector_fails_closed(tmp_path, field, value):
    assert hasattr(models, "Selector"), "untyped selector remains mutable"
    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    evidence = adapter.evidence_address(captured, ["technical"])
    invalid = replace(evidence.selector, **{field: value})
    assert not adapter.resolve(captured, replace(evidence, selector=invalid))


def test_c3_ambiguity_and_restricted_resolution_do_not_leak(tmp_path):
    adapter = LocalHtmlAdapter()
    captured = adapter.capture(
        "fixture", _write(tmp_path, "<p>Same</p><p class='internal-note'>Same</p>")
    )
    with pytest.raises(ValueError, match="ambiguous"):
        adapter.evidence_address(captured, ["Same"])
    addresses = adapter.passage_evidence_addresses(captured)
    assert len(addresses) == 2
    assert len({e.evidence_address_ref for e in addresses}) == 2
    assert {e.restricted for e in addresses} == {True, False}
    denied = adapter.resolve_content(
        captured, addresses[1], consumer_ref="reader", purpose="test"
    )
    assert denied.status == "not_authorized"
    assert denied.content is None
    assert "Same" not in json.dumps(asdict(denied))
    assert not hasattr(denied, "evidence_role")


def test_c4_roundtrip_rebuild_and_immutable_history(tmp_path):
    assert hasattr(models, "NormalizedSourceRepresentation"), (
        "missing rebuildable representation"
    )
    from cp_knowledge_tools.sources.storage import SourceStore

    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    rep = adapter.normalize(captured)
    assert adapter.normalize(captured) == rep
    store = SourceStore(tmp_path / "store")
    store.put_capture(captured)
    store.put_representation(rep)
    loaded = store.load_capture(captured.snapshot.snapshot_ref)
    restored = store.load_representation(rep.representation_ref)
    assert loaded == captured and restored == rep
    assert adapter.rebuild(loaded, restored) == rep
    old_bytes = captured.raw_content
    changed = capture(tmp_path, HTML.replace("First", "Changed"))
    newer = adapter.normalize(changed)
    store.put_capture(changed)
    store.put_representation(newer)
    assert loaded.raw_content == old_bytes
    assert store.load_representation(rep.representation_ref) == rep
    assert newer.representation_ref != rep.representation_ref
    with pytest.raises(ValueError, match="integrity|immutable"):
        store.put_capture(replace(captured, raw_content=b"tampered"))
    with pytest.raises(ValueError, match="dependency|provenance"):
        adapter.rebuild(
            captured,
            replace(
                rep, extraction_run=replace(rep.extraction_run, tool_ref="missing@1")
            ),
        )


def test_c4_incremental_dependencies_are_stage_specific(tmp_path):
    assert hasattr(LocalHtmlAdapter, "normalize"), (
        "missing dependency-aware normalization"
    )
    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    rep = adapter.normalize(captured)
    metadata_change = capture(tmp_path, metadata=(("title", "Changed title"),))
    meta_rep = adapter.normalize(metadata_change)
    assert rep.extraction_run.run_ref == meta_rep.extraction_run.run_ref
    assert rep.normalization_run.run_ref != meta_rep.normalization_run.run_ref
    assert _fp(rep, "raw_content") == _fp(meta_rep, "raw_content")
    assert _fp(rep, "normalized_content") == _fp(meta_rep, "normalized_content")
    assert _fp(rep, "metadata") != _fp(meta_rep, "metadata")
    configured = LocalHtmlAdapter(text_separator=" ").normalize(captured)
    assert configured.extraction_run == rep.extraction_run
    assert configured.normalization_run != rep.normalization_run
    parser_changed = LocalHtmlAdapter(
        excluded_tags=("script", "style", "template", "aside")
    ).normalize(captured)
    assert parser_changed.extraction_run != rep.extraction_run
    assert parser_changed.normalization_run != rep.normalization_run
    # A technical locator and capture timestamp are not parser inputs.
    relocated = replace(
        captured, raw_reference=replace(captured.raw_reference, locator="/moved.html")
    )
    assert adapter.normalize(relocated).extraction_run == rep.extraction_run
    assert adapter.normalize(relocated).records == rep.records


@pytest.mark.parametrize(
    "html,code",
    [
        ("", "empty_extraction"),
        ("<body><img src='x.png'></body>", "unsupported_content"),
        ("<body><iframe src='elsewhere'></iframe></body>", "unsupported_content"),
    ],
)
def test_c5_unsupported_or_empty_is_not_false_success(tmp_path, html, code):
    assert hasattr(LocalHtmlAdapter, "normalize"), "missing diagnostics and coverage"
    rep = LocalHtmlAdapter().normalize(capture(tmp_path, html))
    assert rep.extraction_coverage.status != "complete"
    assert rep.normalization_coverage.status != "complete"
    assert code in {d.error_code for d in rep.diagnostics}
    assert all(
        d.error_id and d.category and d.stage and d.retryability
        for d in rep.diagnostics
    )


def test_c5_partial_failure_preserves_upstream_coverage(tmp_path):
    assert hasattr(LocalHtmlAdapter, "normalize"), "missing partial result contract"
    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path, "<p>Readable</p><img src='x.png'>")
    rep = adapter.normalize(captured)
    assert rep.records[0].content == "Readable"
    assert rep.capture_coverage.status == "complete"
    assert rep.extraction_coverage.status == "partial_expected"
    assert rep.normalization_coverage.status == "complete"
    broken = adapter.capture("bad", _write_bytes(tmp_path, b"\xff\xfe"))
    failed = adapter.normalize(broken)
    assert failed.extraction_coverage.status == "partial_error"
    assert failed.normalization_coverage.status != "complete"
    assert "decoding_failed" in {d.error_code for d in failed.diagnostics}


def test_c5_no_semantics_dom_or_lost_lineage_at_neutral_boundary(tmp_path):
    assert hasattr(LocalHtmlAdapter, "normalize"), "missing neutral boundary"
    captured = capture(
        tmp_path,
        HTML.replace(
            "<p>", '<p data-claim="invented" data-evidence-role="supports">', 1
        ),
    )
    rep = LocalHtmlAdapter().normalize(captured)
    payload = asdict(rep)
    forbidden = {
        "claim",
        "event",
        "entity_ref",
        "evidence_role",
        "perspective",
        "rationale",
        "currentness",
        "semantic_relationship",
    }

    def inspect(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                inspect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                inspect(child)
        else:
            assert type(value) in (str, int, bool, type(None))

    inspect(payload)
    assert "data-claim" not in json.dumps(payload)
    segment = rep.segments[0]
    with pytest.raises((ValueError, TypeError), match="content|neutral"):
        replace(segment, content=BeautifulSoup("<p>native</p>", "html.parser"))
    with pytest.raises(ValueError, match="lineage"):
        replace(segment, inputs=())
    with pytest.raises(ValueError, match="snapshot|lineage"):
        replace(segment.inputs[0], snapshot_ref="")
    assert not forbidden.intersection(f.name for f in fields(segment))
    with pytest.raises(ValueError, match="integrity"):
        LocalHtmlAdapter().normalize(replace(captured, raw_content=b"other"))


def _write(tmp_path, html):
    return _write_bytes(tmp_path, html.encode("utf-8"))


def _write_bytes(tmp_path, content):
    path = tmp_path / "raw.html"
    path.write_bytes(content)
    return path


def _fp(rep, scope):
    return next(fp for fp in rep.fingerprints if fp.hash_scope == scope)


def test_c5_cache_cannot_hide_media_type_or_snapshot_mutation(tmp_path):
    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    adapter.normalize(captured)
    forged = replace(
        captured,
        record=replace(captured.record, media_type="text/plain"),
        raw_reference=replace(captured.raw_reference, media_type="text/plain"),
    )
    with pytest.raises(ValueError, match="integrity|media"):
        adapter.normalize(forged)
    with pytest.raises(ValueError, match="integrity"):
        adapter.normalize(
            replace(
                captured,
                snapshot=replace(
                    captured.snapshot,
                    capture_coverage=replace(
                        captured.snapshot.capture_coverage, status="unknown"
                    ),
                ),
            )
        )


@pytest.mark.parametrize(
    "mutation", ["content", "source_record", "output_hash", "structure_hash"]
)
def test_c5_rehashed_representation_does_not_hide_stale_contract_state(
    tmp_path, mutation
):
    from cp_knowledge_tools.sources.models import representation_identity

    rep = LocalHtmlAdapter().normalize(capture(tmp_path))
    if mutation == "content":
        rep = replace(rep, records=(replace(rep.records[0], content="forged"),))
    elif mutation == "source_record":
        rep = replace(rep, source_records=())
    elif mutation == "output_hash":
        rep = replace(
            rep,
            normalization_run=replace(
                rep.normalization_run,
                output_fingerprint=replace(
                    rep.normalization_run.output_fingerprint, value="0" * 64
                ),
            ),
        )
    else:
        rep = replace(
            rep,
            fingerprints=tuple(
                replace(fp, value="0" * 64) if fp.hash_scope == "structure" else fp
                for fp in rep.fingerprints
            ),
        )
    rep = replace(rep, representation_ref=representation_identity(rep))
    with pytest.raises(ValueError, match="fingerprint|lineage|integrity"):
        rep.validate()


def test_c4_rebuild_rejects_changed_config_and_missing_raw_dependency(tmp_path):
    from cp_knowledge_tools.sources.storage import SourceStore

    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    rep = adapter.normalize(captured)
    with pytest.raises(ValueError, match="dependency|configuration"):
        LocalHtmlAdapter(text_separator=" ").rebuild(captured, rep)
    store = SourceStore(tmp_path / "store")
    store.put_capture(captured)
    store.put_representation(rep)
    (tmp_path / "store/raw" / f"{captured.raw_reference.raw_content_ref}.bin").unlink()
    with pytest.raises(ValueError, match="dependency"):
        store.load_capture(captured.snapshot.snapshot_ref)


def test_c1_lineage_allows_multiple_raw_inputs_without_a_false_document_identity(
    tmp_path,
):
    from cp_knowledge_tools.sources.models import SourceMapping

    adapter = LocalHtmlAdapter()
    first = adapter.normalize(capture(tmp_path)).records[0]
    second_capture = adapter.capture(
        "second-source", _write(tmp_path, "<p>Second input</p>")
    )
    second = adapter.normalize(second_capture).records[0]
    inputs = (first.inputs[0], second.inputs[0])
    combined = replace(first, inputs=inputs)
    split = replace(second, inputs=inputs)
    assert all(isinstance(item, SourceMapping) for item in combined.inputs)
    assert len({i.raw_content_ref for i in split.inputs}) == 2
    with pytest.raises(ValueError, match="single source"):
        _ = combined.source_ref


def test_c4_evidence_json_roundtrip_is_typed_and_revalidated(tmp_path):
    from cp_knowledge_tools.sources.storage import evidence_address_from_dict

    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    address = adapter.evidence_address(captured, ["technical"])
    payload = json.loads(json.dumps(address.to_dict()))
    restored = evidence_address_from_dict(payload)
    assert restored == address and adapter.resolve(captured, restored)
    payload["evidence_role"] = "supports"
    with pytest.raises(ValueError, match="fields"):
        evidence_address_from_dict(payload)


def test_c5_snapshot_cannot_retain_mutable_metadata(tmp_path):
    with pytest.raises(ValueError, match="immutable|neutral"):
        capture(tmp_path, metadata=(["title", "Before"],))


def test_c2_exact_segment_can_be_addressed_but_approximate_mapping_cannot(tmp_path):
    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    rep = adapter.normalize(captured)
    segment = next(s for s in rep.segments if s.structure_type == "p")
    address = adapter.evidence_address_for_segment(captured, segment)
    assert address.evidence_address_ref != segment.segment_ref
    assert address.text == segment.content
    assert adapter.resolve(captured, address)
    for kind in ("approximate", "unresolved"):
        uncertain = replace(
            segment, inputs=(replace(segment.inputs[0], mapping_kind=kind),)
        )
        with pytest.raises(ValueError, match="exact"):
            adapter.evidence_address_for_segment(captured, uncertain)
    forged = replace(segment, content="invented content")
    with pytest.raises(ValueError, match="content|integrity"):
        adapter.evidence_address_for_segment(captured, forged)


@pytest.mark.parametrize(
    "mutation", ["raw_inputs", "normalization_inputs", "stage", "duplicate_scope"]
)
def test_c5_stage_provenance_and_fingerprint_scopes_cannot_be_forged(
    tmp_path, mutation
):
    from cp_knowledge_tools.sources.models import representation_identity

    rep = LocalHtmlAdapter().normalize(capture(tmp_path))
    if mutation == "raw_inputs":
        rep = replace(
            rep,
            extraction_run=replace(
                rep.extraction_run,
                input_fingerprints=(
                    replace(rep.extraction_run.input_fingerprints[0], value="0" * 64),
                ),
            ),
        )
    elif mutation == "normalization_inputs":
        rep = replace(
            rep, normalization_run=replace(rep.normalization_run, input_fingerprints=())
        )
    elif mutation == "stage":
        rep = replace(
            rep, normalization_run=replace(rep.normalization_run, stage="capture")
        )
    else:
        rep = replace(
            rep,
            fingerprints=(
                replace(_fp(rep, "structure"), value="0" * 64),
                *rep.fingerprints,
            ),
        )
    rep = replace(rep, representation_ref=representation_identity(rep))
    with pytest.raises(ValueError, match="fingerprint|provenance|stage"):
        rep.validate()


def test_semantic_document_consumer_does_not_silently_collapse_normalized_records(
    tmp_path,
):
    from cp_knowledge_tools.semantics.source_backed import (
        SourceBackedSemanticInterpreter,
    )

    adapter = LocalHtmlAdapter()
    captured = capture(tmp_path)
    record = adapter.normalize(captured).records[0]
    with pytest.raises(ValueError, match="one normalized record"):
        SourceBackedSemanticInterpreter().interpret(
            (record, replace(record, normalized_record_ref="NREC-second")),
            adapter.passage_evidence_addresses(captured),
            as_of="2026-08-31T10:00:00+02:00",
        )
