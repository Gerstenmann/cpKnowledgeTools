from __future__ import annotations

from typing import Any

from cp_knowledge_tools.delivery import (
    ExperienceRetrievalRequest,
    ExperienceRetriever,
)
from cp_knowledge_tools.policy import PolicyDecision, PolicySubject

KO = PolicySubject("knowledge_object", "KO-TEST", "0.1", "Semantic Core")


def _projection() -> dict[str, Any]:
    return {
        "experience_projection_ref": "EXPP-TEST",
        "semantic_hash": "hash-test",
        "experience_ref": "EXP-TEST",
        "publication_unit_ref": {
            "subject_type": "knowledge_object",
            "stable_id": "KO-TEST",
            "version": "0.1",
            "authority_context": "Semantic Core",
        },
        "experience_completeness": "partial",
        "phases": [
            {"phase_ref": "scope", "status": "supported"},
            {"phase_ref": "outcome", "status": "unresolved"},
        ],
        "threads": [
            {"thread_ref": "scope", "semantic_refs": ["CLM-A", "CLM-B"]}
        ],
        "gaps": [
            {"gap_ref": "GAP-OUTCOME", "status": "unresolved"},
            {"gap_ref": "GAP-FOLLOWUP", "status": "unresolved"},
        ],
        "reuse_context": {
            "domain_terms": ["education", "school", "pilot"],
            "topic_terms": ["minecraft_education", "esports"],
            "purpose_terms": ["experience_reuse"],
        },
        "continuation_requirements": [
            {"continuation_ref": "CONT-01", "status": "required"}
        ],
        "lesson_learned_eligibility": "insufficient_evidence",
        "lesson_learned_candidates": [],
    }


def _decision(result: str = "permit") -> PolicyDecision:
    permitted = result == "permit"
    return PolicyDecision(
        policy_decision_ref="PDEC-EXPERIENCE",
        policy_evaluation_ref="PEVAL-EXPERIENCE",
        result=result,
        authorized_actions=("claim_read",) if permitted else (),
        authorized_subject_refs=(KO,) if permitted else (),
        authorized_scope="POLICY@0.1" if permitted else None,
        actor_or_consumer_ref="consumer",
        purpose="reuse",
        processing_zone="local_test",
        policy_rule_refs=("RULE-EXPERIENCE",),
        decision_reasons=("test",),
        decision_authority_ref="POLICY@0.1",
    )


def _request(query: str, **kwargs: Any) -> ExperienceRetrievalRequest:
    return ExperienceRetrievalRequest(
        retrieval_request_ref=f"RREQ-{query}",
        consumer_ref="consumer",
        purpose="reuse",
        knowledge_object_ref=KO,
        query=query,
        **kwargs,
    )


def test_fetches_experience_facets_by_explicit_queries() -> None:
    retriever = ExperienceRetriever()

    def loader() -> tuple[dict[str, Any], ...]:
        return (_projection(),)

    experience = retriever.retrieve(
        loader,
        _request("experience", experience_ref="EXP-TEST"),
        _decision(),
    )
    phases = retriever.retrieve(loader, _request("phases"), _decision())
    thread = retriever.retrieve(
        loader,
        _request("thread", thread_ref="scope"),
        _decision(),
    )
    gaps = retriever.retrieve(
        loader,
        _request("gaps", gap_ref="GAP-OUTCOME"),
        _decision(),
    )
    lesson = retriever.retrieve(
        loader,
        _request("lesson_learned_eligibility"),
        _decision(),
    )
    continuation = retriever.retrieve(
        loader,
        _request("continuation_requirements"),
        _decision(),
    )

    assert experience.items[0]["experience_ref"] == "EXP-TEST"
    assert {item["phase_ref"] for item in phases.items} == {"scope", "outcome"}
    assert thread.items[0]["semantic_refs"] == ["CLM-A", "CLM-B"]
    assert gaps.items == ({"gap_ref": "GAP-OUTCOME", "status": "unresolved"},)
    assert lesson.items[0]["lesson_learned_eligibility"] == (
        "insufficient_evidence"
    )
    assert continuation.items[0]["continuation_ref"] == "CONT-01"
    assert all(result.evidence_content_resolved is False for result in (
        experience, phases, thread, gaps, lesson, continuation
    ))


def test_reuse_matching_uses_terms_not_organization_or_year_identity() -> None:
    result = ExperienceRetriever().retrieve(
        lambda: (_projection(),),
        _request(
            "reuse_match",
            required_terms=("education", "school", "minecraft_education", "esports"),
        ),
        _decision(),
    )
    no_match = ExperienceRetriever().retrieve(
        lambda: (_projection(),),
        _request("reuse_match", required_terms=("healthcare",)),
        _decision(),
    )

    assert result.outcome == "results"
    assert result.items[0]["experience_ref"] == "EXP-TEST"
    assert result.items[0]["experience_completeness"] == "partial"
    assert no_match.outcome == "no_available_results"


def test_denied_retrieval_does_not_read_projection_content() -> None:
    loader_called = False

    def forbidden_loader() -> tuple[dict[str, Any], ...]:
        nonlocal loader_called
        loader_called = True
        raise AssertionError("projection loaded before authorization")

    result = ExperienceRetriever().retrieve(
        forbidden_loader,
        _request("reuse_match", required_terms=("education",)),
        _decision("deny"),
    )

    assert result.outcome == "request_denied"
    assert result.projection_refs == ()
    assert result.items == ()
    assert loader_called is False
