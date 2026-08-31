"""WI-017 adapter_conformance: two inputs, independent provenance, one consumer.

Projection is an assertion-only test oracle. Never feed projected content or
Golden expectations back into capture, normalization or semantic interpretation.
"""

from __future__ import annotations

import ast
import builtins
import io
import json
import re
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from pathlib import Path

import pdfplumber
import pytest
from bs4 import BeautifulSoup

from cp_knowledge_tools.policy import (
    PolicyConfiguration,
    PolicyEvaluationInput,
    PolicyEvaluator,
    PolicyRule,
    PolicySubject,
    ProfileApplicability,
)
from cp_knowledge_tools.semantics import RuleBasedSemanticInterpreter
from cp_knowledge_tools.sources import (
    CapturedSource,
    EvidenceAddress,
    NormalizedRecord,
    NormalizedSourceRepresentation,
    RawContentReference,
    SourceMapping,
    SourceRecord,
    SourceSnapshot,
    StructuredSegment,
)
from cp_knowledge_tools.sources.adapters.local_html import LocalHtmlAdapter
from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter
from cp_knowledge_tools.sources.storage import SourceStore, evidence_address_from_dict
from tests.sources.pdf_fixture import digital_pdf

TESTS = Path(__file__).resolve().parents[1]
INPUTS = TESTS / "fixtures/source_to_knowledge/cross_format_html_pdf"
GOLDEN = TESTS / "golden/source_to_knowledge/cross_format_html_pdf/expected.v1.json"
NOW = "2026-08-31T10:00:00+02:00"
CONSUMER = "SYNTHETIC-WI017-READER"
PURPOSE = "synthetic_conformance_review"
POLICY = "SYNTHETIC-WI017-POLICY"
SCOPE = "synthetic_source_resolution"

# Syntax and mappings, never expected material values. Same rules for both sides.
EXTRACTIONS = {
    "capacity": (r"limited\s+to\s+(?P<value>\d+)\s+students", "integer"),
    "training_date": (r"starts\s+on\s+(?P<value>\d{1,2}\s+[A-Za-z]+\s+\d{4})", "date"),
    "budget": (r"cost\s+ceiling\s+of\s+EUR\s+(?P<value>[\d,]+)", "integer"),
}


def rules_for(case):
    keys = ("capacity", "training_date") if case == "open" else ("budget",)
    claims = []
    for key in keys:
        pattern, parser = EXTRACTIONS[key]
        rule = {
            "rule_key": key,
            "subject_entity_key": "pilot",
            "predicate_ref": f"example.{key}",
            "evidence_keys": [key],
            "extraction": {"evidence_key": key, "pattern": pattern, "parser": parser},
            "epistemic_status": "reported",
            "epistemic_classification_basis": "explicit_test_interpretation_rule",
        }
        if key == "training_date":
            rule.update(
                time_role="event_time", time_precision="day", time_modality="planned"
            )
        if key == "budget":
            rule["value_qualifier"] = "provisional"
        claims.append(rule)
    return {
        "claims": claims,
        "evidence_links": [
            {
                "rule_key": f"{key}_link",
                "claim_key": key,
                "evidence_key": key,
                "role": "reports_statement",
            }
            for key in keys
        ],
    }


@dataclass
class Side:
    adapter: LocalHtmlAdapter | LocalPdfAdapter
    captured: CapturedSource
    representation: NormalizedSourceRepresentation
    evidence: dict[str, EvidenceAddress]


def prepare(adapter, path, source_key, rules, anchor):
    captured = adapter.capture(source_key, path, captured_at=NOW, policy_refs=(anchor,))
    rep = adapter.normalize(captured)
    evidence = {}
    for rule in rules["claims"]:
        pattern = rule["extraction"]["pattern"]
        matches = [
            segment
            for segment in rep.segments
            if len(segment.inputs) == 1
            and segment.inputs[0].mapping_kind == "exact"
            and re.search(pattern, segment.content)
        ]
        assert matches, "missing grounded passage"
        # Smallest matching source extent. Multiple equal extents on the same
        # ancestor chain are equivalent containers; separate locations are not.
        shortest = min(len(s.content) for s in matches)
        minimal = [s for s in matches if len(s.content) == shortest]
        by_ref = {s.segment_ref: s for s in rep.segments}
        leaves = []
        for candidate in minimal:
            ancestors = set()
            for other in minimal:
                parent = other.parent_ref
                while parent is not None:
                    ancestors.add(parent)
                    parent = by_ref[parent].parent_ref
            if candidate.segment_ref not in ancestors:
                leaves.append(candidate)
        assert len(leaves) == 1, "ambiguous grounded passage"
        evidence[rule["rule_key"]] = adapter.evidence_address_for_segment(
            captured, leaves[0]
        )
    return Side(adapter, captured, rep, evidence)


