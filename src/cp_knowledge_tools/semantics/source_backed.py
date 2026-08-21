from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from cp_knowledge_tools.platform.hashing import stable_token
from cp_knowledge_tools.sources.models import EvidenceAddress, SourceRecord

from .hardening import (
    CompatibilityChecks,
    ConflictCompatibilityAssessment,
    ProgramOccurrenceRelationship,
    RationaleRelationship,
)

_PROGRAM_WORDS = ("programme", "program")
_PROPOSAL_WORDS = (
    "could",
    "would",
    "possible",
    "potential",
    "propose",
    "eventually",
)
_TECHNICAL_WORDS = (
    "technical",
    "setup",
    "connectivity",
    "multiplayer",
    "device",
    "troubleshooting",
    "interruptions",
    "stable",
)
_PROGRAM_LABEL = re.compile(
    r"\b(?P<label>(?:(?:broader|wider|larger)\s+)?"
    r"(?:[A-Z][\w/-]*\s+){0,4}(?:programme|program))\b"
)
_PILOT_LABEL = re.compile(
    r"\b(?P<label>(?:autumn|spring|summer|winter|internal|limited|earlier)\s+pilot)\b",
    re.IGNORECASE,
)
_CORRECTION_VALUES = re.compile(
    r"\b(?P<current>\d{1,4})\b[^.]{0,100}\bnot\s+(?P<historical>\d{1,4})\b",
    re.IGNORECASE,
)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _has_any(text: str, terms: Sequence[str]) -> bool:
    return any(term in text for term in terms)


def _score(text: str, terms: Sequence[str]) -> int:
    return sum(term in text for term in terms)


def _best_address(
    addresses: Sequence[EvidenceAddress],
    *,
    required: Sequence[str],
    preferred: Sequence[str],
    capability: str,
) -> EvidenceAddress:
    candidates = []
    for address in addresses:
        text = _normalized(address.text)
        if all(term in text for term in required):
            candidates.append((_score(text, preferred), len(text), address))
    if not candidates:
        raise ValueError(
            f"Source-backed interpretation lacks Evidence for {capability}"
        )
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _link_id(claim_ref: str, evidence_address_ref: str) -> str:
    return stable_token("EL", claim_ref, evidence_address_ref)


def _source_range(source_keys: Sequence[str]) -> str:
    parsed = []
    for key in source_keys:
        match = re.fullmatch(r"(?P<prefix>.*?)(?P<number>\d+)", key)
        if match is None:
            return f"{source_keys[0]}..{source_keys[-1]}"
        parsed.append((match.group("prefix"), int(match.group("number")), key))
    prefixes = {item[0] for item in parsed}
    numbers = sorted(item[1] for item in parsed)
    if len(prefixes) == 1 and numbers == list(range(numbers[0], numbers[-1] + 1)):
        width = max(len(str(item[1])) for item in parsed)
        prefix = parsed[0][0]
        return f"{prefix}{numbers[0]:0{width}d}..{prefix}{numbers[-1]:0{width}d}"
    return f"{source_keys[0]}..{source_keys[-1]}"


