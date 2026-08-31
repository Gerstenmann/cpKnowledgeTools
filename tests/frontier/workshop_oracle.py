"""Assertion-only WI-018 vectors/oracle. Never import this from a producer.

This fixture-specific exact oracle is not an untrusted-response decoder and
does not judge arbitrary natural-language entailment. It detects corruption
of hand-authored contract vectors; future stochastic evaluation needs its own
reviewed semantic comparison, without changing this Golden to fit output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields
from typing import Any

from cp_knowledge_tools.semantics.candidates import (
    Applicability,
    EpistemicContext,
    EvidenceProvenance,
    ProducerProvenance,
    ProposedClaim,
    ProposedEntity,
    ProposedEvent,
    ProposedEvidenceLink,
    ProposedParticipation,
    ProposedRelationship,
    ProposedTime,
    SemanticCandidatePayload,
    SemanticMappingProvenance,
)
from tests.frontier.workshop_baseline import ROOT, Passage, resolve_local

GOLDEN = ROOT / "tests/golden/source_to_knowledge/workshop_versatility/expected.v1.json"
KINDS = {
    "entity": ProposedEntity,
    "claim": ProposedClaim,
    "event": ProposedEvent,
    "participation": ProposedParticipation,
    "relationship": ProposedRelationship,
}


def expected() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text())


def provenance(passage: Passage) -> EvidenceProvenance:
    a = passage.address
    return EvidenceProvenance(
        a.source_key, a.source_ref, a.snapshot_ref, a.record_ref, a.evidence_address_ref
    )


def vector(
    spec: dict[str, Any], passages: dict[str, Passage]
) -> SemanticCandidatePayload:
    """Build an assertion vector from Expected, NOT an output from Source processing."""
    key, kind = spec["key"], spec["kind"]
    proposed = KINDS[kind](**spec["fields"])
    return SemanticCandidatePayload(
        candidate_payload_kind=kind,
        interpretation_rule_ref=key,
        **{f"proposed_{kind}": proposed},
        evidence_links=tuple(
            ProposedEvidenceLink(
                f"test-link:{key}:{i}",
                passages[e].address.evidence_address_ref,
                "reports_statement",
            )
            for i, e in enumerate(spec["evidence"])
        ),
        time=(ProposedTime(**spec["time"]),) if "time" in spec else (),
        epistemic_context=EpistemicContext("reported", "hand_authored_source_reading"),
        applicability=Applicability(
            context_refs=("workshop-versatility@1",),
            conditions=(spec["qualification"],) if "qualification" in spec else (),
        ),
        producer_provenance=ProducerProvenance(
            producer_ref="WI018-ASSERTION-VECTOR-NOT-A-GENERATOR",
            producer_version="1",
            method="assertion_only_hand_authored_contract_vector",
            evidence=tuple(provenance(passages[e]) for e in spec["evidence"]),
            extraction=None,
            semantic_mapping=SemanticMappingProvenance(
                interpretation_rule_ref=key,
                configured_fields=tuple(spec["fields"]),
            ),
        ),
    )


def assert_vector(
    payload: dict[str, Any], spec: dict[str, Any], passages: dict[str, Passage]
) -> None:
    """Scenario-local exact oracle plus actual Source resolution, no authority grant."""
    assert set(payload) == {f.name for f in fields(SemanticCandidatePayload)}
    assert payload["interpretation_rule_ref"] == spec["key"]
    assert payload["candidate_payload_kind"] == spec["kind"]
    for kind, factory in KINDS.items():
        desired = asdict(factory(**spec["fields"])) if kind == spec["kind"] else None
        assert payload[f"proposed_{kind}"] == desired
    assert payload["time"] == ((spec["time"],) if "time" in spec else ())
    assert payload["epistemic_context"] == {
        "status": "reported",
        "classification_basis": "hand_authored_source_reading",
    }
    assert payload["applicability"] == {
        "context_refs": ("workshop-versatility@1",),
        "conditions": (spec["qualification"],) if "qualification" in spec else (),
    }
    assert (
        payload["profile_refs"]
        == payload["known_conflicts"]
        == payload["known_gaps"]
        == ()
    )
    links = payload["evidence_links"]
    assert len(links) == len(spec["evidence"]) > 0
    for link, key in zip(links, spec["evidence"], strict=True):
        p = passages[key]
        assert (
            hashlib.sha256(p.captured.raw_content).hexdigest()
            == expected()["source_hashes"][p.address.source_key]
        ), "Scenario source changed: review/version Golden, never auto-fit"
        assert link["evidence_address_ref"] == p.address.evidence_address_ref
        assert link["role"] == "reports_statement"
        assert resolve_local(p.captured, p.address) == p.content
    producer = payload["producer_provenance"]
    assert producer is not None
    assert producer["method"] == "assertion_only_hand_authored_contract_vector"
    assert producer["producer_ref"] == "WI018-ASSERTION-VECTOR-NOT-A-GENERATOR"
    assert producer["producer_version"] == "1"
    assert producer["extraction"] is None
    assert producer["semantic_mapping"]["interpretation_rule_ref"] == spec["key"]
    assert producer["evidence"] == tuple(
        asdict(provenance(passages[e])) for e in spec["evidence"]
    )
