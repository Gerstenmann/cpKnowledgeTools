from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cp_knowledge_tools.sources.models import EvidenceAddress, NormalizedRecord

from .candidates import (
    Applicability,
    EpistemicContext,
    EvidenceProvenance,
    KnownGap,
    ProducerProvenance,
    ProposedClaim,
    ProposedEntity,
    ProposedEvent,
    ProposedEvidenceLink,
    ProposedParticipation,
    ProposedRelationship,
    ProposedTime,
    SemanticCandidatePayload,
    SemanticInterpretationResult,
    SemanticMappingProvenance,
    SemanticValue,
)
from .extraction import DeterministicEvidenceExtractor, ExtractionResult


class RuleBasedSemanticInterpreter:
    """Produce non-canonical semantic proposals from source-neutral Evidence.

    Scenario rules supply semantic mappings and deterministic extraction
    instructions. Material factual values are read from ``EvidenceAddress``
    text; they are not accepted as completed Claim or Event values.
    """

    producer_ref = "CPKT-RULE-INTERPRETER"
    producer_version = "0.3"

    def __init__(
        self,
        extractor: DeterministicEvidenceExtractor | None = None,
    ) -> None:
        self._extractor = extractor or DeterministicEvidenceExtractor()

    def interpret(
        self,
        records: dict[str, NormalizedRecord],
        evidence: dict[str, EvidenceAddress],
        rules: dict[str, Any],
    ) -> SemanticInterpretationResult:
        candidates: list[SemanticCandidatePayload] = []
        gaps: list[KnownGap] = []
        link_rules = rules.get("evidence_links", [])

        for rule in rules.get("entities", []):
            candidate, gap = self._entity_candidate(records, evidence, rule)
            self._collect(candidate, gap, candidates, gaps)

        for rule in rules.get("claims", []):
            candidate, gap = self._claim_candidate(
                records,
                evidence,
                rule,
                link_rules,
            )
            self._collect(candidate, gap, candidates, gaps)

        for rule in rules.get("relationships", []):
            candidate, gap = self._relationship_candidate(
                records,
                evidence,
                rule,
                link_rules,
            )
            self._collect(candidate, gap, candidates, gaps)

        for rule in rules.get("events", []):
            candidate, gap = self._event_candidate(
                records,
                evidence,
                rule,
                link_rules,
            )
            self._collect(candidate, gap, candidates, gaps)

        for rule in rules.get("participations", []):
            candidate = self._participation_candidate(
                records,
                evidence,
                rule,
                link_rules,
            )
            candidates.append(candidate)

        for rule in rules.get("pattern_claims", []):
            candidate, gap = self._pattern_claim_candidate(records, evidence, rule)
            self._collect(candidate, gap, candidates, gaps)

        return SemanticInterpretationResult(
            candidate_payloads=tuple(candidates),
            known_gaps=tuple(gaps),
        )

    def _entity_candidate(
        self,
        records: dict[str, NormalizedRecord],
        evidence: dict[str, EvidenceAddress],
        rule: dict[str, Any],
    ) -> tuple[SemanticCandidatePayload | None, KnownGap | None]:
        addresses = self._addresses(records, evidence, rule)
        extraction, gap = self._extract(rule, evidence, addresses)
        if gap is not None:
            return None, gap
        assert extraction is not None
        label = str(extraction.value)
        mapping = self._mapping_provenance(
            rule,
            configured_fields=("entity_class",),
        )
        return (
            SemanticCandidatePayload(
                candidate_payload_kind="implementation_local.proposed_entity",
                interpretation_rule_ref=rule["rule_key"],
                proposed_entity=ProposedEntity(
                    entity_key=rule["rule_key"],
                    label=label,
                    entity_class=rule["entity_class"],
                ),
                applicability=self._applicability(rule),
                profile_refs=tuple(rule.get("profile_refs", ())),
                producer_provenance=self._producer(
                    addresses,
                    extraction,
                    mapping,
                ),
            ),
            None,
        )

    def _claim_candidate(
        self,
        records: dict[str, NormalizedRecord],
        evidence: dict[str, EvidenceAddress],
        rule: dict[str, Any],
        link_rules: list[dict[str, Any]],
    ) -> tuple[SemanticCandidatePayload | None, KnownGap | None]:
        addresses = self._addresses(records, evidence, rule)
        extraction, gap = self._extract(rule, evidence, addresses)
        if gap is not None:
            return None, gap
        assert extraction is not None
        value, value_mapping_from, value_mapping_to = self._semantic_value(
            extraction.value,
            rule,
        )
        object_entity_label = None
        if rule.get("object_kind") == "entity_mention":
            object_entity_label = str(value)
            value = None

        candidate_links = self._candidate_evidence_links(
            evidence,
            rule["rule_key"],
            link_rules,
        )
        mapping_fields = [
            "subject_entity_key",
            "predicate_ref",
            "epistemic_status",
            "epistemic_classification_basis",
        ]
        if "semantic_value_map" in rule:
            mapping_fields.append("semantic_value_map")
        if candidate_links:
            mapping_fields.append("evidence_links.role")
        for optional in ("time_modality", "value_qualifier", "object_kind"):
            if optional in rule:
                mapping_fields.append(optional)
        mapping = self._mapping_provenance(
            rule,
            configured_fields=tuple(mapping_fields),
            value_mapping_from=value_mapping_from,
            value_mapping_to=value_mapping_to,
        )
        time = ()
        if rule.get("time_role"):
            time = (
                ProposedTime(
                    role=rule["time_role"],
                    value=str(value) if value is not None else None,
                    precision=rule.get("time_precision", "unknown"),
                    modality=rule.get("time_modality", "unknown"),
                ),
            )
        return (
            SemanticCandidatePayload(
                candidate_payload_kind="implementation_local.proposed_claim",
                interpretation_rule_ref=rule["rule_key"],
                proposed_claim=ProposedClaim(
                    claim_key=rule["rule_key"],
                    subject_entity_key=rule["subject_entity_key"],
                    predicate_ref=rule["predicate_ref"],
                    value=value,
                    object_entity_label=object_entity_label,
                    time_modality=rule.get("time_modality"),
                    value_qualifier=rule.get("value_qualifier"),
                ),
                evidence_links=candidate_links,
                time=time,
                epistemic_context=EpistemicContext(
                    status=rule["epistemic_status"],
                    classification_basis=rule["epistemic_classification_basis"],
                ),
                applicability=self._applicability(rule),
                profile_refs=tuple(rule.get("profile_refs", ())),
                producer_provenance=self._producer(
                    addresses,
                    extraction,
                    mapping,
                ),
            ),
            None,
        )

    def _event_candidate(
        self,
        records: dict[str, NormalizedRecord],
        evidence: dict[str, EvidenceAddress],
        rule: dict[str, Any],
        link_rules: list[dict[str, Any]],
    ) -> tuple[SemanticCandidatePayload | None, KnownGap | None]:
        addresses = self._addresses(records, evidence, rule)
        extraction = None
        event_time = None
        if "extraction" in rule:
            extraction, gap = self._extract(rule, evidence, addresses)
            if gap is not None:
                return None, gap
            assert extraction is not None
            event_time = str(extraction.value)
        elif rule.get("event_time_from_source"):
            source_times = {
                records[address.source_key].source_time for address in addresses
            }
            if len(source_times) != 1:
                raise ValueError(
                    "Event source-time derivation requires one unique source time: "
                    f"{rule['rule_key']}"
                )
            event_time = source_times.pop()
        candidate_links = self._candidate_evidence_links(
            evidence,
            rule["rule_key"],
            link_rules,
        )
        mapping_fields = [
            "event_type_ref",
            "label",
            "time_precision",
            "time_modality",
        ]
        if rule.get("event_time_from_source"):
            mapping_fields.append("event_time_from_source")
        if candidate_links:
            mapping_fields.append("evidence_links.role")
        mapping = self._mapping_provenance(
            rule,
            configured_fields=tuple(mapping_fields),
        )
        time = (
            ProposedTime(
                role="event_time",
                value=event_time,
                precision=rule.get("time_precision", "unknown"),
                modality=rule.get("time_modality", "planned"),
            ),
        )
        return (
            SemanticCandidatePayload(
                candidate_payload_kind="implementation_local.proposed_event",
                interpretation_rule_ref=rule["rule_key"],
                proposed_event=ProposedEvent(
                    event_key=rule["rule_key"],
                    event_type_ref=rule["event_type_ref"],
                    label=rule["label"],
                    event_time=event_time,
                    time_precision=rule.get("time_precision", "unknown"),
                    time_modality=rule.get("time_modality", "planned"),
                ),
                evidence_links=candidate_links,
                time=time,
                applicability=self._applicability(rule),
                profile_refs=tuple(rule.get("profile_refs", ())),
                producer_provenance=self._producer(
                    addresses,
                    extraction,
                    mapping,
                ),
            ),
            None,
        )

    def _participation_candidate(
        self,
        records: dict[str, NormalizedRecord],
        evidence: dict[str, EvidenceAddress],
        rule: dict[str, Any],
        link_rules: list[dict[str, Any]],
    ) -> SemanticCandidatePayload:
        addresses = self._addresses(records, evidence, rule)
        role = rule["role"]
        if not role:
            raise ValueError("Event Participation role is mandatory")
        mapping = self._mapping_provenance(
            rule,
            configured_fields=(
                "entity_key",
                "event_key",
                "role",
                "evidence_links.role",
            ),
        )
        return SemanticCandidatePayload(
            candidate_payload_kind="implementation_local.proposed_participation",
            interpretation_rule_ref=rule["rule_key"],
            proposed_participation=ProposedParticipation(
                participation_key=rule["rule_key"],
                entity_key=rule["entity_key"],
                event_key=rule["event_key"],
                role=role,
            ),
            evidence_links=self._candidate_evidence_links(
                evidence,
                rule["rule_key"],
                link_rules,
            ),
            applicability=self._applicability(rule),
            profile_refs=tuple(rule.get("profile_refs", ())),
            producer_provenance=self._producer(addresses, None, mapping),
        )

    def _relationship_candidate(
        self,
        records: dict[str, NormalizedRecord],
        evidence: dict[str, EvidenceAddress],
        rule: dict[str, Any],
        link_rules: list[dict[str, Any]],
    ) -> tuple[SemanticCandidatePayload | None, KnownGap | None]:
        addresses = self._addresses(records, evidence, rule)
        extraction, gap = self._extract(rule, evidence, addresses)
        if gap is not None:
            return None, gap
        assert extraction is not None
        candidate_links = self._candidate_evidence_links(
            evidence,
            rule["rule_key"],
            link_rules,
        )
        time = tuple(
            ProposedTime(
                role="source_time",
                value=records[address.source_key].source_time,
                precision="minute",
                modality="actual",
            )
            for address in addresses
        )
        mapping = self._mapping_provenance(
            rule,
            configured_fields=(
                "subject_key",
                "predicate_ref",
                "object_key",
                "epistemic_status",
                "epistemic_classification_basis",
                "evidence_links.role",
                "time.source_time",
            ),
        )
        return (
            SemanticCandidatePayload(
                candidate_payload_kind=(
                    "implementation_local.proposed_relationship"
                ),
                interpretation_rule_ref=rule["rule_key"],
                proposed_relationship=ProposedRelationship(
                    relationship_key=rule["rule_key"],
                    subject_key=rule["subject_key"],
                    predicate_ref=rule["predicate_ref"],
                    object_key=rule["object_key"],
                ),
                evidence_links=candidate_links,
                time=time,
                epistemic_context=EpistemicContext(
                    status=rule["epistemic_status"],
                    classification_basis=rule[
                        "epistemic_classification_basis"
                    ],
                ),
                applicability=self._applicability(rule),
                profile_refs=tuple(rule.get("profile_refs", ())),
                producer_provenance=self._producer(
                    addresses,
                    extraction,
                    mapping,
                ),
            ),
            None,
        )

    def _pattern_claim_candidate(
        self,
        records: dict[str, NormalizedRecord],
        evidence: dict[str, EvidenceAddress],
        rule: dict[str, Any],
    ) -> tuple[SemanticCandidatePayload | None, KnownGap | None]:
        addresses = self._addresses(records, evidence, rule)
        extraction, gap = self._extract(rule, evidence, addresses)
        if gap is not None:
            return None, gap
        assert extraction is not None
        mapping = self._mapping_provenance(
            rule,
            configured_fields=(
                "epistemic_status",
                "epistemic_classification_basis",
                "evidence_role",
            ),
        )
        link = ProposedEvidenceLink(
            evidence_link_key=f"{rule['rule_key']}.reports",
            evidence_address_ref=addresses[0].evidence_address_ref,
            role=rule["evidence_role"],
        )
        return (
            SemanticCandidatePayload(
                candidate_payload_kind=(
                    "implementation_local.proposed_unscoped_statement"
                ),
                interpretation_rule_ref=rule["rule_key"],
                proposed_claim=ProposedClaim(
                    claim_key=rule["rule_key"],
                    subject_entity_key=None,
                    predicate_ref=None,
                    value=None,
                    statement=str(extraction.value),
                ),
                evidence_links=(link,),
                epistemic_context=EpistemicContext(
                    status=rule["epistemic_status"],
                    classification_basis=rule["epistemic_classification_basis"],
                ),
                applicability=self._applicability(rule),
                profile_refs=tuple(rule.get("profile_refs", ())),
                producer_provenance=self._producer(
                    addresses,
                    extraction,
                    mapping,
                ),
            ),
            None,
        )

    def _addresses(
        self,
        records: dict[str, NormalizedRecord],
        evidence: dict[str, EvidenceAddress],
        rule: dict[str, Any],
    ) -> tuple[EvidenceAddress, ...]:
        evidence_keys = tuple(rule.get("evidence_keys", ()))
        if not evidence_keys:
            raise ValueError(
                f"Semantic proposal lacks Evidence: {rule['rule_key']}"
            )
        addresses = []
        for evidence_key in evidence_keys:
            if evidence_key not in evidence:
                raise ValueError(f"Semantic Evidence missing: {evidence_key}")
            address = evidence[evidence_key]
            if address.source_key not in records:
                raise ValueError(f"Semantic Source missing: {address.source_key}")
            if records[address.source_key].record_ref != address.record_ref:
                raise ValueError(
                    "Evidence does not identify the active Source Record: "
                    f"{evidence_key}"
                )
            addresses.append(address)
        return tuple(addresses)

    def _extract(
        self,
        rule: dict[str, Any],
        evidence: dict[str, EvidenceAddress],
        addresses: tuple[EvidenceAddress, ...],
    ) -> tuple[ExtractionResult | None, KnownGap | None]:
        specification = rule.get("extraction")
        if specification is None:
            raise ValueError(
                f"Material semantic rule lacks extraction: {rule['rule_key']}"
            )
        evidence_key = specification["evidence_key"]
        if evidence_key not in evidence:
            raise ValueError(f"Extraction Evidence missing: {evidence_key}")
        try:
            extraction = self._extractor.extract(evidence[evidence_key], specification)
        except (OverflowError, ValueError):
            return (
                None,
                KnownGap(
                    gap_code="extraction_parse_error",
                    interpretation_rule_ref=rule["rule_key"],
                    detail=(
                        "Configured deterministic extraction could not parse "
                        "matched Evidence text"
                    ),
                    evidence_address_refs=tuple(
                        address.evidence_address_ref for address in addresses
                    ),
                ),
            )
        if extraction is not None:
            return extraction, None
        return (
            None,
            KnownGap(
                gap_code="extraction_no_match",
                interpretation_rule_ref=rule["rule_key"],
                detail=(
                    "Configured deterministic extraction did not match Evidence text"
                ),
                evidence_address_refs=tuple(
                    address.evidence_address_ref for address in addresses
                ),
            ),
        )

    def _semantic_value(
        self,
        extracted_value: SemanticValue,
        rule: dict[str, Any],
    ) -> tuple[SemanticValue, SemanticValue, SemanticValue]:
        value_map = rule.get("semantic_value_map")
        if not value_map:
            return extracted_value, None, None
        mapping_key = str(extracted_value)
        if mapping_key not in value_map:
            raise ValueError(
                f"No semantic value mapping for {mapping_key!r} in "
                f"{rule['rule_key']}"
            )
        mapped_value = value_map[mapping_key]
        return mapped_value, extracted_value, mapped_value

    def _candidate_evidence_links(
        self,
        evidence: dict[str, EvidenceAddress],
        subject_key: str,
        link_rules: list[dict[str, Any]],
    ) -> tuple[ProposedEvidenceLink, ...]:
        result = []
        for rule in link_rules:
            configured_subject_key = rule.get("subject_key", rule.get("claim_key"))
            if configured_subject_key != subject_key:
                continue
            address = evidence[rule["evidence_key"]]
            result.append(
                ProposedEvidenceLink(
                    evidence_link_key=rule["rule_key"],
                    evidence_address_ref=address.evidence_address_ref,
                    role=rule["role"],
                )
            )
        return tuple(result)

    def _producer(
        self,
        addresses: tuple[EvidenceAddress, ...],
        extraction: ExtractionResult | None,
        mapping: SemanticMappingProvenance,
    ) -> ProducerProvenance:
        return ProducerProvenance(
            producer_ref=self.producer_ref,
            producer_version=self.producer_version,
            method="deterministic_evidence_interpretation",
            evidence=tuple(
                EvidenceProvenance(
                    source_key=address.source_key,
                    source_ref=address.source_ref,
                    snapshot_ref=address.snapshot_ref,
                    record_ref=address.record_ref,
                    evidence_address_ref=address.evidence_address_ref,
                )
                for address in addresses
            ),
            extraction=extraction.provenance if extraction is not None else None,
            semantic_mapping=mapping,
        )

    def _mapping_provenance(
        self,
        rule: dict[str, Any],
        *,
        configured_fields: Iterable[str],
        value_mapping_from: SemanticValue = None,
        value_mapping_to: SemanticValue = None,
    ) -> SemanticMappingProvenance:
        return SemanticMappingProvenance(
            interpretation_rule_ref=rule["rule_key"],
            configured_fields=tuple(configured_fields),
            value_mapping_from=value_mapping_from,
            value_mapping_to=value_mapping_to,
        )

    def _applicability(self, rule: dict[str, Any]) -> Applicability:
        applicability = rule.get("applicability", {})
        return Applicability(
            context_refs=tuple(applicability.get("context_refs", ())),
            conditions=tuple(applicability.get("conditions", ())),
        )

    def _collect(
        self,
        candidate: SemanticCandidatePayload | None,
        gap: KnownGap | None,
        candidates: list[SemanticCandidatePayload],
        gaps: list[KnownGap],
    ) -> None:
        if candidate is not None:
            candidates.append(candidate)
        if gap is not None:
            gaps.append(gap)
