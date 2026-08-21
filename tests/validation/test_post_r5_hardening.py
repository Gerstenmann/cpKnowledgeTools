from __future__ import annotations

from copy import deepcopy

import pytest

from cp_knowledge_tools.publication.hardening import HardeningPublicationContext
from cp_knowledge_tools.validation.hardening import HardeningContractValidator


def _payload() -> dict[str, object]:
    return {
        "claim_refs": ["CLM-A", "CLM-B", "CLM-REASON", "CLM-CURRENT"],
        "claim_relationships": [
            {
                "relationship_ref": "REL-QUALIFIES",
                "source_claim_ref": "CLM-B",
                "target_ref": "CLM-A",
                "predicate": "qualifies",
            },
            {
                "relationship_ref": "REL-RATIONALE",
                "source_claim_ref": "CLM-REASON",
                "target_ref": "CLM-A",
                "predicate": "rationale_for",
                "profile_ref": "cpks.profile.organizational-context@0.3",
                "evidence_link_ids": ["EL-REASON"],
            },
        ],
        "program_occurrences": [
            {
                "program_ref": "PRG-01",
                "occurrence_ref": "EVT-01",
                "predicate": "part_of",
            }
        ],
        "evidence_assessments": [
            {
                "assessment_ref": "EVA-01",
                "claim_ref": "CLM-A",
                "purpose": "publication_validation",
                "evidence_link_ids": ["EL-A", "EL-B"],
                "dimensions": {
                    "independence": "shared_origin",
                    "directness": "direct",
                    "source_role": "observer",
                    "formality": "formal",
                    "competence": "competent",
                    "claim_authority": "claim_authorized",
                    "specificity": "specific",
                    "temporal_proximity": "near",
                    "perspective": "operator",
                },
                "method": "explicit_assessment",
                "assessed_by": "validator:test",
                "assessed_at": "2026-08-20T10:00:00+02:00",
                "uncertainty": "none",
            }
        ],
        "temporal_constraints": [
            {
                "constraint_ref": "TC-01",
                "subject_ref": "EVT-01",
                "bound_kind": "interval",
                "lower_bound": "2024-10-01",
                "upper_bound": "2024-12-18",
                "precision": "day",
                "modality": "actual",
                "input_refs": ["EVT-PREVIOUS", "CLM-REPORT"],
                "evidence_link_ids": ["EL-REPORT"],
                "rule_ref": "RULE-01",
                "derivation_provenance": ["after_previous", "before_report"],
                "certainty": "deterministic",
                "derivation_kind": "deterministic_rule",
            }
        ],
        "conflict_compatibility_assessments": [
            {
                "assessment_ref": "CCA-01",
                "claim_refs": ["CLM-A", "CLM-B"],
                "checks": {
                    "time": True,
                    "context": True,
                    "perspective": True,
                    "observation_granularity": True,
                    "qualification": True,
                },
                "remaining_material_incompatibility": False,
                "outcome": "qualification_or_compatible_difference",
            }
        ],
        "epistemic_context": [
            {
                "claim_ref": "CLM-A",
                "epistemic_status": "reported",
                "perspective": "operator",
                "qualification_refs": ["CLM-B"],
                "evidence_assessment_refs": ["EVA-01"],
            }
        ],
        "delivery_context": {
            "primary_claim_ref": "CLM-CURRENT",
            "correction_history_refs": ["CLM-A"],
            "equivalent_unresolved_alternative_refs": [],
        },
    }


def _codes(payload: dict[str, object]) -> set[str]:
    return {
        diagnostic.code
        for diagnostic in HardeningContractValidator().validate(payload).diagnostics
    }


def test_publication_hardening_context_preserves_active_contract_fields() -> None:
    contract = HardeningPublicationContext.from_mapping(_payload())

    assert contract.to_dict()["evidence_assessments"][0]["claim_ref"] == "CLM-A"
    assert contract.to_dict()["temporal_constraints"][0]["certainty"] == (
        "deterministic"
    )
    assert contract.to_dict()["epistemic_context"][0]["epistemic_status"] == (
        "reported"
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda value: value.update({"composite_claims": [["CLM-A", "CLM-B"]]}),
            "atomic_claim_identity_collapsed",
        ),
        (
            lambda value: value["claim_relationships"][1].update(
                {"predicate": "causes"}
            ),
            "rationale_not_structured_or_causality_invented",
        ),
        (
            lambda value: value["program_occurrences"][0].update(
                {"occurrence_ref": "PRG-01"}
            ),
            "program_occurrence_identity_collapsed",
        ),
        (
            lambda value: value["evidence_assessments"][0].update(
                {"independence_basis": "source_count"}
            ),
            "independence_inferred_from_source_count",
        ),
        (
            lambda value: value["evidence_assessments"][0].update(
                {"global_score": 0.9}
            ),
            "evidence_dimensions_replaced_by_global_score",
        ),
        (
            lambda value: value["temporal_constraints"][0].update(
                {"derivation_kind": "probabilistic_inference"}
            ),
            "probabilistic_inference_marked_deterministic",
        ),
        (
            lambda value: value["conflict_compatibility_assessments"][0].update(
                {
                    "outcome": "hard_conflict",
                    "remaining_material_incompatibility": True,
                    "checks": {"time": True},
                }
            ),
            "hard_conflict_without_compatibility_checks",
        ),
        (
            lambda value: value["delivery_context"].update(
                {"equivalent_unresolved_alternative_refs": ["CLM-A"]}
            ),
            "correction_history_rendered_as_equal_alternative",
        ),
    ],
)
def test_negative_semantic_contracts_fail_closed(mutation, expected_code: str) -> None:
    payload = deepcopy(_payload())
    mutation(payload)

    assert expected_code in _codes(payload)
    with pytest.raises(ValueError, match="hardening publication context"):
        HardeningPublicationContext.from_mapping(payload)