@pytest.fixture(params=("open", "restricted"))
def pair(request):
    case = request.param
    scenario = json.loads((INPUTS / "scenario.v1.json").read_text())
    assert scenario["scenario_role"] == "adapter_conformance" and scenario["synthetic"]
    config = scenario["cases"][case]
    rules = rules_for(case)
    sides = tuple(
        prepare(
            factory(),
            INPUTS / config["inputs"][name],
            f"wi017-{case}-{name}",
            rules,
            config["policy_anchor"],
        )
        for name, factory in (("html", LocalHtmlAdapter), ("pdf", LocalPdfAdapter))
    )
    return case, rules, sides


def whitespace(text):
    return " ".join(text.split())


def content_text(text):
    # Inline HTML can place sentence punctuation in a separate text node.
    # Ignore that whitespace only at a sentence end, never join words/digits
    # or discard punctuation (e.g. 3 . 200 must not become 3.200).
    return re.sub(r"\s+([.!?])(?=\s|$)", r"\1", whitespace(text))


def content_projection(rep):
    rep.validate()
    assert all(
        c.status == "complete"
        for c in (
            rep.capture_coverage,
            rep.extraction_coverage,
            rep.normalization_coverage,
        )
    ), "partial coverage is not full equivalence"
    assert rep.records, "empty content is not full equivalence"
    return tuple(content_text(r.content) for r in rep.records)


def interpret(side, rules):
    # Only the two existing neutral consumer ports; no format or Golden argument.
    return RuleBasedSemanticInterpreter().interpret(
        {r.source_key: r for r in side.representation.records}, side.evidence, rules
    )


def grounded_projection(side, result):
    """Retain the whole payload; abstract only independently verified references."""
    side.captured.validate()
    side.representation.validate()
    logical = {}
    for key, address in side.evidence.items():
        assert side.adapter.resolve(side.captured, address), "ungrounded evidence"
        assert (
            address.source_key,
            address.source_ref,
            address.snapshot_ref,
            address.record_ref,
            address.raw_content_ref,
        ) == (
            side.captured.record.source_key,
            side.captured.record.source_ref,
            side.captured.snapshot.snapshot_ref,
            side.captured.record.record_ref,
            side.captured.raw_reference.raw_content_ref,
        )
        logical[address.evidence_address_ref] = key
    assert len(logical) == len(side.evidence), "logical evidence must stay distinct"
    payload = result.to_dict()
    for candidate in payload["candidate_payloads"]:
        key = candidate["interpretation_rule_ref"]
        address = side.evidence[key]
        producer = candidate["producer_provenance"]
        assert producer is not None
        assert producer["evidence"] == (
            dict(
                source_key=address.source_key,
                source_ref=address.source_ref,
                snapshot_ref=address.snapshot_ref,
                record_ref=address.record_ref,
                evidence_address_ref=address.evidence_address_ref,
            ),
        ), "claim must ground in its own configured passage"
        producer["evidence"] = ({"logical_evidence_key": key},)
        extraction = producer["extraction"]
        assert extraction["evidence_address_ref"] == address.evidence_address_ref
        match = re.search(extraction["pattern"], address.text)
        assert match is not None
        assert (
            match.group(extraction["capture_group"]).strip()
            == (extraction["extracted_text"])
        )
        extraction["evidence_address_ref"] = key
        extraction["extracted_text"] = whitespace(extraction["extracted_text"])
        assert candidate["evidence_links"], "missing evidence role"
        for link in candidate["evidence_links"]:
            assert link["evidence_address_ref"] == address.evidence_address_ref
            link["evidence_address_ref"] = key
        for gap in candidate["known_gaps"]:
            gap["evidence_address_refs"] = tuple(
                logical[r] for r in gap["evidence_address_refs"]
            )
    for gap in payload["known_gaps"]:
        refs = gap["evidence_address_refs"]
        assert refs and all(logical[r] == gap["interpretation_rule_ref"] for r in refs)
        gap["evidence_address_refs"] = tuple(logical[r] for r in refs)
    # Sorting compares a multiset, not a set: duplicates remain detectable.
    return {
        "candidates": sorted(
            json.dumps(c, sort_keys=True) for c in payload["candidate_payloads"]
        ),
        "gaps": sorted(json.dumps(g, sort_keys=True) for g in payload["known_gaps"]),
    }


