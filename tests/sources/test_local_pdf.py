from dataclasses import asdict, replace

import pytest

from cp_knowledge_tools.sources.adapters.local_html import LocalHtmlAdapter
from cp_knowledge_tools.sources.models import NormalizedSourceRepresentation, Selector
from tests.sources.pdf_fixture import digital_pdf

NOW = "2026-08-31T12:00:00+02:00"


@pytest.fixture
def adapter():
    from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter

    return LocalPdfAdapter()


def capture(adapter, tmp_path, data=None, **kwargs):
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(digital_pdf() if data is None else data)
    return adapter.capture("synthetic-pdf", path, captured_at=NOW, **kwargs)


def test_digital_pdf_neutral_structure_and_lineage(adapter, tmp_path):
    source = capture(adapter, tmp_path, digital_pdf(("First page.", "Second page.")))
    rep = adapter.normalize(source)
    rep.validate()
    assert isinstance(rep, NormalizedSourceRepresentation)
    assert rep.records[0].content == "First page.\nSecond page."
    assert rep.records[0].title == "Synthetic PDF"
    assert rep.records[0].creator_label == "Synthetic Author"
    assert {s.structure_type for s in rep.segments} >= {"document", "page", "text_line"}
    assert len(rep.records[0].inputs) == 2  # multiple page inputs -> one record
    assert all(
        s.inputs[0].snapshot_ref == source.snapshot.snapshot_ref for s in rep.segments
    )
    assert {f.hash_scope for f in rep.fingerprints} == {
        "raw_content",
        "metadata",
        "normalized_content",
        "structure",
    }
    assert rep.capture_coverage.status == rep.extraction_coverage.status == "complete"
    assert rep.normalization_coverage.status == "complete"
    assert "pdfplumber@" in rep.extraction_run.tool_ref
    assert "pdfminer.six@" in rep.extraction_run.tool_ref
    assert adapter.rebuild(source, rep) == rep


def test_ruled_table_and_region_geometry(adapter, tmp_path):
    rep = adapter.normalize(capture(adapter, tmp_path, digital_pdf(table=True)))
    assert {s.structure_type for s in rep.segments} >= {
        "table",
        "table_row",
        "table_cell",
    }
    cell = next(
        s
        for s in rep.segments
        if s.structure_type == "table_cell" and s.content == "Blue"
    )
    assert cell.inputs[0].selector.selector_type == "pdf_region"
    assert cell.inputs[0].mapping_kind == "exact"


def test_incomplete_ruled_grid_is_not_silently_repaired(adapter, tmp_path):
    source = capture(adapter, tmp_path, digital_pdf(table=True, table_gap=True))
    rep = adapter.normalize(source)
    assert not any(s.structure_type == "table" for s in rep.segments)
    assert rep.extraction_coverage.status == "partial_expected"
    assert {d.error_code for d in rep.diagnostics} & {
        "table_structure_unresolved",
        "vector_structure_unresolved",
    }
    assert "Team Count" in rep.records[0].content


def test_page_region_text_evidence_and_ambiguity(adapter, tmp_path):
    source = capture(
        adapter, tmp_path, digital_pdf(("Repeated passage.", "Repeated passage."))
    )
    with pytest.raises(ValueError, match="ambiguous"):
        adapter.evidence_address(source, ["Repeated passage."])
    rep = adapter.normalize(source)
    pages = [s for s in rep.segments if s.structure_type == "page"]
    addresses = [adapter.evidence_address_for_segment(source, s) for s in pages]
    assert len(addresses) == 2 and addresses[0] != addresses[1]
    assert all(
        a.selector.selector_type == "pdf_page" and adapter.resolve(source, a)
        for a in addresses
    )
    passages = adapter.passage_evidence_addresses(source)
    assert len(passages) == 2
    assert all(
        a.selector.selector_type == "pdf_region" and adapter.resolve(source, a)
        for a in passages
    )
    assert all(
        a.evidence_address_ref not in {s.segment_ref for s in rep.segments}
        for a in passages
    )


@pytest.mark.parametrize(
    "change",
    [
        {"snapshot_ref": "wrong"},
        {"source_key": "wrong"},
        {"raw_content_ref": "wrong"},
        {"content_hash": "0" * 64},
        {"text": "forged"},
        {"policy_refs": ("forged",)},
        {"parser_tool_ref": "old"},
        {"resolution_rule_ref": "unknown"},
        {"selector": Selector("html_dom_path", "1", ("/",))},
        {"selector": Selector("pdf_page", "999", ("1",))},
        {"selector": Selector("pdf_page", "1", ("999",))},
        {"selector": Selector("pdf_region", "1", ("1", "NaN", "0", "1", "2"))},
    ],
)
def test_forged_addresses_fail_closed(adapter, tmp_path, change):
    source = capture(adapter, tmp_path)
    address = adapter.evidence_address(source, ["limited to 16"])
    assert adapter.resolve(source, address)
    assert not adapter.resolve(source, replace(address, **change))
    assert not adapter.resolve(replace(source, raw_content=b"tampered"), address)


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"not PDF", "partial_error", "invalid_pdf"),
        (b"%PDF-1.4\ntruncated", "partial_error", "pdf_parse_failed"),
        (digital_pdf(("",)), "partial_expected", "no_digital_text"),
        (digital_pdf(("",), image=True), "partial_expected", "no_digital_text"),
    ],
)
def test_unsupported_input_is_never_empty_success(
    adapter, tmp_path, data, status, code
):
    source = capture(adapter, tmp_path, data)
    rep = adapter.normalize(source)
    rep.validate()
    assert not rep.records and not rep.segments
    assert rep.extraction_coverage.status == status
    assert rep.normalization_coverage.status == "unknown"
    assert code in {d.error_code for d in rep.diagnostics}
    assert all(d.source_context == "local_pdf" for d in rep.diagnostics)
    with pytest.raises(ValueError):
        adapter.evidence_address(source, ["absent"])


