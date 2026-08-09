from __future__ import annotations

from pathlib import Path

import pytest

from cp_knowledge_tools.platform.hashing import sha256_text
from cp_knowledge_tools.semantics import RuleBasedSemanticInterpreter
from cp_knowledge_tools.sources.models import EvidenceAddress, SourceRecord


def _record() -> SourceRecord:
    return SourceRecord(
        source_key="status",
        path=Path("synthetic-status.txt"),
        source_ref="SRC-STATUS",
        snapshot_ref="SNAP-STATUS",
        record_ref="REC-STATUS",
        source_time="2024-09-06T15:30:00+02:00",
        media_type="text/plain",
        title="Synthetic status",
        raw_sha256="synthetic",
        raw_html="",
        normalized_text="Synthetic status",
        captured_at="2026-08-10T00:00:00+02:00",
    )


def _evidence(key: str, text: str) -> EvidenceAddress:
    content_hash = sha256_text(text)
    return EvidenceAddress(
        evidence_address_ref=f"EVA-{key}-{content_hash[:8]}",
        source_key="status",
        source_ref="SRC-STATUS",
        snapshot_ref="SNAP-STATUS",
        record_ref="REC-STATUS",
        selector={
            "selector_type": "text_quote",
            "selector_version": "test",
            "selector_value": "context-only",
            "target_type": "source_passage",
        },
        content_hash=content_hash,
        text=text,
        restricted=False,
    )


def _claim_rule(
    *,
    rule_key: str,
    evidence_key: str,
    predicate_ref: str,
    pattern: str,
    parser: str,
    epistemic_status: str = "reported",
) -> dict:
    return {
        "rule_key": rule_key,
        "subject_entity_key": "subject",
        "predicate_ref": predicate_ref,
        "evidence_keys": [evidence_key],
        "extraction": {
            "evidence_key": evidence_key,
            "pattern": pattern,
            "parser": parser,
        },
        "epistemic_status": epistemic_status,
        "epistemic_classification_basis": "explicit_test_interpretation_rule",
    }


def _claims(result) -> list:
    return [
        candidate.proposed_claim
        for candidate in result.candidate_payloads
        if candidate.proposed_claim is not None
    ]


@pytest.mark.parametrize(
    ("evidence_text", "expected"),
    [
        ("Team training Starts on 26 September 2024.", "2024-09-26"),
        ("Team training Starts on 27 September 2024.", "2024-09-27"),
    ],
)
def test_date_candidate_changes_when_evidence_changes(
    evidence_text: str,
    expected: str,
) -> None:
    rule = _claim_rule(
        rule_key="training_date",
        evidence_key="training",
        predicate_ref="example.training_start",
        pattern=r"Starts on (?P<value>\d{1,2} [A-Za-z]+ \d{4})",
        parser="date",
    )

    result = RuleBasedSemanticInterpreter().interpret(
        {"status": _record()},
        {"training": _evidence("training", evidence_text)},
        {"claims": [rule]},
    )

    claim = _claims(result)[0]
    assert claim.value == expected
    assert claim.predicate_ref == "example.training_start"


@pytest.mark.parametrize(
    ("evidence_text", "expected"),
    [
        ("Capacity The pilot is limited to 16 students.", 16),
        ("Capacity The pilot is limited to 17 students.", 17),
    ],
)
def test_integer_candidate_changes_when_evidence_changes(
    evidence_text: str,
    expected: int,
) -> None:
    rule = _claim_rule(
        rule_key="capacity",
        evidence_key="capacity",
        predicate_ref="example.capacity",
        pattern=r"limited to (?P<value>\d+) students",
        parser="integer",
    )

    result = RuleBasedSemanticInterpreter().interpret(
        {"status": _record()},
        {"capacity": _evidence("capacity", evidence_text)},
        {"claims": [rule]},
    )

    assert _claims(result)[0].value == expected


def test_missing_extraction_emits_gap_and_no_stale_candidate() -> None:
    rule = _claim_rule(
        rule_key="capacity",
        evidence_key="capacity",
        predicate_ref="example.capacity",
        pattern=r"limited to (?P<value>\d+) students",
        parser="integer",
    )

    result = RuleBasedSemanticInterpreter().interpret(
        {"status": _record()},
        {"capacity": _evidence("capacity", "Capacity remains under review.")},
        {"claims": [rule]},
    )

    assert _claims(result) == []
    assert len(result.known_gaps) == 1
    assert result.known_gaps[0].gap_code == "extraction_no_match"
    assert result.known_gaps[0].interpretation_rule_ref == "capacity"


