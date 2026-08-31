"""Preparation GREEN means contracts/boundaries, never LLM generation GREEN."""

from __future__ import annotations

import builtins
import io
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from cp_knowledge_tools.lifecycle.resolution import (
    LifecycleCandidateRegistrar,
    SameObjectAssessmentRequest,
    SameObjectEvaluator,
)
from cp_knowledge_tools.semantics import (
    ChangeCandidatePipeline,
    ChangeCandidateRequest,
    EvidenceAssessment,
    EvidenceDimensions,
    FindingInput,
    KnownGap,
    MaterialDeltaFindingEvaluator,
    PriorKnowledgeState,
    SemanticChangeOperationPolicy,
    SemanticChangeProposal,
    SemanticInterpretationResult,
    SemanticState,
    SemanticTarget,
)
from cp_knowledge_tools.sources.adapters.local_html import LocalHtmlAdapter
from tests.frontier import workshop_baseline as harness
from tests.frontier.workshop_oracle import assert_vector, expected, vector


@pytest.fixture
def passages() -> dict[str, harness.Passage]:
    return harness.prepare_inputs()


@pytest.mark.parametrize("key", [c["key"] for c in expected()["candidates"]])
def test_existing_candidate_contract_represents_authored_vectors(
    passages: dict[str, harness.Passage], key: str
) -> None:
    spec = next(c for c in expected()["candidates"] if c["key"] == key)
    payload = vector(spec, passages)
    assert_vector(payload.to_dict(), spec, passages)
    assert (
        not {"canonical_id", "publication_state", "policy_decision"}
        & asdict(payload).keys()
    )


def test_unknowns_perspective_qualification_and_bounds(
    passages: dict[str, harness.Passage],
) -> None:
    golden = expected()
    gaps = tuple(
        KnownGap(
            g["key"],
            "WI018-ASSERTION-ONLY",
            g["expected"],
            tuple(passages[e].address.evidence_address_ref for e in g["evidence"]),
        )
        for g in golden["gaps"]
    )
    abstention = SemanticInterpretationResult((), gaps).to_dict()
    assert abstention["candidate_payloads"] == ()
    assert len(abstention["known_gaps"]) == 4
    assert all(g["evidence_address_refs"] for g in abstention["known_gaps"])
    # Perspective has a separate existing Evidence contract, not a new payload field.
    perspective_spec = next(
        c for c in golden["candidates"] if c["key"] == "usable-perspective"
    )
    perspective_vector = vector(perspective_spec, passages)
    assert_vector(perspective_vector.to_dict(), perspective_spec, passages)
    link = perspective_vector.evidence_links[0]
    assert (
        link.evidence_address_ref
        == passages["handover-de:p3"].address.evidence_address_ref
    )
    assert link.evidence_link_key != link.evidence_address_ref
    assessment = EvidenceAssessment(
        assessment_ref="TEST-EA-USABILITY",
        claim_ref="usable-perspective",
        purpose="synthetic_frontier_review",
        evidence_link_ids=(link.evidence_link_key,),
        dimensions=EvidenceDimensions(
            independence="unknown",
            directness="documented_statement",
            source_role="workshop_lead_note",
            formality="unsigned_note",
            competence="not_established",
            claim_authority="not_release_authority",
            specificity="TW-42",
            temporal_proximity="not_established",
            perspective=golden["perspective"]["perspective"],
        ),
        method="assertion_only_contract_vector",
        assessed_by="WI018-test",
        assessed_at=harness.NOW,
        uncertainty="signed release not evidenced",
    ).to_dict()
    assert assessment["dimensions"]["perspective"] == "workshop_lead"
    assert assessment["evidence_link_ids"] == [link.evidence_link_key]
    assert "global_score" not in assessment
    scenario = json.loads((harness.INPUTS / "scenario.v1.json").read_text())
    bounds = scenario["bounds"]
    assert len(golden["candidates"]) == 16 <= bounds["candidate_payloads_max"] == 24
    assert len(golden["identity_questions"]) == bounds["identity_questions_max"] == 3
    assert len(gaps) == bounds["known_gaps_max"]
    assert bounds["planned_stochastic_repetitions_per_frozen_configuration"] == 5
    assert {s["language"] for s in scenario["sources"]} == {"de", "en"}
    assert len(golden["negatives"]) == 13