def assert_neutral(value):
    if is_dataclass(value):
        assert type(value).__module__ == "cp_knowledge_tools.sources.models"
        for field in fields(value):
            assert_neutral(getattr(value, field.name))
    elif type(value) is tuple:
        for child in value:
            assert_neutral(child)
    else:
        assert type(value) in (str, int, bool, type(None))


def test_cf01_cf03_cf11_contract_roles_and_own_lineage(pair):
    case, _, (html, pdf) = pair
    for side in (html, pdf):
        capture, rep = side.captured, side.representation
        assert type(capture.snapshot) is SourceSnapshot
        assert type(capture.raw_reference) is RawContentReference
        assert type(capture.record) is SourceRecord
        assert type(rep) is NormalizedSourceRepresentation
        assert rep.contract_version == "0.2"
        assert rep.source_records == (capture.record,)
        assert rep.raw_references == (capture.raw_reference,)
        capture.validate()
        rep.validate()
        assert_neutral(rep)
        assert {f.hash_scope for f in rep.fingerprints} == {
            "raw_content",
            "metadata",
            "normalized_content",
            "structure",
        }
        assert rep.extraction_run.stage == "extraction"
        assert rep.normalization_run.stage == "normalization"
        assert rep.extraction_run.output_fingerprint in (
            rep.normalization_run.input_fingerprints
        )
        reverse: dict[str, set[str]] = {}
        for output in (*rep.records, *rep.segments):
            assert type(output) in (NormalizedRecord, StructuredSegment)
            output_ref = (
                output.normalized_record_ref
                if type(output) is NormalizedRecord
                else output.segment_ref
            )
            for mapping in output.inputs:
                assert type(mapping) is SourceMapping
                assert (
                    mapping.source_key,
                    mapping.source_ref,
                    mapping.snapshot_ref,
                    mapping.record_ref,
                    mapping.raw_content_ref,
                ) == (
                    capture.record.source_key,
                    capture.record.source_ref,
                    capture.snapshot.snapshot_ref,
                    capture.record.record_ref,
                    capture.raw_reference.raw_content_ref,
                )
                assert mapping.raw_fingerprint == capture.raw_reference.fingerprint
                assert mapping.stage_ref == rep.normalization_run.run_ref
                reverse.setdefault(mapping.raw_content_ref, set()).add(output_ref)
        assert len(reverse[capture.raw_reference.raw_content_ref]) == (
            len(rep.records) + len(rep.segments)
        )
        assert all(type(a) is EvidenceAddress for a in side.evidence.values())
        for address in side.evidence.values():
            assert_neutral(address)
            assert address.evidence_address_ref not in {
                s.segment_ref for s in rep.segments
            }
    assert {s.structure_type for s in html.representation.segments} != {
        s.structure_type for s in pdf.representation.segments
    }
    if case == "open":
        # N:1 page mappings within one SourceRecord; not cross-document fusion.
        assert len(pdf.representation.records[0].inputs) == 2
    for attr in ("source_key", "source_ref", "snapshot_ref", "record_ref"):
        assert getattr(html.captured.record, attr) != getattr(pdf.captured.record, attr)
    assert html.captured.raw_reference != pdf.captured.raw_reference
    assert (
        html.representation.representation_ref != pdf.representation.representation_ref
    )


