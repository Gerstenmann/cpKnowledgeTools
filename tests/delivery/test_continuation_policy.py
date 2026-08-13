from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from cp_knowledge_tools.delivery.continuation import (
    AuthorizationDecision,
    CandidateEvidence,
    CandidateMetadata,
    CandidateScope,
    ContinuationBudget,
    ContinuationExecutor,
    ContinuationRequest,
    ContinuationServices,
    PolicyContext,
)


def _request(
    gap_refs: tuple[str, ...] = ("GAP-1",),
    lesson_required: tuple[str, ...] = ("GAP-1",),
) -> ContinuationRequest:
    return ContinuationRequest(
        continuation_request_ref="CREQ-POLICY",
        consumer_ref="consumer-test",
        purpose="similar_experience_retrieval",
        experience_ref="EXP-TEST",
        continuation_requirement_ref="CONT-TEST",
        gap_refs=gap_refs,
        lesson_learned_required_gap_refs=lesson_required,
        search_after="2024-01-01T00:00:00Z",
        candidate_scope=CandidateScope("SCOPE-TEST", ("SOURCE-A",)),
        budget=ContinuationBudget(1, 1, 1, 1, 0, 1),
        policy_context=PolicyContext("POLICY@0.1", "local_test", (), ()),
        requested_at="2026-08-13T12:00:00+02:00",
    )


def _services(calls: list[str]) -> ContinuationServices:
    def discover(
        request: ContinuationRequest, round_index: int, limit: int
    ) -> tuple[str, ...]:
        calls.append("discover")
        return ("SOURCE-A",)

    def read_metadata(candidate_ref: str) -> CandidateMetadata:
        calls.append(f"read_metadata:{candidate_ref}")
        return CandidateMetadata(candidate_ref, "2024-02-01T00:00:00Z", ("test",))

    def rank(metadata: CandidateMetadata, gap_refs: tuple[str, ...]) -> float:
        calls.append(f"rank:{metadata.candidate_ref}")
        return 1.0

    def read_content(candidate_ref: str) -> str:
        calls.append(f"read_content:{candidate_ref}")
        return "evidence content"

    def interpret(
        metadata: CandidateMetadata,
        content: str,
        gap_refs: tuple[str, ...],
    ) -> CandidateEvidence:
        calls.append(f"interpret:{metadata.candidate_ref}")
        return CandidateEvidence(
            evidence_ref="EVIDENCE-A",
            source_ref=metadata.candidate_ref,
            resolved_gap_refs=("GAP-1",),
            informed_gap_refs=("GAP-1",),
            facts=(),
        )

    return ContinuationServices(
        discover=discover,
        read_metadata=read_metadata,
        rank=rank,
        read_content=read_content,
        interpret=interpret,
    )


def _authorizer(
    calls: list[str], deny: str | None = None
) -> Callable[[str, ContinuationRequest, str | None], AuthorizationDecision]:
    def authorize(
        operation: str,
        request: ContinuationRequest,
        candidate_ref: str | None,
    ) -> AuthorizationDecision:
        suffix = f":{candidate_ref}" if candidate_ref else ""
        calls.append(f"authorize:{operation}{suffix}")
        return AuthorizationDecision(
            permitted=operation != deny,
            policy_decision_ref=f"PDEC-{operation.upper()}",
            reason="test_policy",
        )

    return authorize


def test_no_discover_call_or_candidate_existence_leak_before_permit() -> None:
    calls: list[str] = []
    result = ContinuationExecutor().execute(
        _request(), _services(calls), _authorizer(calls, deny="discover")
    )

    assert calls == ["authorize:discover"]
    assert result.sources_discovered == ()
    assert result.metadata_reads == ()
    assert result.content_reads == ()
    assert result.stop_reason == "discover_not_authorized"
    assert "SOURCE-A" not in str(result.to_dict())


def test_authorization_precedes_metadata_ranking_and_content_load() -> None:
    calls: list[str] = []
    result = ContinuationExecutor().execute(
        _request(), _services(calls), _authorizer(calls)
    )

    assert calls == [
        "authorize:discover",
        "discover",
        "authorize:read_metadata:SOURCE-A",
        "read_metadata:SOURCE-A",
        "rank:SOURCE-A",
        "authorize:read_content:SOURCE-A",
        "read_content:SOURCE-A",
        "interpret:SOURCE-A",
    ]
    assert result.resolved_gaps == ("GAP-1",)
    assert result.budget_usage.search_rounds == 1
    assert result.budget_usage.branches == 0
    assert result.budget_usage.depth == 1