def change_evaluation(
    passage: harness.Passage, proposal: SemanticChangeProposal
) -> Any:
    # Authored reading exercises downstream boundaries; no semantic extraction claim.
    read = harness.resolve_local(passage.captured, passage.address)
    payload = {"predicate": "vendor_identity", "value": "unresolved"}
    finding = (
        MaterialDeltaFindingEvaluator()
        .evaluate(
            FindingInput(
                task_ref="WI018-TEST",
                source_result_ref=passage.address.evidence_address_ref,
                source_ref=passage.address.source_ref,
                subject_refs=("test-vendor-question",),
                prior_state_ref="TEST-EMPTY-PRIOR",
                prior_state=SemanticState(None),
                observed_state=SemanticState(
                    payload,
                    (passage.address.evidence_address_ref,),
                    epistemic_state="reported",
                ),
                description="authored assertion vector: vendor identity unresolved",
                delta_class=("new_information",),
                evidence_content_read=read is not None,
                content_read_authorized=read is not None,
                evidence_resolvable=LocalHtmlAdapter().resolve(
                    passage.captured, passage.address
                ),
                semantic_assertion=True,
                producer_ref="WI018-ASSERTION-ONLY",
            )
        )
        .finding
    )
    assert finding is not None
    return ChangeCandidatePipeline(
        SemanticChangeOperationPolicy.from_allowed(
            ("add",), policy_ref="SYNTHETIC-WI018-OPERATION-POLICY"
        )
    ).evaluate(
        ChangeCandidateRequest(
            findings=(finding,),
            semantic_target=SemanticTarget("claim", ("test-question",)),
            prior_state=PriorKnowledgeState(
                ("TEST-EMPTY-PRIOR",), "no prior test assertion"
            ),
            proposals=(proposal,),
            producer_ref="WI018-ASSERTION-ONLY",
        )
    )


def identity_proposal() -> SemanticChangeProposal:
    return SemanticChangeProposal(
        "add",
        "retain identity question",
        {"predicate": "vendor_identity", "value": "unresolved"},
        unresolved_identity_questions=("vendor-de may be vendor-en; not confirmed",),
    )


def test_open_identity_survives_registration_without_same_object_resolution(
    passages: dict[str, harness.Passage],
) -> None:
    result = change_evaluation(passages["clarification-de:p2"], identity_proposal())
    assert len(result.candidates) == 1
    change = result.candidates[0]
    assert change.non_canonical and change.requires_review
    assert (
        change.unresolved_identity_questions
        == identity_proposal().unresolved_identity_questions
    )
    candidate = LifecycleCandidateRegistrar().register(
        change,
        registered_by="WI018-test",
        registered_at=harness.NOW,
        rule_basis_refs=("CPKS-SPEC-KPR",),
        idempotency_key="WI018-TEST-REGISTRATION",
    )
    assessment = SameObjectEvaluator().evaluate(
        SameObjectAssessmentRequest(
            candidate_revision=candidate,
            prior_snapshot=None,
            proposed_snapshot=None,
            existing_canonical_refs=(),
            prior_identity_evidence_refs=change.evidence_refs,
            assessed_dimensions=(),
            material_delta_dimensions=("identity_question",),
            rationale="No identity authority is supplied by a language alias",
            rule_basis_refs=("CPKS-SPEC-KM",),
            unresolved_identity_questions=change.unresolved_identity_questions,
        )
    )
    assert candidate.non_canonical and assessment.result == "ambiguous_or_unresolved"


@pytest.mark.parametrize("decision", ["merge vendor-de vendor-en", "merge tw42 tw24"])
def test_n04_n05_actual_pipeline_blocks_preempted_identity(
    passages: dict[str, harness.Passage],
    decision: str,
) -> None:
    proposal = replace(identity_proposal(), identity_decisions=(decision,))
    result = change_evaluation(passages["clarification-de:p2"], proposal)
    assert result.disposition == "blocked"
    assert result.reason_code == "same_object_or_identity_resolution_preempted"


def test_n11_actual_pipeline_blocks_lifecycle_bypass(
    passages: dict[str, harness.Passage],
) -> None:
    proposal = replace(identity_proposal(), foreign_authority_outputs=("published",))
    result = change_evaluation(passages["clarification-de:p2"], proposal)
    assert result.disposition == "blocked"
    assert result.reason_code == "foreign_authority_output_preempted"


@pytest.mark.parametrize(
    "case", ["N01", "N02", "N03", "N06", "N07", "N08", "N09", "N10", "N12"]
)
def test_assertion_oracle_rejects_concrete_negative_vectors(
    passages: dict[str, harness.Passage],
    case: str,
) -> None:
    # These are oracle self-checks, not evidence of product entailment validation.
    spec = next(c for c in expected()["candidates"] if c["key"] == "returned")
    payload = vector(spec, passages).to_dict()
    if case == "N01":
        payload["evidence_links"] = ()
    elif case == "N02":
        payload["evidence_links"][0]["evidence_address_ref"] = "EVA-INVENTED"
    elif case == "N03":
        payload["producer_provenance"]["evidence"][0]["source_ref"] = "SRC-INVENTED"
    elif case == "N06":
        payload["proposed_claim"].update(predicate_ref="example.owned_by", value="Mara")
    elif case == "N07":
        payload["proposed_claim"].update(predicate_ref="example.caused", value="check")
    elif case == "N08":
        payload["proposed_claim"].update(
            predicate_ref="example.check_price_eur", value=120
        )
    elif case == "N09":
        payload["evidence_links"] = ()
        payload["model_confidence"] = 0.99
    elif case == "N10":
        payload["canonical_id"] = "KO-FAKE"
    elif case == "N12":
        payload["proposed_claim"].update(
            predicate_ref="html.parent_owns_child", value=True
        )
    with pytest.raises(AssertionError):
        assert_vector(payload, spec, passages)


