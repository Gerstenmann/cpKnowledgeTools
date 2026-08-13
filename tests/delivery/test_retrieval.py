from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from cp_knowledge_tools.delivery import (
    EvidenceResolutionRequest,
    EvidenceResolver,
    KnowledgeRetriever,
    RetrievalRequest,
)
from cp_knowledge_tools.policy import PolicyDecision, PolicySubject

KO = PolicySubject("knowledge_object", "KO-TEST", "0.1", "Semantic Core")
CONSUMER = "consumer-test"
PURPOSE = "retrieve-status"


def _ref(subject_type: str, stable_id: str) -> dict[str, str]:
    return {
        "subject_type": subject_type,
        "stable_id": stable_id,
        "version": "0.1",
        "authority_context": "Semantic Core",
    }


def _claim(claim_id: str, value: str, epistemic_status: str) -> dict[str, Any]:
    return {
        "claim_ref": _ref("claim", claim_id),
        "statement": {
            "subject_ref": _ref("entity", "ENT-SUBJECT"),
            "predicate_ref": "test.training_start",
            "object": {
                "kind": "literal",
                "reference": None,
                "value": value,
                "datatype": "str",
                "language": "en",
            },
        },
        "epistemic_status": epistemic_status,
        "time": [],
        "evidence_link_ids": [f"EL-{claim_id}"],
        "authority_basis_refs": [],
        "policy_anchor_ids": ["PA-KO"],
        "conflict_set_ids": ["CF-TRAINING"],
        "narrative_anchor": f"claim-{claim_id}",
    }


def _projection() -> dict[str, Any]:
    old = _claim("CLM-OLD", "2024-09-19", "reported")
    current = _claim("CLM-CURRENT", "2024-09-26", "confirmed")
    return {
        "projection_schema_version": "0.1",
        "projection_ref": "DRP-TEST",
        "semantic_hash": "hash-test",
        "knowledge_object_ref": {
            "subject_type": KO.subject_type,
            "stable_id": KO.stable_id,
            "version": KO.version,
            "authority_context": KO.authority_context,
        },
        "claim_index": [old, current],
        "event_index": [
            {
                "event_ref": _ref("event", "EVT-DECISION"),
                "event_type_ref": "test.event_type.decision",
                "label": "Deployment decision",
                "time": [
                    {
                        "role": "event_time",
                        "value_kind": "unknown",
                        "precision": "unknown",
                        "modality": "actual",
                        "start": None,
                        "end": None,
                        "timezone": None,
                        "approximate": False,
                        "uncertainty": None,
                        "source_ref": None,
                    }
                ],
                "evidence_link_ids": ["EL-EVT-DECISION"],
                "policy_anchor_ids": ["PA-KO"],
                "narrative_anchor": "event-decision",
            }
        ],
        "participation_index": [
            {
                "participation_ref": _ref(
                    "event_participation", "PART-TEAM-DECISION"
                ),
                "event_ref": _ref("event", "EVT-DECISION"),
                "entity_ref": _ref("entity", "ENT-OPERATIONS-TEAM"),
                "role": "test.role.decision_maker",
                "time": [],
                "claim_refs": [],
                "evidence_link_ids": ["EL-PART-DECISION"],
                "policy_anchor_ids": ["PA-KO"],
                "narrative_anchor": "participation-team-decision",
            }
        ],
        "evidence_index": [
            {
                "evidence_link_id": "EL-CLM-OLD",
                "subject_ref": old["claim_ref"],
                "evidence_address_ref": _ref("evidence_address", "EA-OLD"),
                "role": "reports_statement",
                "policy_anchor_ids": ["PA-KO"],
            },
            {
                "evidence_link_id": "EL-CLM-CURRENT",
                "subject_ref": current["claim_ref"],
                "evidence_address_ref": _ref("evidence_address", "EA-CURRENT"),
                "role": "supports",
                "policy_anchor_ids": ["PA-KO"],
            },
            {
                "evidence_link_id": "EL-PART-DECISION",
                "subject_ref": _ref(
                    "event_participation", "PART-TEAM-DECISION"
                ),
                "evidence_address_ref": _ref(
                    "evidence_address", "EA-PART-DECISION"
                ),
                "role": "supports",
                "policy_anchor_ids": ["PA-KO"],
            },
        ],
        "conflict_index": [
            {
                "conflict_set_id": "CF-TRAINING",
                "claim_refs": [old["claim_ref"], current["claim_ref"]],
                "conflict_dimensions": ["temporal"],
                "preferred_claim_ref": current["claim_ref"],
                "preference_context": "current_plan",
            }
        ],
        "policy_index": [],
    }


def _decision(*, result: str = "permit") -> PolicyDecision:
    authorized = result == "permit"
    return PolicyDecision(
        policy_decision_ref="PDEC-TEST",
        policy_evaluation_ref="PEVAL-TEST",
        result=result,
        authorized_actions=("claim_read",) if authorized else (),
        authorized_subject_refs=(KO,) if authorized else (),
        authorized_scope="TEST-POLICY@0.1" if authorized else None,
        actor_or_consumer_ref=CONSUMER,
        purpose=PURPOSE,
        processing_zone="local_test",
        policy_rule_refs=("RULE-TEST",),
        decision_reasons=("test",),
        decision_authority_ref="TEST-POLICY@0.1",
    )


def _request(state_selection: str) -> RetrievalRequest:
    return RetrievalRequest(
        retrieval_request_ref=f"RREQ-{state_selection}",
        consumer_ref=CONSUMER,
        purpose=PURPOSE,
        knowledge_object_ref=KO,
        semantic_subject_refs=("ENT-SUBJECT",),
        claim_predicate_refs=("test.training_start",),
        state_selection=state_selection,
    )