def test_cf04_cf06_equivalent_content_and_complete_candidates(pair):
    case, rules, sides = pair
    results = [interpret(side, rules) for side in sides]
    assert content_projection(sides[0].representation) == content_projection(
        sides[1].representation
    )
    assert grounded_projection(sides[0], results[0]) == grounded_projection(
        sides[1], results[1]
    )
    # Expectations are opened only after product outputs exist.
    oracle = json.loads(GOLDEN.read_text())
    assert oracle["scenario_role"] == "adapter_conformance"
    expected = oracle[case]
    for result in results:
        assert len(result.candidate_payloads) == expected["candidate_count"]
        assert len(result.known_gaps) == expected["gap_count"]
        assert {
            c.interpretation_rule_ref: c.proposed_claim.value
            for c in result.candidate_payloads
        } == expected["claim_values"]
        for candidate in result.candidate_payloads:
            assert (
                candidate.candidate_payload_kind
                == "implementation_local.proposed_claim"
            )
            assert candidate.proposed_claim.subject_entity_key == "pilot"
            assert candidate.proposed_claim.predicate_ref == (
                f"example.{candidate.interpretation_rule_ref}"
            )
            assert candidate.epistemic_context.status == "reported"
            assert tuple(link.role for link in candidate.evidence_links) == (
                "reports_statement",
            )
            assert not candidate.known_gaps and not candidate.known_conflicts


def test_cf07_cf08_distinct_reproducible_evidence_and_selector_fail_closed(pair):
    _, _, (html, pdf) = pair
    for key in html.evidence:
        left, right = html.evidence[key], pdf.evidence[key]
        assert left.evidence_address_ref != right.evidence_address_ref
        assert left.selector != right.selector
        for side, address, other in ((html, left, right), (pdf, right, left)):
            restored = evidence_address_from_dict(
                json.loads(json.dumps(asdict(address)))
            )
            assert restored == address and side.adapter.resolve(side.captured, restored)
            assert not side.adapter.resolve(side.captured, other)
            for changed in (
                replace(address, selector=other.selector),
                replace(
                    address, selector=replace(address.selector, selector_version="999")
                ),
                replace(
                    address, selector=replace(address.selector, selector_type="unknown")
                ),
                replace(address, text=address.text + " invented assertion"),
                replace(address, content_hash="0" * 64),
                replace(address, evidence_address_ref=other.evidence_address_ref),
                replace(address, snapshot_ref=other.snapshot_ref),
            ):
                assert not side.adapter.resolve(side.captured, changed)


def decision_for(side, address, *, effect="permit", metadata=False):
    subjects = (
        PolicySubject(
            "evidence_address", address.evidence_address_ref, "1", "Source and Evidence"
        ),
        PolicySubject(
            "source_snapshot", address.snapshot_ref, "1", "Source and Evidence"
        ),
    )
    operations = ("resolve_evidence", "read_metadata" if metadata else "read_content")
    anchors = side.captured.snapshot.policy_refs
    evaluation = PolicyEvaluationInput(
        policy_evaluation_ref="PEVAL-WI017",
        actor_or_consumer_ref=CONSUMER,
        purpose=PURPOSE,
        requested_operation=None,
        subject_refs=subjects,
        policy_config_ref=f"{POLICY}@1",
        processing_zone="local_synthetic_test",
        profile_refs=(),
        profile_applicability=ProfileApplicability("resolved"),
        policy_anchor_ids=anchors,
        requested_at=NOW,
        context_valid_at=NOW,
        requested_action="resolve_evidence",
        requested_data_operations=operations,
        requested_effect_scope=SCOPE,
    )
    config = PolicyConfiguration(
        policy_ref=POLICY,
        version="1",
        status="active",
        rules=tuple(
            PolicyRule(
                policy_rule_ref=f"SYNTHETIC-WI017-{index}",
                actor_or_consumer_ref=CONSUMER,
                purpose=PURPOSE,
                requested_operation=None,
                requested_action="resolve_evidence",
                requested_data_operations=operations,
                subject_ref=subject,
                required_policy_anchor_ids=anchors,
                effect=effect,
                reason=f"synthetic_exact_subject_{effect}",
                authorized_scope=SCOPE,
            )
            for index, subject in enumerate(subjects)
        ),
        decision_authority_ref="SYNTHETIC-TEST-POLICY-OWNER",
        valid_from="2026-08-31T09:00:00+02:00",
        valid_until="2026-08-31T11:00:00+02:00",
        synthetic_test_fixture=True,
    )
    return dict(
        evaluation=evaluation, decision=PolicyEvaluator().evaluate(evaluation, config)
    )