def test_actual_source_boundary_rejects_forged_address_lineage_and_denied_read(
    passages: dict[str, harness.Passage],
) -> None:
    p = passages["handover-de:p1"]
    for address in (
        replace(p.address, evidence_address_ref="EVA-INVENTED"),
        replace(p.address, source_ref="SRC-INVENTED"),
        replace(p.address, snapshot_ref="SNAP-INVENTED"),
    ):
        assert not LocalHtmlAdapter().resolve(p.captured, address)
        assert harness.resolve_local(p.captured, address) is None
    assert harness.resolve_local(p.captured, p.address, effect="deny") is None


def test_oracle_detects_changed_source_despite_valid_new_evidence(
    passages: dict[str, harness.Passage],
    tmp_path: Path,
) -> None:
    path = tmp_path / "altered.html"
    path.write_text("<article><p>TW-42 was not returned.</p></article>")
    adapter = LocalHtmlAdapter()
    capture = adapter.capture(
        "handover-de", path, captured_at=harness.NOW, policy_refs=(harness.ANCHOR,)
    )
    segment = next(
        s for s in adapter.normalize(capture).segments if s.segment_type == "paragraph"
    )
    address = adapter.evidence_address_for_segment(capture, segment)
    altered = {
        **passages,
        "handover-de:p1": harness.Passage(capture, address, segment.content),
    }
    assert harness.resolve_local(capture, address) == segment.content
    spec = next(c for c in expected()["candidates"] if c["key"] == "returned")
    with pytest.raises(AssertionError, match="Scenario source changed"):
        assert_vector(vector(spec, altered).to_dict(), spec, altered)


def test_n13_capture_normalization_and_inventory_cannot_read_golden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[Path] = []

    def guard(original: Any) -> Any:
        def read(file: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(file, (str, Path)):
                path = Path(file).resolve()
                assert "golden" not in path.parts, (
                    "Expected leaked into input processing"
                )
                opened.append(path)
            return original(file, *args, **kwargs)

        return read

    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(io, "open", guard(io.open))
    passages = harness.prepare_inputs()
    harness.product_inventory()
    assert len(passages) == 9
    assert set(harness.INPUTS.glob("*.html")) <= set(opened)


def test_baseline_distinguishes_missing_producer_from_success_and_stale_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exercise the reporting branches against their historical inspection input.
    # Product evolution must not require rewriting authored WI-018 audit evidence
    # or reasserting its missing-capability finding about current product bytes.
    inspected = harness.product_inventory()
    audited_hash = json.loads(harness.AUDIT.read_text())["product_tree_sha256"]
    monkeypatch.setattr(
        harness,
        "product_inventory",
        lambda: {**inspected, "product_tree_sha256": audited_hash},
    )
    report = harness.baseline()
    assert report["source_boundary_status"] == "green"
    assert report["generation_status"] == "not_executed_missing_capability"
    assert report["external_requests"] == 0 and report["generated_candidates"] == []
    assert "RuleBasedSemanticInterpreter" in report["inventory"]["semantic_exports"]
    actual_inventory = report["inventory"]
    monkeypatch.setattr(
        harness,
        "product_inventory",
        lambda: {**actual_inventory, "product_tree_sha256": "changed-product-bytes"},
    )
    assert harness.baseline()["generation_status"] == "requires_reinspection"


@pytest.mark.parametrize("location", ["scenario", "source", "bounds", "processing"])
def test_n13_manifest_rejects_embedded_expected_payload(
    tmp_path: Path,
    location: str,
) -> None:
    scenario = json.loads((harness.INPUTS / "scenario.v1.json").read_text())
    targets = {
        "scenario": scenario,
        "source": scenario["sources"][0],
        "bounds": scenario["bounds"],
        "processing": scenario["processing"],
    }
    target = targets[location]
    target["expected"] = {"candidate": "a leaked Golden answer"}
    (tmp_path / "scenario.v1.json").write_text(json.dumps(scenario))
    with pytest.raises(AssertionError, match="Unexpected .* input field"):
        harness.prepare_inputs(tmp_path)
