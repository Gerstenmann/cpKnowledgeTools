from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from cp_knowledge_tools.semantics.hardening import (
    AtomicClaimLink,
    CompatibilityChecks,
    ConflictCompatibilityAssessment,
    EvidenceAssessment,
    EvidenceDimensions,
    ProgramOccurrenceRelationship,
    RationaleRelationship,
    TemporalConstraint,
    integrate_cumulative_knowledge_state,
)

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / (
    "tests/fixtures/source_to_knowledge/minecraft_esports/"
    "hardening/semantic_cases.v0.1.json"
)


def _cases() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def test_sf01_atomic_claim_link_preserves_both_identities() -> None:
    link = AtomicClaimLink(
        relationship_ref="REL-QUALIFICATION-01",
        source_claim_ref="CLM-TECHNICAL-SCOPE",
        target_claim_ref="CLM-TECHNICAL-RELIABILITY",
        predicate="qualifies",
    )

    assert link.claim_refs == (
        "CLM-TECHNICAL-SCOPE",
        "CLM-TECHNICAL-RELIABILITY",
    )
    assert link.to_dict()["predicate"] == "qualifies"
    with pytest.raises(ValueError, match="distinct"):
        AtomicClaimLink("REL-BAD", "CLM-A", "CLM-A", "qualifies")


def test_sf02_rationale_is_evidentiable_and_never_implicit_causality() -> None:
    fixture = _cases()["rationale"]
    relationship = RationaleRelationship(
        relationship_ref="REL-RATIONALE-01",
        reason_claim_ref=fixture["reason_claim_ref"],
        target_ref=fixture["target_ref"],
        evidence_link_ids=tuple(fixture["evidence_link_ids"]),
        profile_ref=fixture["profile_ref"],
    )

    assert relationship.predicate == "rationale_for"
    assert relationship.causality_asserted is False
    with pytest.raises(ValueError, match="Evidence"):
        RationaleRelationship(
            "REL-BAD",
            "CLM-REASON",
            "CLM-TARGET",
            (),
            "cpks.profile.organizational-context@0.3",
        )


def test_sf03_program_and_occurrence_are_related_but_distinct() -> None:
    fixture = _cases()["program_occurrence"]
    relationship = ProgramOccurrenceRelationship(
        relationship_ref="REL-PROGRAM-OCCURRENCE-01",
        program_ref=fixture["program_ref"],
        occurrence_ref=fixture["occurrence_ref"],
        predicate=fixture["relationship"],
    )

    assert relationship.program_ref != relationship.occurrence_ref
    with pytest.raises(ValueError, match="distinct"):
        ProgramOccurrenceRelationship("REL-BAD", "SAME", "SAME", "part_of")


def test_sf05_evidence_assessment_is_claim_purpose_and_dimension_bound() -> None:
    dimensions = EvidenceDimensions(
        independence="shared_origin",
        directness="direct_statement",
        source_role="formal_confirmation",
        formality="formal",
        competence="domain_competent",
        claim_authority="authorized_for_claim",
        specificity="claim_specific",
        temporal_proximity="near_event",
        perspective="institutional_decision",
    )
    assessment = EvidenceAssessment(
        assessment_ref="EA-SECOND-CYCLE-01",
        claim_ref="CLM-SECOND-CYCLE-APPROVED",
        purpose="publication_validation",
        evidence_link_ids=("EL-DOC05-APPROVAL", "EL-DOC07-APPROVAL"),
        dimensions=dimensions,
        method="explicit_origin_comparison",
        assessed_by="validator:test",
        assessed_at="2026-08-20T10:00:00+02:00",
        uncertainty="shared origin confirmed by fixture lineage",
    )

    payload = assessment.to_dict()
    assert payload["dimensions"]["independence"] == "shared_origin"
    assert "global_score" not in payload
    with pytest.raises(ValueError, match="independence"):
        EvidenceDimensions(
            independence="two_sources",
            directness="direct",
            source_role="observer",
            formality="informal",
            competence="unknown",
            claim_authority="unknown",
            specificity="specific",
            temporal_proximity="unknown",
            perspective="observer",
        )