def test_metadata_denial_prevents_loader_and_unauthorized_ranking() -> None:
    calls: list[str] = []
    result = ContinuationExecutor().execute(
        _request(), _services(calls), _authorizer(calls, deny="read_metadata")
    )

    assert calls == [
        "authorize:discover",
        "discover",
        "authorize:read_metadata:SOURCE-A",
    ]
    assert result.metadata_reads == ()
    assert result.stop_reason == "metadata_not_authorized"


def test_content_denial_prevents_loader_interpretation_and_gap_closure() -> None:
    calls: list[str] = []
    result = ContinuationExecutor().execute(
        _request(), _services(calls), _authorizer(calls, deny="read_content")
    )

    assert "read_content:SOURCE-A" not in calls
    assert "interpret:SOURCE-A" not in calls
    assert result.content_reads == ()
    assert result.evidence_refs == ()
    assert result.resolved_gaps == ()
    assert result.unresolved_gaps == ("GAP-1",)
    assert result.stop_reason == "content_not_authorized"


def test_candidate_at_or_before_search_boundary_is_not_ranked_or_read() -> None:
    calls: list[str] = []
    services = _services(calls)

    def old_metadata(candidate_ref: str) -> CandidateMetadata:
        calls.append(f"read_metadata:{candidate_ref}")
        return CandidateMetadata(candidate_ref, "2023-12-31T23:59:59Z", ("test",))

    services = ContinuationServices(
        discover=services.discover,
        read_metadata=old_metadata,
        rank=services.rank,
        read_content=services.read_content,
        interpret=services.interpret,
    )

    result = ContinuationExecutor().execute(
        _request(), services, _authorizer(calls)
    )

    assert "rank:SOURCE-A" not in calls
    assert "read_content:SOURCE-A" not in calls
    assert result.stop_reason == "no_relevant_candidates"


def test_informative_evidence_is_retained_without_closing_optional_gap() -> None:
    calls: list[str] = []
    services = _services(calls)

    def interpret(
        metadata: CandidateMetadata,
        content: str,
        gap_refs: tuple[str, ...],
    ) -> CandidateEvidence:
        calls.append(f"interpret:{metadata.candidate_ref}")
        return CandidateEvidence(
            evidence_ref="EVIDENCE-A",
            source_ref=metadata.candidate_ref,
            resolved_gap_refs=("GAP-REQUIRED",),
            informed_gap_refs=("GAP-REQUIRED", "GAP-OPTIONAL"),
            facts=(("optional_status", "approved_not_completed"),),
        )

    services = ContinuationServices(
        discover=services.discover,
        read_metadata=services.read_metadata,
        rank=services.rank,
        read_content=services.read_content,
        interpret=interpret,
    )
    result = ContinuationExecutor().execute(
        _request(
            gap_refs=("GAP-REQUIRED", "GAP-OPTIONAL"),
            lesson_required=("GAP-REQUIRED",),
        ),
        services,
        _authorizer(calls),
    )

    assert result.outcome == "partial"
    assert result.resolved_gaps == ("GAP-REQUIRED",)
    assert result.unresolved_gaps == ("GAP-OPTIONAL",)
    assert result.evidence_refs == ("EVIDENCE-A",)
    assert result.evidence[0].informed_gap_refs == (
        "GAP-REQUIRED",
        "GAP-OPTIONAL",
    )
    assert result.lesson_learned_eligibility == "eligible"


def test_zero_search_round_budget_stops_without_authorization_or_branch() -> None:
    calls: list[str] = []
    request = replace(
        _request(),
        budget=ContinuationBudget(1, 0, 1, 1, 0, 1),
    )

    result = ContinuationExecutor().execute(
        request, _services(calls), _authorizer(calls)
    )

    assert calls == []
    assert result.stop_reason == "budget_exhausted"
    assert result.budget_usage.search_rounds == 0
    assert result.budget_usage.branches == 0
    assert result.budget_usage.depth == 0