def test_mixed_document_reports_excluded_image_and_empty_page(adapter, tmp_path):
    rep = adapter.normalize(
        capture(adapter, tmp_path, digital_pdf(("Digital text.", ""), image=True))
    )
    assert rep.records[0].content == "Digital text."
    assert rep.extraction_coverage.status == "partial_expected"
    assert {d.error_code for d in rep.diagnostics} >= {
        "non_text_content",
        "no_digital_text",
    }


def test_cache_snapshot_metadata_config_and_raw_boundaries(adapter, tmp_path):
    from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter

    source = capture(adapter, tmp_path)
    original = adapter.normalize(source)
    metadata = capture(adapter, tmp_path, metadata=(("title", "External title"),))
    changed = adapter.normalize(metadata)
    assert original.extraction_run == changed.extraction_run
    assert original.normalization_run != changed.normalization_run
    assert original.records[0].title == "Synthetic PDF"
    # Capture is immutable even if the original locator is replaced.
    (tmp_path / "synthetic.pdf").write_bytes(b"not the captured source")
    assert adapter.normalize(source) == original
    different = LocalPdfAdapter(text_separator=" ").normalize(source)
    assert different.extraction_run == original.extraction_run
    assert different.normalization_run != original.normalization_run
    with pytest.raises(ValueError):
        LocalPdfAdapter(text_separator=" ").rebuild(source, original)
    limited = LocalPdfAdapter(max_pages=1)
    two_pages = capture(limited, tmp_path, digital_pdf(("One", "Two")))
    rep = limited.normalize(two_pages)
    assert rep.extraction_coverage.status == "partial_error"
    assert "pdf_limit_exceeded" in {d.error_code for d in rep.diagnostics}


def test_segment_mapping_cannot_collapse_multiple_inputs(adapter, tmp_path):
    source = capture(adapter, tmp_path)
    segment = next(
        s for s in adapter.normalize(source).segments if s.structure_type == "text_line"
    )
    with pytest.raises(ValueError):
        adapter.evidence_address_for_segment(
            source, replace(segment, inputs=segment.inputs * 2)
        )
    with pytest.raises(ValueError):
        adapter.evidence_address_for_segment(
            source, replace(segment, content="invented")
        )


def test_denial_happens_before_any_pdf_parsing(adapter, tmp_path, monkeypatch):
    source = capture(adapter, tmp_path, policy_refs=("SYNTHETIC-POLICY",))
    address = adapter.evidence_address(source, ["16 students"])
    assert address.policy_refs == ("SYNTHETIC-POLICY",)

    def forbidden(*args, **kwargs):
        pytest.fail("unauthorized parsing")

    monkeypatch.setattr(adapter, "resolve", forbidden)
    result = adapter.resolve_content(
        source, address, consumer_ref="reader", purpose="review"
    )
    assert asdict(result) == {
        "status": "not_authorized",
        "content": None,
        "diagnostic_code": None,
    }


@pytest.mark.parametrize("capacity", [16, 17])
def test_html_pdf_use_existing_semantic_consumer_without_special_case(
    adapter, tmp_path, capacity
):
    from cp_knowledge_tools.semantics import RuleBasedSemanticInterpreter

    sentence = f"The pilot is limited to {capacity} students."
    html = LocalHtmlAdapter()
    path = tmp_path / "same.html"
    path.write_text(f"<p>{sentence}</p>")
    sources = [
        (adapter, capture(adapter, tmp_path, digital_pdf((sentence,)))),
        (html, html.capture("synthetic-html", path, captured_at=NOW)),
    ]
    for current, source in sources:
        rep = current.normalize(source)
        evidence = current.evidence_address(source, [sentence])
        result = RuleBasedSemanticInterpreter().interpret(
            {rep.records[0].source_key: rep.records[0]},
            {"capacity": evidence},
            {
                "claims": [
                    {
                        "rule_key": "capacity",
                        "subject_entity_key": "pilot",
                        "predicate_ref": "example.capacity",
                        "evidence_keys": ["capacity"],
                        "extraction": {
                            "evidence_key": "capacity",
                            "pattern": r"limited to (?P<value>\d+) students",
                            "parser": "integer",
                        },
                        "epistemic_status": "reported",
                        "epistemic_classification_basis": "explicit_test_rule",
                    }
                ]
            },
        )
        claims = [
            c.proposed_claim for c in result.candidate_payloads if c.proposed_claim
        ]
        assert len(claims) == 1 and claims[0].value == capacity