def resolve_content(side, address, grant=None, **kwargs):
    request = dict(consumer_ref=CONSUMER, purpose=PURPOSE)
    request.update(kwargs)
    return side.adapter.resolve_content(
        side.captured, address, **request, **(grant or {})
    )


def assert_denied(result):
    assert asdict(result) == dict(
        status="not_authorized", content=None, diagnostic_code=None
    )


def test_cf09_policy_equivalence_exact_subjects_and_no_leak(pair, monkeypatch):
    _, _, sides = pair
    for side, other in (sides, sides[::-1]):
        for key, address in side.evidence.items():
            assert side.captured.snapshot.policy_refs == address.policy_refs
            assert side.representation.records[0].policy_refs == address.policy_refs
            permit = decision_for(side, address)
            assert permit["decision"].result == "permit"
            result = resolve_content(side, address, permit)
            assert result.status == "resolved" and result.content == address.text
            metadata = decision_for(side, address, metadata=True)
            result = resolve_content(side, address, metadata, mode="metadata_only")
            assert result.status == "resolved" and result.content is None
            assert_denied(resolve_content(side, address, metadata))
            deny = decision_for(side, address, effect="deny")
            assert deny["decision"].result == "deny"
            with monkeypatch.context() as patch:

                def forbidden(*args, **kwargs):
                    pytest.fail("denied caller reached source inspection")

                patch.setattr(side.adapter, "resolve", forbidden)
                assert_denied(resolve_content(side, address, deny))
                assert_denied(resolve_content(side, address))
                assert_denied(
                    resolve_content(side, address, permit, consumer_ref="stranger")
                )
                assert_denied(resolve_content(side, address, permit, purpose="publish"))
                assert_denied(
                    resolve_content(
                        side, address, decision_for(other, other.evidence[key])
                    )
                )


@pytest.mark.parametrize(
    "closed_factory,open_factory",
    (
        (LocalPdfAdapter, LocalHtmlAdapter),
        (LocalHtmlAdapter, LocalPdfAdapter),
    ),
)
def test_restricted_source_is_not_unlocked_by_open_equivalent(
    closed_factory, open_factory
):
    rules = rules_for("restricted")
    closed = prepare(
        closed_factory(),
        INPUTS
        / (
            "restricted.pdf" if closed_factory is LocalPdfAdapter else "restricted.html"
        ),
        "closed-source",
        rules,
        "PA-WI017-RESTRICTED",
    )
    opened = prepare(
        open_factory(),
        INPUTS
        / ("restricted.pdf" if open_factory is LocalPdfAdapter else "restricted.html"),
        "open-copy",
        rules,
        "PA-WI017-OPEN",
    )
    assert grounded_projection(closed, interpret(closed, rules)) == grounded_projection(
        opened, interpret(opened, rules)
    )
    grant = decision_for(opened, opened.evidence["budget"])
    assert resolve_content(opened, opened.evidence["budget"], grant).content is not None
    assert_denied(resolve_content(closed, closed.evidence["budget"], grant))
    assert_denied(resolve_content(closed, closed.evidence["budget"]))


def test_cf02_native_objects_rejected_at_neutral_boundary(pair):
    _, _, sides = pair
    with pdfplumber.open(INPUTS / "open.pdf") as document:
        for native in (
            BeautifulSoup("<p>Native</p>", "html.parser").p,
            document.pages[0],
        ):
            for side in sides:
                for output in (
                    side.representation.records[0],
                    side.representation.segments[0],
                ):
                    with pytest.raises(ValueError, match="source-neutral"):
                        replace(output, content=native)


