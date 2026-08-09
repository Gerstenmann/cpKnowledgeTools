from __future__ import annotations

from typing import Any

from cp_knowledge_tools.platform.hashing import stable_token

from .candidates import SemanticCandidatePayload, SemanticInterpretationResult


class SemanticStateMaterializer:
    """Materialize MVP semantic state after explicit Candidate creation.

    Current/historical state and conflict preferences are supplied through a
    separate downstream curation configuration. This is intentionally not a
    general Candidate Resolution or Knowledge Lifecycle implementation.
    """

    def materialize(
        self,
        interpretation: SemanticInterpretationResult,
        curation: dict[str, Any],
    ) -> dict[str, Any]:
        candidates = interpretation.candidate_payloads
        entities = self._entities(candidates)
        entity_by_key = {item["rule_key"]: item for item in entities}
        entity_by_label = {item["label"]: item for item in entities}
        claims, pattern_claims = self._claims(
            candidates,
            entity_by_key,
            entity_by_label,
            curation.get("claim_states", {}),
        )
        claim_by_key = {item["rule_key"]: item for item in claims}
        evidence_links = self._evidence_links(candidates, claim_by_key)
        events = self._events(candidates)
        event_by_key = {item["rule_key"]: item for item in events}
        participations = self._participations(
            candidates,
            entity_by_key,
            event_by_key,
        )
        conflict_sets = self._conflicts(
            claim_by_key,
            curation.get("conflict_sets", []),
        )
        return {
            "entities": entities,
            "claims": claims,
            "evidence_links": evidence_links,
            "events": events,
            "participations": participations,
            "conflict_sets": conflict_sets,
            "pattern_claims": pattern_claims,
        }

    def _entities(
        self,
        candidates: tuple[SemanticCandidatePayload, ...],
    ) -> list[dict[str, Any]]:
        result = []
        for candidate in candidates:
            proposal = candidate.proposed_entity
            if proposal is None:
                continue
            result.append(
                {
                    "rule_key": proposal.entity_key,
                    "entity_ref": stable_token(
                        "ENT",
                        proposal.entity_class,
                        proposal.label,
                    ),
                    "label": proposal.label,
                    "class": proposal.entity_class,
                }
            )
        return result

    def _claims(
        self,
        candidates: tuple[SemanticCandidatePayload, ...],
        entity_by_key: dict[str, dict[str, Any]],
        entity_by_label: dict[str, dict[str, Any]],
        claim_states: dict[str, dict[str, bool]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        claims = []
        pattern_claims = []
        for candidate in candidates:
            proposal = candidate.proposed_claim
            if proposal is None:
                continue
            if proposal.subject_entity_key is None or proposal.predicate_ref is None:
                assert proposal.statement is not None
                assert candidate.epistemic_context is not None
                pattern_claims.append(
                    {
                        "rule_key": proposal.claim_key,
                        "statement": proposal.statement,
                        "epistemic_status": candidate.epistemic_context.status,
                        "evidence_roles": [
                            link.role for link in candidate.evidence_links
                        ],
                        "source_keys": self._source_keys(candidate),
                    }
                )
                continue

            if proposal.claim_key not in claim_states:
                raise ValueError(
                    "Downstream curation lacks explicit Claim state for "
                    f"{proposal.claim_key}"
                )
            state = claim_states[proposal.claim_key]
            subject = entity_by_key[proposal.subject_entity_key]
            object_ref = None
            if proposal.object_entity_label is not None:
                object_ref = entity_by_label[proposal.object_entity_label]["entity_ref"]
            claim_ref = stable_token(
                "CLM",
                subject["entity_ref"],
                proposal.predicate_ref,
                object_ref or proposal.value,
                proposal.time_modality,
            )
            assert candidate.epistemic_context is not None
            claims.append(
                {
                    "rule_key": proposal.claim_key,
                    "claim_ref": claim_ref,
                    "subject_ref": subject["entity_ref"],
                    "predicate_ref": proposal.predicate_ref,
                    "value": proposal.value,
                    "object_ref": object_ref,
                    "epistemic_status": candidate.epistemic_context.status,
                    "source_keys": self._source_keys(candidate),
                    "evidence_keys": [
                        link.evidence_link_key for link in candidate.evidence_links
                    ],
                    "time_modality": proposal.time_modality,
                    "current": state["current"],
                    "preserved": state["preserved"],
                    "value_qualifier": proposal.value_qualifier,
                }
            )
        return claims, pattern_claims

    def _evidence_links(
        self,
        candidates: tuple[SemanticCandidatePayload, ...],
        claim_by_key: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for candidate in candidates:
            proposal = candidate.proposed_claim
            if (
                proposal is None
                or proposal.claim_key not in claim_by_key
                or proposal.subject_entity_key is None
            ):
                continue
            claim = claim_by_key[proposal.claim_key]
            for link in candidate.evidence_links:
                result.append(
                    {
                        "rule_key": link.evidence_link_key,
                        "evidence_link_ref": stable_token(
                            "EL",
                            claim["claim_ref"],
                            link.evidence_address_ref,
                            link.role,
                        ),
                        "claim_ref": claim["claim_ref"],
                        "evidence_address_ref": link.evidence_address_ref,
                        "role": link.role,
                    }
                )
        return result

    def _events(
        self,
        candidates: tuple[SemanticCandidatePayload, ...],
    ) -> list[dict[str, Any]]:
        result = []
        for candidate in candidates:
            proposal = candidate.proposed_event
            if proposal is None:
                continue
            result.append(
                {
                    "rule_key": proposal.event_key,
                    "event_ref": stable_token(
                        "EVT",
                        proposal.event_type_ref,
                        proposal.label,
                    ),
                    "event_type_ref": proposal.event_type_ref,
                    "label": proposal.label,
                    "event_time": proposal.event_time,
                    "time_precision": proposal.time_precision,
                    "time_modality": proposal.time_modality,
                    "source_keys": self._source_keys(candidate),
                    "evidence_keys": [
                        item.evidence_address_ref
                        for item in candidate.producer_provenance.evidence
                    ],
                }
            )
        return result

    def _participations(
        self,
        candidates: tuple[SemanticCandidatePayload, ...],
        entity_by_key: dict[str, dict[str, Any]],
        event_by_key: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for candidate in candidates:
            proposal = candidate.proposed_participation
            if proposal is None:
                continue
            entity = entity_by_key[proposal.entity_key]
            event = event_by_key[proposal.event_key]
            result.append(
                {
                    "rule_key": proposal.participation_key,
                    "participation_ref": stable_token(
                        "PART",
                        entity["entity_ref"],
                        event["event_ref"],
                        proposal.role,
                    ),
                    "entity_ref": entity["entity_ref"],
                    "event_ref": event["event_ref"],
                    "role": proposal.role,
                    "source_keys": self._source_keys(candidate),
                }
            )
        return result

    def _conflicts(
        self,
        claim_by_key: dict[str, dict[str, Any]],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for rule in rules:
            claims = [claim_by_key[key] for key in rule["claim_keys"]]
            preferred = claim_by_key[rule["preferred_claim_key"]]
            result.append(
                {
                    "rule_key": rule["rule_key"],
                    "conflict_set_ref": stable_token(
                        "CF",
                        *sorted(claim["claim_ref"] for claim in claims),
                        *rule["conflict_dimensions"],
                    ),
                    "claim_refs": [claim["claim_ref"] for claim in claims],
                    "conflict_dimensions": list(rule["conflict_dimensions"]),
                    "preferred_claim_ref": preferred["claim_ref"],
                    "preference_context": rule["preference_context"],
                    "rationale": rule["rationale"],
                }
            )
        return result

    def _source_keys(self, candidate: SemanticCandidatePayload) -> list[str]:
        assert candidate.producer_provenance is not None
        return list(
            dict.fromkeys(
                item.source_key for item in candidate.producer_provenance.evidence
            )
        )