def test_current_query_uses_preferred_claim_from_projection() -> None:
    result = KnowledgeRetriever().retrieve(
        _projection(),
        _request("current"),
        _decision(),
    )

    assert result.outcome == "results"
    assert result.projection_ref == "DRP-TEST"
    assert result.publication_unit_ref == {
        "subject_type": "knowledge_object",
        "stable_id": "KO-TEST",
        "version": "0.1",
        "authority_context": "Semantic Core",
    }
    assert [item["subject_ref"]["stable_id"] for item in result.claim_items] == [
        "CLM-CURRENT"
    ]
    assert result.claim_items[0]["epistemic_status"] == "confirmed"
    assert result.claim_items[0]["state_role"] == "current"
    assert result.claim_items[0]["preferred_in_conflict"] is True
    assert result.claim_items[0]["evidence_refs"][0]["stable_id"] == "EA-CURRENT"
    assert result.evidence_content_resolved is False


def test_history_query_preserves_current_and_historical_claims() -> None:
    result = KnowledgeRetriever().retrieve(
        _projection(),
        _request("all"),
        _decision(),
    )

    states = {
        item["subject_ref"]["stable_id"]: item["state_role"]
        for item in result.claim_items
    }
    assert states == {"CLM-OLD": "historical", "CLM-CURRENT": "current"}
    assert result.conflict_items[0]["conflict_set_id"] == "CF-TRAINING"


def test_relational_claim_query_returns_reference_object() -> None:
    projection = _projection()
    projection["claim_index"].append(
        {
            **_claim("CLM-RELATIONSHIP", "unused", "confirmed"),
            "statement": {
                "subject_ref": _ref("entity", "ENT-PERSON"),
                "predicate_ref": "test.relationship.affiliated_with",
                "object": {
                    "kind": "reference",
                    "reference": _ref("entity", "ENT-ORGANIZATION"),
                    "value": None,
                    "datatype": None,
                    "language": None,
                },
            },
        }
    )
    request = RetrievalRequest(
        retrieval_request_ref="RREQ-RELATIONSHIP",
        consumer_ref=CONSUMER,
        purpose=PURPOSE,
        knowledge_object_ref=KO,
        semantic_subject_refs=("ENT-PERSON",),
        claim_predicate_refs=("test.relationship.affiliated_with",),
    )

    result = KnowledgeRetriever().retrieve(projection, request, _decision())

    assert result.outcome == "results"
    assert result.claim_items[0]["statement"]["object"]["reference"][
        "stable_id"
    ] == "ENT-ORGANIZATION"


def test_participation_query_filters_by_role_and_event_type() -> None:
    request = RetrievalRequest(
        retrieval_request_ref="RREQ-DECISION-MAKER",
        consumer_ref=CONSUMER,
        purpose=PURPOSE,
        knowledge_object_ref=KO,
        semantic_subject_refs=(),
        event_type_refs=("test.event_type.decision",),
        participant_entity_refs=("ENT-OPERATIONS-TEAM",),
        participation_role_refs=("test.role.decision_maker",),
    )

    result = KnowledgeRetriever().retrieve(_projection(), request, _decision())

    assert result.outcome == "results"
    assert result.event_items == ()
    assert result.participation_items[0]["entity_ref"]["stable_id"] == (
        "ENT-OPERATIONS-TEAM"
    )
    assert result.participation_items[0]["event_type_ref"] == (
        "test.event_type.decision"
    )
    assert result.participation_items[0]["evidence_refs"][0]["stable_id"] == (
        "EA-PART-DECISION"
    )


def test_participation_role_abstains_when_projection_has_no_match() -> None:
    request = RetrievalRequest(
        retrieval_request_ref="RREQ-NO-REPRESENTATIVE",
        consumer_ref=CONSUMER,
        purpose=PURPOSE,
        knowledge_object_ref=KO,
        semantic_subject_refs=(),
        event_type_refs=("test.event_type.decision",),
        participation_role_refs=("test.role.representative",),
    )

    result = KnowledgeRetriever().retrieve(_projection(), request, _decision())

    assert result.outcome == "no_available_results"
    assert result.participation_items == ()


class _ForbiddenProjection(Mapping[str, Any]):
    def __getitem__(self, key: str) -> Any:
        raise AssertionError(f"projection content accessed before authorization: {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


def test_denied_retrieval_does_not_access_projection() -> None:
    result = KnowledgeRetriever().retrieve(
        _ForbiddenProjection(),
        _request("current"),
        _decision(result="deny"),
    )

    assert result.outcome == "request_denied"
    assert result.projection_ref == "not_accessed"
    assert result.claim_items == ()


def test_denied_evidence_resolution_does_not_load_content() -> None:
    evidence_ref = PolicySubject(
        "evidence_address",
        "EA-RESTRICTED",
        "0.1",
        "Source and Evidence",
    )
    request = EvidenceResolutionRequest(
        evidence_resolution_request_ref="ERREQ-TEST",
        consumer_ref=CONSUMER,
        purpose=PURPOSE,
        evidence_ref=evidence_ref,
    )
    called = False

    def loader() -> str:
        nonlocal called
        called = True
        return "restricted content"

    result = EvidenceResolver().resolve(request, _decision(result="deny"), loader)

    assert result.status == "not_authorized"
    assert result.content is None
    assert result.content_resolved is False
    assert called is False