def test_reported_statement_is_not_automatically_confirmed() -> None:
    rule = _claim_rule(
        rule_key="reported_capacity",
        evidence_key="capacity",
        predicate_ref="example.capacity",
        pattern=r"around (?P<value>\d+) students",
        parser="integer",
    )
    rules = {
        "claims": [rule],
        "evidence_links": [
            {
                "rule_key": "capacity_report",
                "claim_key": "reported_capacity",
                "evidence_key": "capacity",
                "role": "reports_statement",
            }
        ],
    }

    result = RuleBasedSemanticInterpreter().interpret(
        {"status": _record()},
        {"capacity": _evidence("capacity", "I estimate around 20 students.")},
        rules,
    )

    candidate = result.candidate_payloads[0]
    assert candidate.epistemic_context is not None
    assert candidate.epistemic_context.status == "reported"
    assert candidate.epistemic_context.status != "confirmed"
    assert [link.role for link in candidate.evidence_links] == [
        "reports_statement"
    ]


def test_competing_values_survive_as_separate_candidates() -> None:
    earlier = _claim_rule(
        rule_key="training_earlier",
        evidence_key="earlier",
        predicate_ref="example.training_start",
        pattern=r"start on (?P<value>\d{1,2} [A-Za-z]+ \d{4})",
        parser="date",
    )
    later = _claim_rule(
        rule_key="training_later",
        evidence_key="later",
        predicate_ref="example.training_start",
        pattern=r"Starts on (?P<value>\d{1,2} [A-Za-z]+ \d{4})",
        parser="date",
        epistemic_status="confirmed",
    )

    result = RuleBasedSemanticInterpreter().interpret(
        {"status": _record()},
        {
            "earlier": _evidence(
                "earlier",
                "Internal team training could start on 19 September 2024.",
            ),
            "later": _evidence(
                "later",
                "Team training Starts on 26 September 2024.",
            ),
        },
        {"claims": [earlier, later]},
    )

    claims = _claims(result)
    assert [claim.value for claim in claims] == ["2024-09-19", "2024-09-26"]
    assert {claim.predicate_ref for claim in claims} == {"example.training_start"}


def test_candidate_provenance_separates_extraction_from_semantic_mapping() -> None:
    rule = _claim_rule(
        rule_key="capacity",
        evidence_key="capacity",
        predicate_ref="example.capacity",
        pattern=r"limited to (?P<value>\d+) students",
        parser="integer",
        epistemic_status="confirmed",
    )

    result = RuleBasedSemanticInterpreter().interpret(
        {"status": _record()},
        {"capacity": _evidence("capacity", "limited to 16 students.")},
        {"claims": [rule]},
    )

    provenance = result.candidate_payloads[0].producer_provenance
    assert provenance is not None
    assert provenance.extraction is not None
    assert provenance.extraction.extracted_text == "16"
    assert provenance.extraction.extracted_value == 16
    assert provenance.evidence[0].record_ref == "REC-STATUS"
    assert provenance.evidence[0].evidence_address_ref.startswith("EVA-capacity-")
    assert provenance.semantic_mapping.interpretation_rule_ref == "capacity"
    assert "predicate_ref" in provenance.semantic_mapping.configured_fields


def test_candidate_payload_has_no_lifecycle_or_authorization_state() -> None:
    rule = _claim_rule(
        rule_key="capacity",
        evidence_key="capacity",
        predicate_ref="example.capacity",
        pattern=r"limited to (?P<value>\d+) students",
        parser="integer",
    )
    result = RuleBasedSemanticInterpreter().interpret(
        {"status": _record()},
        {"capacity": _evidence("capacity", "limited to 16 students.")},
        {"claims": [rule]},
    )

    payload = result.candidate_payloads[0].to_dict()
    forbidden = {
        "candidate_id",
        "candidate_revision",
        "candidate_processing_state",
        "review_state",
        "canonicalization_approval",
        "publication_state",
        "policy_decision",
        "policy_permit",
    }
    assert forbidden.isdisjoint(payload)
