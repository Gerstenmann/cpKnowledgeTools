from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cp_knowledge_tools.delivery.continuation import (
    CandidateScope,
    ContinuationBudget,
    ContinuationRequest,
    PolicyContext,
)


def test_continuation_request_preserves_bounded_context() -> None:
    request = ContinuationRequest(
        continuation_request_ref="CREQ-TEST",
        consumer_ref="consumer-test",
        purpose="similar_experience_retrieval",
        experience_ref="EXP-TEST",
        continuation_requirement_ref="CONT-TEST",
        gap_refs=("GAP-1", "GAP-2"),
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
    with pytest.raises(FrozenInstanceError):
        request.purpose = "changed"  # type: ignore[misc]


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
