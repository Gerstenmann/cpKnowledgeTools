from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cp_knowledge_tools.delivery.continuation import (
    CandidateScope,
    ContinuationBudget,
    ContinuationRequest,
    PolicyContext,
    derive_lesson_learned_required_gap_refs,
)


def test_continuation_request_preserves_bounded_context() -> None:
    request = ContinuationRequest(
        continuation_request_ref="CREQ-TEST",
        consumer_ref="consumer-test",
        purpose="similar_experience_retrieval",
        experience_ref="EXP-TEST",
        continuation_requirement_ref="CONT-TEST",
        gap_refs=("GAP-1", "GAP-2"),
        lesson_learned_required_gap_refs=("GAP-1",),
        search_after="2024-09-06T15:30:00+02:00",
        candidate_scope=CandidateScope(
            scope_ref="SCOPE-TEST",
            allowed_source_refs=("SOURCE-A", "SOURCE-B"),
        ),
        budget=ContinuationBudget(
            max_candidate_sources=2,
            max_search_rounds=1,
            max_metadata_reads=2,
            max_content_reads=1,
            max_branches=0,
            max_depth=1,
        ),
        policy_context=PolicyContext(
            policy_config_ref="POLICY-TEST@0.1",
            processing_zone="local_test",
            profile_refs=(),
            policy_anchor_ids=("PA-TEST",),
        ),
        requested_at="2026-08-13T12:00:00+02:00",
    )

    assert request.to_dict()["candidate_scope"]["scope_ref"] == "SCOPE-TEST"
    assert request.to_dict()["budget"]["max_content_reads"] == 1
    assert request.to_dict()["lesson_learned_required_gap_refs"] == ("GAP-1",)
    with pytest.raises(FrozenInstanceError):
        request.purpose = "changed"  # type: ignore[misc]


def test_required_lesson_gap_refs_must_be_requested() -> None:
    with pytest.raises(ValueError, match="lesson_learned_required_gap_refs"):
        ContinuationRequest(
            continuation_request_ref="CREQ-TEST",
            consumer_ref="consumer-test",
            purpose="similar_experience_retrieval",
            experience_ref="EXP-TEST",
            continuation_requirement_ref="CONT-TEST",
            gap_refs=("GAP-1",),
            lesson_learned_required_gap_refs=("GAP-OTHER",),
            search_after="2024-09-06T15:30:00+02:00",
            candidate_scope=CandidateScope("SCOPE-TEST", ("SOURCE-A",)),
            budget=ContinuationBudget(1, 1, 1, 1, 0, 1),
            policy_context=PolicyContext("POLICY@0.1", "local_test", (), ()),
            requested_at="2026-08-13T12:00:00+02:00",
        )


def test_required_lesson_gaps_are_derived_from_phase_semantics() -> None:
    projection = {
        "phases": [
            {"phase_ref": "execution", "required_for_lesson_learned": True},
            {"phase_ref": "follow_up", "required_for_lesson_learned": False},
        ],
        "gaps": [
            {"gap_ref": "GAP-EXECUTION", "phase_ref": "execution"},
            {"gap_ref": "GAP-FOLLOW-UP", "phase_ref": "follow_up"},
        ],
    }

    assert derive_lesson_learned_required_gap_refs(
        projection, ("GAP-EXECUTION", "GAP-FOLLOW-UP")
    ) == ("GAP-EXECUTION",)


@pytest.mark.parametrize(
    "field",
    [
        "max_candidate_sources",
        "max_search_rounds",
        "max_metadata_reads",
        "max_content_reads",
        "max_branches",
        "max_depth",
    ],
)
def test_continuation_budget_rejects_negative_bounds(field: str) -> None:
    values = {
        "max_candidate_sources": 1,
        "max_search_rounds": 1,
        "max_metadata_reads": 1,
        "max_content_reads": 1,
        "max_branches": 0,
        "max_depth": 1,
    }
    values[field] = -1

    with pytest.raises(ValueError, match=field):
        ContinuationBudget(**values)