@pytest.mark.parametrize("name", ["encrypted.pdf", "encrypted-empty-password.pdf"])
def test_encrypted_input_is_rejected_even_with_empty_password(adapter, tmp_path, name):
    from pathlib import Path

    data = (
        Path(__file__).parents[1] / "fixtures/source_to_knowledge/synthetic_pdf" / name
    ).read_bytes()
    rep = adapter.normalize(capture(adapter, tmp_path, data))
    assert rep.extraction_coverage.status == "partial_error"
    assert not rep.records
    assert {d.error_code for d in rep.diagnostics} == {"encrypted_pdf"}


def test_pdf_state_roundtrip_and_actual_content_invalidation(adapter, tmp_path):
    import json

    from cp_knowledge_tools.sources.storage import (
        SourceStore,
        evidence_address_from_dict,
    )

    source = capture(adapter, tmp_path)
    rep = adapter.normalize(source)
    store = SourceStore(tmp_path / "store")
    store.put_capture(source)
    store.put_representation(rep)
    loaded = store.load_capture(source.snapshot.snapshot_ref)
    restored = store.load_representation(rep.representation_ref)
    assert adapter.rebuild(loaded, restored) == rep
    address = adapter.evidence_address(source, ["16 students"])
    exported = evidence_address_from_dict(json.loads(json.dumps(address.to_dict())))
    assert adapter.resolve(loaded, exported)
    changed = capture(
        adapter, tmp_path, digital_pdf(("The pilot is limited to 17 students.",))
    )
    current = adapter.normalize(changed)
    assert current.extraction_run != rep.extraction_run
    assert not adapter.resolve(changed, address)
    old = {f.hash_scope: f for f in rep.fingerprints}
    new = {f.hash_scope: f for f in current.fingerprints}
    assert old["structure"] == new["structure"]
    assert old["metadata"] == new["metadata"]
    assert old["raw_content"] != new["raw_content"]
    assert old["normalized_content"] != new["normalized_content"]
    assert store.load_representation(rep.representation_ref) == rep


@pytest.mark.parametrize("limits", [{"max_bytes": 10}, {"max_chars": 3}])
def test_byte_and_character_limits_are_diagnostic(tmp_path, limits):
    from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter

    adapter = LocalPdfAdapter(**limits)
    source = capture(adapter, tmp_path)
    rep = adapter.normalize(source)
    assert not rep.records
    assert rep.extraction_coverage.status == "partial_error"
    assert {d.error_code for d in rep.diagnostics} == {"pdf_limit_exceeded"}


@pytest.mark.parametrize(
    "config",
    [
        dict(max_pages=True),
        dict(max_bytes=0),
        dict(max_chars=500001),
        dict(text_separator="|"),
    ],
)
def test_unsupported_configuration_fails(config):
    from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter

    with pytest.raises(ValueError):
        LocalPdfAdapter(**config)


def test_exact_regions_do_not_accept_nearby_geometry_or_other_page(adapter, tmp_path):
    source = capture(adapter, tmp_path, digital_pdf(("First page.", "Second page.")))
    address = adapter.passage_evidence_addresses(source)[0]
    values = address.selector.selector_value
    for replacement in [
        ("2", *values[1:]),
        (values[0], "50.001", *values[2:]),
        (*values[:2], "-999.000", *values[3:]),
        (*values[:4], "Infinity", *values[5:]),
    ]:
        invalid = replace(
            address, selector=replace(address.selector, selector_value=replacement)
        )
        assert not adapter.resolve(source, invalid)


def test_evidence_profile_stays_fixed_across_normalization_config(adapter, tmp_path):
    from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter

    source = capture(adapter, tmp_path)
    other = LocalPdfAdapter(text_separator=" ", max_chars=300000)
    address = adapter.evidence_address(source, ["16 students"])
    assert other.evidence_address(source, ["16 students"]) == address
    assert other.resolve(source, address)
    assert (
        other.normalize(source).extraction_run
        != adapter.normalize(source).extraction_run
    )


@pytest.mark.parametrize(
    "limits", [{"max_pages": 1}, {"max_bytes": 10}, {"max_chars": 3}]
)
def test_evidence_resolution_never_raises_caller_resource_limits(
    adapter, tmp_path, limits
):
    from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter

    source = capture(adapter, tmp_path, digital_pdf(("First page.", "Second page.")))
    address = adapter.evidence_address(source, ["Second page."])
    limited = LocalPdfAdapter(**limits)
    assert limited.normalize(source).extraction_coverage.status == "partial_error"
    assert not limited.resolve(source, address)
    with pytest.raises(ValueError, match="unavailable"):
        limited.evidence_address(source, ["Second page."])
    with pytest.raises(ValueError, match="unavailable"):
        limited.passage_evidence_addresses(source)