def test_cf05_cf08_consumer_never_reads_selector_or_parser_metadata(pair, monkeypatch):
    _, rules, sides = pair
    original = EvidenceAddress.__getattribute__

    def guard(self, name):
        assert name not in {"selector", "parser_tool_ref", "resolution_rule_ref"}, (
            "native address routing in semantic consumer"
        )
        return original(self, name)

    expected = [interpret(side, rules) for side in sides]
    with monkeypatch.context() as patch:
        patch.setattr(EvidenceAddress, "__getattribute__", guard)
        results = [interpret(side, rules) for side in sides]
    assert results == expected


def assert_no_format_routing(source):
    # Bounded structural guard for the actual selected consumer and extractor.
    # It complements dynamic tests; it is not proof about every possible alias.
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
            assert not any(
                re.search(r"html|pdf|bs4|sources\.adapters", n) for n in names
            )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not re.search(
                r"\b(?:html|pdf|pdfplumber|pdfminer|BeautifulSoup)\b", node.value
            ), "format routing in semantic consumer"
        if isinstance(node, ast.Attribute):
            assert node.attr not in {
                "selector",
                "parser_tool_ref",
                "resolution_rule_ref",
            }


def test_cf05_no_format_routing_in_selected_consumer():
    source = TESTS.parent / "src/cp_knowledge_tools/semantics"
    for name in ("rule_interpreter.py", "extraction.py"):
        assert_no_format_routing((source / name).read_text())
    with pytest.raises(AssertionError):
        assert_no_format_routing('if source_format == "pdf": value = 17')


def test_cf10_structure_and_partial_diagnostics_are_not_semantic_claims(pair, tmp_path):
    _, _, sides = pair
    for side in sides:
        assert not interpret(side, {}).candidate_payloads
    path = tmp_path / "image-and-text.pdf"
    path.write_bytes(digital_pdf(("The pilot is limited to 16 students.",), image=True))
    rules = rules_for("restricted")
    rules["claims"] = rules_for("open")["claims"][:1]
    partial = prepare(LocalPdfAdapter(), path, "partial", rules, "PA-WI017-OPEN")
    assert partial.representation.extraction_coverage.status == "partial_expected"
    assert partial.representation.diagnostics
    assert partial.representation.extraction_coverage.diagnostic_refs
    with pytest.raises(AssertionError, match="partial coverage"):
        content_projection(partial.representation)
    assert not interpret(partial, {}).candidate_payloads
    result = interpret(partial, rules)
    assert len(result.candidate_payloads) == 1
    assert result.candidate_payloads[0].proposed_claim.value == 16


def test_cf12_independent_storage_and_rebuild(pair, tmp_path):
    _, rules, sides = pair
    store = SourceStore(tmp_path / "state")
    for side in sides:
        store.put_capture(side.captured)
        store.put_representation(side.representation)
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    for side in sides:
        captured = store.load_capture(side.captured.snapshot.snapshot_ref)
        rep = store.load_representation(side.representation.representation_ref)
        fresh = type(side.adapter)()
        rebuilt = fresh.rebuild(captured, rep)
        assert rebuilt == side.representation
        store.put_capture(captured)
        store.put_representation(rebuilt)
        restored = Side(
            fresh,
            captured,
            rebuilt,
            {
                key: evidence_address_from_dict(json.loads(json.dumps(asdict(address))))
                for key, address in side.evidence.items()
            },
        )
        assert grounded_projection(restored, interpret(restored, rules)) == (
            grounded_projection(side, interpret(side, rules))
        )
        assert {
            p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()
        } == before


@pytest.mark.parametrize("change", ("extra", "missing", "value", "duplicate"))
def test_projection_detects_information_changes(change, tmp_path):
    rules = rules_for("restricted")
    side = prepare(
        LocalPdfAdapter(),
        INPUTS / "restricted.pdf",
        "original",
        rules,
        "PA-WI017-RESTRICTED",
    )
    text = side.representation.records[0].content
    changed = {
        "extra": text + " Additional approval is still pending.",
        "missing": text.split("A public-facing")[0],
        "value": text.replace("3,200", "3,300"),
        "duplicate": text + " " + text,
    }[change]
    path = tmp_path / "changed.html"
    path.write_text(f"<p>{changed}</p>")
    other = prepare(LocalHtmlAdapter(), path, "changed", rules, "PA-WI017-RESTRICTED")
    assert content_projection(side.representation) != content_projection(
        other.representation
    )
    left = grounded_projection(side, interpret(side, rules))
    right = grounded_projection(other, interpret(other, rules))
    if change == "value":
        assert left != right
    else:
        # Candidate-only comparison would miss unextracted material information.
        assert left == right