def test_sf06_temporal_constraint_preserves_unknown_time_and_hard_bounds() -> None:
    fixture = _cases()["temporal_constraint"]
    constraint = TemporalConstraint.from_mapping(fixture)

    assert constraint.certainty == "deterministic"
    assert constraint.lower_bound == "2024-10-01"
    assert constraint.upper_bound == "2024-12-18"
    with pytest.raises(ValueError, match="probabilistic"):
        TemporalConstraint.from_mapping(
            {**fixture, "derivation_kind": "probabilistic_inference"}
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"bound_kind": "closed_interval"}, "bound_kind"),
        ({"bound_kind": "unknown"}, "bound_kind"),
        ({"bound_kind": "lower", "lower_bound": None}, "lower_bound"),
        ({"bound_kind": "upper", "upper_bound": None}, "upper_bound"),
        (
            {"bound_kind": "interval", "lower_bound": None, "upper_bound": None},
            "hard bound",
        ),
    ],
)
def test_temporal_constraint_bound_kind_fails_closed(
    changes: dict[str, object], message: str
) -> None:
    fixture = {**_cases()["temporal_constraint"], "bound_kind": "interval"}

    with pytest.raises(ValueError, match=message):
        TemporalConstraint.from_mapping({**fixture, **changes})


def test_interval_accepts_one_boundary_under_active_contract_rule() -> None:
    fixture = {
        **_cases()["temporal_constraint"],
        "bound_kind": "interval",
        "upper_bound": None,
    }

    constraint = TemporalConstraint.from_mapping(fixture)

    assert constraint.lower_bound == "2024-10-01"
    assert constraint.upper_bound is None


def test_sf07_hard_conflict_requires_all_compatibility_checks() -> None:
    compatible = ConflictCompatibilityAssessment(
        assessment_ref="CCA-DOC04-DOC08",
        claim_refs=("CLM-DOC04-TECHNICAL", "CLM-DOC08-TECHNICAL"),
        checks=CompatibilityChecks.all_checked(),
        remaining_material_incompatibility=False,
        outcome="qualification_or_compatible_difference",
    )

    assert compatible.outcome == "qualification_or_compatible_difference"
    with pytest.raises(ValueError, match="compatibility checks"):
        ConflictCompatibilityAssessment(
            assessment_ref="CCA-BAD",
            claim_refs=("CLM-A", "CLM-B"),
            checks=CompatibilityChecks(
                time=True,
                context=True,
                perspective=False,
                observation_granularity=True,
                qualification=True,
            ),
            remaining_material_incompatibility=True,
            outcome="hard_conflict",
        )


def test_d9_cumulative_integration_preserves_state_and_separate_evidence() -> None:
    baseline = {
        "entities": [{"entity_ref": "ENT-PROGRAM", "name": "Synthetic Program"}],
        "claims": [{"claim_ref": "CLM-APPROVED", "value": True}],
        "events": [{"event_ref": "EVT-DECISION", "event_type": "decision"}],
        "relationships": [{"relationship_ref": "REL-PART", "predicate": "part_of"}],
        "evidence_links": [
            {"evidence_link_id": "EL-BASE", "claim_ref": "CLM-APPROVED"}
        ],
    }
    increment = {
        "entities": [],
        "claims": [deepcopy(baseline["claims"][0])],
        "events": [],
        "relationships": [],
        "evidence_links": [
            {"evidence_link_id": "EL-ADDITIONAL", "claim_ref": "CLM-APPROVED"}
        ],
    }

    integrated = integrate_cumulative_knowledge_state(baseline, increment)

    assert integrated["entities"] == baseline["entities"]
    assert integrated["events"] == baseline["events"]
    assert integrated["relationships"] == baseline["relationships"]
    assert [item["evidence_link_id"] for item in integrated["evidence_links"]] == [
        "EL-BASE",
        "EL-ADDITIONAL",
    ]
    assert baseline["evidence_links"] == [
        {"evidence_link_id": "EL-BASE", "claim_ref": "CLM-APPROVED"}
    ]