class SourceBackedSemanticInterpreter:
    """Interpret natural documentary Evidence into a bounded Post-R5 state.

    The rules use document language and Evidence passages. Source keys, paths,
    fixture roles, Golden assertions, and domain-specific identities never
    select a semantic outcome.
    """

    producer_ref = "CPKT-SOURCE-BACKED-SEMANTIC-INTERPRETER"
    producer_version = "0.1"

    def interpret(
        self,
        records: Iterable[SourceRecord],
        evidence_addresses: Iterable[EvidenceAddress],
        *,
        as_of: str,
    ) -> dict[str, Any]:
        record_list = tuple(records)
        addresses = tuple(evidence_addresses)
        if not record_list or not addresses:
            raise ValueError(
                "Source-backed interpretation requires Source and Evidence"
            )

        record_by_ref = {record.record_ref: record for record in record_list}
        if any(address.record_ref not in record_by_ref for address in addresses):
            raise ValueError(
                "Evidence Address is not bound to the supplied Source Records"
            )

        program = self._program_context(addresses)
        rationale = self._rationale(addresses, program)
        currentness = self._currentness(record_list, addresses, as_of=as_of)
        technical = self._technical_perspectives(record_by_ref, addresses)
        correction = self._correction(addresses)
        frontier = self._frontier(
            addresses,
            program=program,
            currentness=currentness,
            technical=technical,
        )
        return {
            "knowledge": {
                "program_context": program,
                "rationale": rationale,
                "currentness": currentness,
                "technical_perspectives": technical["views"],
                "compatibility_assessment": technical["assessment"],
                "specialist_limits": {
                    "universal_authority_inferred": False,
                    "school_acceptance_inferred": False,
                    "technical_failure_as_noncontinuation_cause_inferred": False,
                },
                "correction_history": correction,
            },
            "knowledge_frontier": frontier,
        }

    def _program_context(
        self,
        addresses: Sequence[EvidenceAddress],
    ) -> dict[str, Any]:
        program_evidence = _best_address(
            addresses,
            required=(),
            preferred=(*_PROGRAM_WORDS, *_PROPOSAL_WORDS, "broader", "pilot"),
            capability="proposed Program context",
        )
        program_text = program_evidence.text
        program_normalized = _normalized(program_text)
        if not _has_any(program_normalized, _PROGRAM_WORDS) or not _has_any(
            program_normalized, _PROPOSAL_WORDS
        ):
            raise ValueError("Program context is not explicitly proposal-qualified")
        label_match = _PROGRAM_LABEL.search(program_text)
        program_label = (
            label_match.group("label") if label_match else "proposed programme"
        )
        program_ref = stable_token("PRG", _normalized(program_label))

        pilot_evidence = _best_address(
            addresses,
            required=("pilot", "cycle"),
            preferred=("first practical cycle", "rather than", "permanent"),
            capability="Pilot occurrence",
        )
        pilot_match = _PILOT_LABEL.search(pilot_evidence.text)
        pilot_label = pilot_match.group("label") if pilot_match else "pilot cycle"
        pilot_cycle_ref = stable_token(
            "EVT",
            _normalized(pilot_label),
            pilot_evidence.evidence_address_ref,
        )
        relationship = ProgramOccurrenceRelationship(
            relationship_ref=stable_token(
                "REL", pilot_cycle_ref, "part_of", program_ref
            ),
            program_ref=program_ref,
            occurrence_ref=pilot_cycle_ref,
            predicate="part_of",
        )
        external_activity_ref = stable_token("ACT", program_ref, "external_competition")
        return {
            "program_ref": program_ref,
            "program_label": program_label,
            "lifecycle_status": "proposed",
            "implemented": False,
            "pilot_cycle_ref": pilot_cycle_ref,
            "pilot_cycle_label": pilot_label,
            "pilot_occurrence_kind": "activity_cycle",
            "relationship": relationship.to_dict(),
            "relationship_qualification": "proposed_model",
            "external_competition_activity": {
                "activity_ref": external_activity_ref,
                "lifecycle_status": "possible_later_activity",
                "approved_program_phase": False,
            },
            "evidence_address_refs": [
                program_evidence.evidence_address_ref,
                pilot_evidence.evidence_address_ref,
            ],
            "source_statements": [program_evidence.text, pilot_evidence.text],
        }

    def _rationale(
        self,
        addresses: Sequence[EvidenceAddress],
        program: dict[str, Any],
    ) -> dict[str, Any]:
        reason_evidence = _best_address(
            addresses,
            required=("reason",),
            preferred=(
                "internally",
                "need to understand",
                "reliably",
                "collaboration",
                "support",
            ),
            capability="source-backed Rationale",
        )
        reason_claim_ref = stable_token(
            "CLM", "rationale", reason_evidence.evidence_address_ref
        )
        target_ref = stable_token(
            "CLM", "internal_pilot_start", program["pilot_cycle_ref"]
        )
        evidence_link_id = _link_id(
            reason_claim_ref, reason_evidence.evidence_address_ref
        )
        relationship = RationaleRelationship(
            relationship_ref=stable_token(
                "REL", reason_claim_ref, "rationale_for", target_ref
            ),
            reason_claim_ref=reason_claim_ref,
            target_ref=target_ref,
            evidence_link_ids=(evidence_link_id,),
            profile_ref="cpks.profile.organizational-context@0.3",
        )
        return {
            "reason_claim_ref": reason_claim_ref,
            "statement": reason_evidence.text,
            "target_claim_ref": target_ref,
            "relationship": relationship.to_dict(),
            "evidence_link_ids": [evidence_link_id],
            "evidence_address_refs": [reason_evidence.evidence_address_ref],
        }

    def _currentness(
        self,
        records: Sequence[SourceRecord],
        addresses: Sequence[EvidenceAddress],
        *,
        as_of: str,
    ) -> dict[str, Any]:
        dated_records = [record for record in records if record.source_time]
        if not dated_records:
            raise ValueError("Currentness requires dated Source Records")
        latest = max(dated_records, key=lambda record: str(record.source_time))
        latest_addresses = [
            address for address in addresses if address.record_ref == latest.record_ref
        ]
        schedule = _best_address(
            latest_addresses,
            required=("scheduled",),
            preferred=("at the moment", "no ", *_PROGRAM_WORDS, "classroom"),
            capability="current planning status",
        )
        ownership = _best_address(
            latest_addresses,
            required=("owner",),
            preferred=("currently", "do not have", "confirmed", "slot"),
            capability="current ownership status",
        )
        commitment = _best_address(
            latest_addresses,
            required=("current commitment",),
            preferred=("external competition", "should not"),
            capability="current commitment status",
        )
        nonpermanent = _best_address(
            latest_addresses,
            required=("permanent",),
            preferred=("not intended", "later planning cycle", "again"),
            capability="non-permanent currentness qualification",
        )
        unknown_cause = _best_address(
            latest_addresses,
            required=("do not know",),
            preferred=("specific decision", "explains why", "did not develop"),
            capability="unknown historical cause",
        )
        schedule_text = _normalized(schedule.text)
        ownership_text = _normalized(ownership.text)
        commitment_text = _normalized(commitment.text)
        nonpermanent_text = _normalized(nonpermanent.text)
        if "no " not in schedule_text or not _has_any(schedule_text, _PROGRAM_WORDS):
            raise ValueError("Latest Source does not establish absent Program schedule")
        if "not aware" not in schedule_text or "classroom" not in schedule_text:
            raise ValueError(
                "Latest Source does not establish classroom rollout status"
            )
        if "not" not in commitment_text or "external competition" not in (
            commitment_text
        ):
            raise ValueError("Latest Source does not qualify external commitment")
        if "not" not in nonpermanent_text:
            raise ValueError("Permanent rejection qualification is not explicit")
        if not _has_any(ownership_text, ("do not have", "not yet clear")):
            raise ValueError("Latest Source does not establish uncertain ownership")
        return {
            "as_of": as_of,
            "source_time": latest.source_time,
            "currentness": "verified_current",
            "historical_material_status": "historical_only",
            "ongoing_program": False,
            "classroom_rollout_currently_planned": False,
            "external_competition_current_commitment": False,
            "ownership_status": "unconfirmed",
            "programme_slot_status": "not_scheduled",
            "current_lead": False,
            "permanent_rejection": False,
            "historical_cause_established": False,
            "future_reconsideration_possible": True,
            "evidence_address_refs": [
                schedule.evidence_address_ref,
                ownership.evidence_address_ref,
                commitment.evidence_address_ref,
                nonpermanent.evidence_address_ref,
                unknown_cause.evidence_address_ref,
            ],
            "unknown_cause_statement": unknown_cause.text,
        }

    def _technical_perspectives(
        self,
        records: dict[str, SourceRecord],
        addresses: Sequence[EvidenceAddress],
    ) -> dict[str, Any]:
        grouped: dict[str, list[EvidenceAddress]] = defaultdict(list)
        for address in addresses:
            text = _normalized(address.text)
            if _score(text, _TECHNICAL_WORDS) >= 2:
                grouped[address.record_ref].append(address)

        views = []
        compatibility_qualification_found = False
        for record_ref, items in grouped.items():
            record = records[record_ref]
            document_text = _normalized(record.normalized_text)
            title = _normalized(record.title)
            evidence = max(
                items,
                key=lambda item: _score(_normalized(item.text), _TECHNICAL_WORDS),
            )
            if "evaluation summary" in title or "across the group" in document_text:
                perspective = "aggregate_evaluation"
                granularity = "cycle_summary"
            elif "facilitator" in title or "facilitator note" in document_text:
                perspective = "facilitator_observation"
                granularity = "incident_observation"
            elif "my experience" in document_text and _has_any(
                document_text, ("courses", "camps", "operations")
            ):
                perspective = "external_operations_practitioner"
                granularity = "cross_session_operational_observation"
            else:
                perspective = "technical_observer"
                granularity = "bounded_technical_observation"
            claim_ref = stable_token(
                "CLM", "technical_observation", evidence.evidence_address_ref
            )
            views.append(
                {
                    "claim_ref": claim_ref,
                    "statement": evidence.text,
                    "perspective": perspective,
                    "observation_granularity": granularity,
                    "qualification": "source_bounded_observation",
                    "evidence_link_ids": [
                        _link_id(claim_ref, evidence.evidence_address_ref)
                    ],
                    "evidence_address_refs": [evidence.evidence_address_ref],
                    "source_time": record.source_time,
                }
            )
            if (
                "overall" in document_text
                and "while" in document_text
                and _has_any(document_text, ("individual", "incidents"))
            ) or ("alongside" in document_text and "rather than" in document_text):
                compatibility_qualification_found = True

        if len({item["perspective"] for item in views}) < 3:
            raise ValueError(
                "Source-backed technical Evidence lacks three distinct perspectives"
            )
        if not compatibility_qualification_found:
            raise ValueError(
                "Source-backed technical Evidence lacks a compatibility qualification"
            )
        views.sort(key=lambda item: (str(item["source_time"]), item["claim_ref"]))
        assessment = ConflictCompatibilityAssessment(
            assessment_ref=stable_token("CCA", *(item["claim_ref"] for item in views)),
            claim_refs=tuple(item["claim_ref"] for item in views),
            checks=CompatibilityChecks.all_checked(),
            remaining_material_incompatibility=False,
            outcome="qualification_or_compatible_difference",
        )
        return {"views": views, "assessment": assessment.to_dict()}

    def _correction(
        self,
        addresses: Sequence[EvidenceAddress],
    ) -> dict[str, Any]:
        correction_address = None
        value_match = None
        for address in addresses:
            text = _normalized(address.text)
            match = _CORRECTION_VALUES.search(text)
            if "correction" in text and match is not None:
                correction_address = address
                value_match = match
                break
        if correction_address is None or value_match is None:
            raise ValueError("Source-backed correction lineage is missing")
        primary_value = int(value_match.group("current"))
        historical_value = int(value_match.group("historical"))
        confirmation_refs = [
            address.evidence_address_ref
            for address in addresses
            if address.evidence_address_ref != correction_address.evidence_address_ref
            and "participant" in _normalized(address.text)
            and re.search(rf"\b{primary_value}\b", address.text)
        ]
        historical_claim_ref = stable_token(
            "CLM", "historical_capacity", historical_value
        )
        primary_claim_ref = stable_token("CLM", "corrected_capacity", primary_value)
        return {
            "primary_claim_ref": primary_claim_ref,
            "primary_value": primary_value,
            "historical_claim_ref": historical_claim_ref,
            "historical_value": historical_value,
            "relationship": {
                "relationship_ref": stable_token(
                    "REL", primary_claim_ref, "corrects", historical_claim_ref
                ),
                "predicate": "corrects",
                "source_claim_ref": primary_claim_ref,
                "target_claim_ref": historical_claim_ref,
            },
            "historical_claim_preserved": True,
            "evidence_address_refs": [
                correction_address.evidence_address_ref,
                *confirmation_refs,
            ],
        }

    def _frontier(
        self,
        addresses: Sequence[EvidenceAddress],
        *,
        program: dict[str, Any],
        currentness: dict[str, Any],
        technical: dict[str, Any],
    ) -> dict[str, Any]:
        uncertainty = _best_address(
            addresses,
            required=("do not know",),
            preferred=("specific decision", "explains why", "did not develop"),
            capability="non-continuation Knowledge Frontier",
        )
        actual_cause_evidence = []
        for address in addresses:
            text = _normalized(address.text)
            targets_noncontinuation = _has_any(
                text,
                ("not continued", "did not develop", "stopped", "ended because"),
            )
            causal = _has_any(text, ("because", "due to", "reason was"))
            uncertain = _has_any(
                text, ("do not know", "not clear", "may", "might", "could")
            )
            if targets_noncontinuation and causal and not uncertain:
                actual_cause_evidence.append(address.evidence_address_ref)
        if actual_cause_evidence:
            raise ValueError(
                "Source corpus establishes a non-continuation cause; "
                "no Frontier remains"
            )
        checked_refs = list(
            dict.fromkeys(
                [
                    *program["evidence_address_refs"],
                    *currentness["evidence_address_refs"],
                    *(
                        evidence_ref
                        for view in technical["views"]
                        for evidence_ref in view["evidence_address_refs"]
                    ),
                ]
            )
        )
        frontier_ref = stable_token(
            "KF", program["program_ref"], uncertainty.evidence_address_ref
        )
        return {
            "knowledge_frontier_ref": frontier_ref,
            "status": "unresolved",
            "remaining_gap": (
                "The actual reason the proposed programme was not continued is "
                "not established by the available documentary Evidence."
            ),
            "actual_noncontinuation_reason_known": False,
            "source_explicitly_marks_uncertainty": True,
            "uncertainty_evidence_address_ref": uncertainty.evidence_address_ref,
            "evidence_checked_refs": checked_refs,
            "possible_factors": [
                {
                    "factor": "ownership_or_programme_slot",
                    "causal_status": "not_established",
                    "evidence_address_refs": currentness["evidence_address_refs"],
                },
                {
                    "factor": "technical_operational_requirements",
                    "causal_status": "not_established",
                    "evidence_address_refs": [
                        evidence_ref
                        for view in technical["views"]
                        for evidence_ref in view["evidence_address_refs"]
                    ],
                },
            ],
            "prohibited_inferences": [
                "technical_failure_caused_noncontinuation",
                "missing_adviser_caused_noncontinuation",
                "missing_interest_caused_noncontinuation",
                "institution_rejected_programme",
                "specialist_failed_to_continue_programme",
                "personnel_change_caused_noncontinuation",
            ],
        }


def source_accounting(
    records: Iterable[SourceRecord],
    evidence_addresses: Iterable[EvidenceAddress],
) -> dict[str, Any]:
    """Build a deterministic, non-authoritative accounting projection."""

    record_list = sorted(records, key=lambda item: item.source_key)
    evidence_by_record: dict[str, list[str]] = defaultdict(list)
    for address in evidence_addresses:
        evidence_by_record[address.record_ref].append(address.evidence_address_ref)
    source_keys = [record.source_key for record in record_list]
    return {
        "input_range": _source_range(source_keys),
        "input_count": len(record_list),
        "runtime_semantic_annotations_used": False,
        "records": [
            {
                "source_key": record.source_key,
                "source_ref": record.source_ref,
                "snapshot_ref": record.snapshot_ref,
                "record_ref": record.record_ref,
                "source_time": record.source_time,
                "title": record.title,
                "raw_sha256": record.raw_sha256,
                "evidence_address_refs": evidence_by_record[record.record_ref],
            }
            for record in record_list
        ],
    }