def test_projection_preserves_candidate_multiplicity_roles_and_grounding(pair):
    _, rules, sides = pair
    side, other = sides
    result = interpret(side, rules)
    first = result.candidate_payloads[0]
    baseline = grounded_projection(side, result)
    duplicate = replace(result, candidate_payloads=(*result.candidate_payloads, first))
    assert grounded_projection(side, duplicate) != baseline
    for changed in (
        replace(
            first,
            evidence_links=(replace(first.evidence_links[0], role="contradicts"),),
        ),
        replace(first, known_conflicts=("unresolved-conflict",)),
        replace(
            first,
            epistemic_context=replace(first.epistemic_context, status="uncertain"),
        ),
    ):
        altered = replace(
            result, candidate_payloads=(changed, *result.candidate_payloads[1:])
        )
        assert grounded_projection(side, altered) != baseline
    # Do not let comparison manufacture or silently rebind evidence.
    forged = replace(
        first,
        evidence_links=(
            replace(
                first.evidence_links[0],
                evidence_address_ref=next(
                    iter(other.evidence.values())
                ).evidence_address_ref,
            ),
        ),
    )
    with pytest.raises(AssertionError):
        grounded_projection(side, replace(result, candidate_payloads=(forged,)))


def test_missing_and_ambiguous_passages_fail_instead_of_empty_equality(tmp_path):
    rules = rules_for("restricted")
    for html, message in (
        ("<p>No amount was provided.</p>", "missing grounded"),
        (
            "<p>cost ceiling of EUR 3,200</p><p>cost ceiling of EUR 3,200</p>",
            "ambiguous",
        ),
    ):
        path = tmp_path / "input.html"
        path.write_text(html)
        with pytest.raises(AssertionError, match=message):
            prepare(LocalHtmlAdapter(), path, "input", rules, "PA-WI017-OPEN")


def test_known_gaps_remain_visible_and_grounded(pair):
    _, rules, sides = pair
    rules["claims"][0]["extraction"]["pattern"] = r"not present (?P<value>\d+)"
    results = [interpret(side, rules) for side in sides]
    assert all(
        result.known_gaps[0].gap_code == "extraction_no_match" for result in results
    )
    assert grounded_projection(sides[0], results[0]) == grounded_projection(
        sides[1], results[1]
    )
    assert len(results[0].candidate_payloads) == len(rules["claims"]) - 1


def test_golden_read_guard_and_literal_runtime_input_rejected(monkeypatch):
    original_open, original_io = builtins.open, io.open

    def guarded(opener):
        def checked(path, *args, **kwargs):
            if isinstance(path, (str, Path)):
                assert not Path(path).resolve().is_relative_to(TESTS / "golden"), (
                    "Golden is an oracle, not runtime input"
                )
            return opener(path, *args, **kwargs)

        return checked

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", guarded(original_open))
        patch.setattr(io, "open", guarded(original_io))
        with pytest.raises(AssertionError, match="Golden"):
            GOLDEN.read_text()
        for case in ("open", "restricted"):
            for suffix, factory in (
                ("html", LocalHtmlAdapter),
                ("pdf", LocalPdfAdapter),
            ):
                rules = rules_for(case)
                side = prepare(
                    factory(),
                    INPUTS / f"{case}.{suffix}",
                    f"{case}-{suffix}",
                    rules,
                    "PA-WI017-TEST",
                )
                assert interpret(side, rules).candidate_payloads
                # A literal expected claim cannot substitute for extraction.
                del rules["claims"][0]["extraction"]
                rules["claims"][0]["value"] = 999999
                with pytest.raises(ValueError, match="lacks extraction"):
                    interpret(side, rules)
