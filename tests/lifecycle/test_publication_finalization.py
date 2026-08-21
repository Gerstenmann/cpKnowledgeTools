from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from cp_knowledge_tools.lifecycle import (
    HashRuleBinding,
    PublicationFinalizationPlan,
    PublicationUnitBinding,
    publication_unit_knowledge_content_hash,
    publication_unit_representation_hash,
)


def _hash_rule() -> HashRuleBinding:
    return HashRuleBinding(
        algorithm="sha256",
        canonicalization_profile_ref="synthetic-json-jcs@0.1",
        approval_context_ref="synthetic_test_hash_rule_binding",
        synthetic_test_fixture=True,
    )


def _manifest() -> dict:
    return {
        "document_type": "knowledge_object_publication_unit",
        "schema_ref": "CPKS-SPEC-KM-PU@0.2",
        "template_ref": "CPKS-TPL-KM-PU@0.2",
        "semantic_model_ref": "CPKS-SPEC-KM@0.20",
        "vocabulary_set_ref": "CPKS-SPEC-KM-VOC@0.1",
        "knowledge_object_id": "KO-TEST",
        "knowledge_object_version": "0.2",
        "title": "Synthetic knowledge",
        "language": "en",
        "canonical_path": None,
        "primary_kind": "descriptive",
        "knowledge_functions": ["descriptive"],
        "applicability": {"purposes": ["testing"]},
        "profile_refs": [],
        "claims": [
            {
                "claim_ref": {"stable_id": "CLM-NEW"},
                "statement": {"value": "unchanged knowledge"},
            }
        ],
        "events": [],
        "event_participations": [],
        "evidence_links": [{"evidence_link_id": "EL-TEST"}],
        "structural_relationships": [],
        "conflict_sets": [],
        "policy_anchors": [
            {
                "policy_anchor_id": "PA-SYNTHETIC",
                "policy_refs": ["SYNTHETIC-POLICY@0.1"],
                "policy_decision_refs": ["PDEC-PLANNED"],
            }
        ],
        "cross_view_mappings": [{"mapping_id": "CVM-TEST"}],
        "human_readable": {
            "body_language": "en",
            "publication_anchor": "publication",
        },
        "review_record_refs": ["RVR-CANDIDATE"],
        "policy_decision_refs": ["PDEC-PLANNED"],
        "publication": {
            "publication_state": "unpublished",
            "publication_finalization_plan_ref": "PFP-TEST",
            "publication_record_ref": None,
            "published_at": None,
            "publisher_ref": None,
            "predecessor_publication_ref": None,
        },
        "integrity": {
            "content_hash": None,
            "cross_view_validation": {
                "status": "pass",
                "report_ref": "CONF-CROSS-VIEW",
            },
        },
    }


def _body() -> str:
    return (
        "# Synthetic knowledge\n\n"
        '<a id="details"></a>\n'
        "## Details\n\n"
        "unchanged knowledge\n\n"
        '<a id="publication"></a>\n'
        "## Review and publication\n\n"
        "Unpublished; finalization plan PFP-TEST.\n"
    )


def test_knowledge_content_hash_excludes_only_finalization_metadata() -> None:
    manifest = _manifest()
    before = publication_unit_knowledge_content_hash(manifest, _body(), _hash_rule())

    finalized = deepcopy(manifest)
    finalized["canonical_path"] = "Knowledge/Synthetic/KO-TEST@0.2.md"
    finalized["review_record_refs"].append("RVR-PUBLICATION")
    finalized["policy_decision_refs"] = ["PDEC-ACTUAL"]
    finalized["policy_anchors"][0]["policy_decision_refs"] = ["PDEC-ACTUAL"]
    finalized["publication"].update(
        {
            "publication_state": "published",
            "publication_record_ref": "PREC-PLANNED",
            "published_at": "2026-08-15T11:00:00+02:00",
            "publisher_ref": "SYNTHETIC-PUBLISHER",
        }
    )
    finalized_body = _body().replace(
        "Unpublished; finalization plan PFP-TEST.",
        "Published under PREC-PLANNED.",
    )

    after = publication_unit_knowledge_content_hash(
        finalized, finalized_body, _hash_rule()
    )
    assert before == after
    assert before.hash_scope == "publication_unit_knowledge_content"

    changed = deepcopy(finalized)
    changed["claims"][0]["statement"]["value"] = "changed knowledge"
    changed_hash = publication_unit_knowledge_content_hash(
        changed, finalized_body, _hash_rule()
    )
    assert changed_hash.value != before.value


def test_km_pu_03_hash_includes_hardening_knowledge_content() -> None:
    manifest = _manifest()
    manifest["schema_ref"] = "CPKS-SPEC-KM-PU@0.3"
    manifest["semantic_model_ref"] = "CPKS-SPEC-KM@0.21"
    manifest["template_ref"] = "CPKT-TEST-TPL-KM-PU@0.1"
    manifest["evidence_assessments"] = [{"assessment_ref": "EVA-01"}]
    manifest["temporal_constraints"] = [{"constraint_ref": "TC-01"}]
    baseline = publication_unit_knowledge_content_hash(manifest, _body(), _hash_rule())

    changed = deepcopy(manifest)
    changed["temporal_constraints"][0]["constraint_ref"] = "TC-02"
    revised = publication_unit_knowledge_content_hash(changed, _body(), _hash_rule())

    assert baseline != revised


def test_publication_unit_binds_separate_knowledge_and_prepublication_hashes() -> None:
    unit = PublicationUnitBinding.create(
        manifest=_manifest(),
        markdown_body=_body(),
        hash_rule_binding=_hash_rule(),
    )

    assert unit.content_hash.hash_scope == "publication_unit_knowledge_content"
    assert unit.prepublication_representation_hash.hash_scope == (
        "publication_unit_prepublication_representation"
    )
    assert unit.manifest["integrity"]["content_hash"] == unit.content_hash.to_dict()
    assert unit.publication_finalization_plan_ref == "PFP-TEST"
    assert unit.canonical_path is None


def test_current_publication_unit_rejects_incompatible_legacy_template() -> None:
    manifest = _manifest()
    manifest["template_ref"] = "CPKS-TPL-KM-PU@0.1"

    with pytest.raises(
        ValueError,
        match="^publication_unit_template_incompatible$",
    ):
        PublicationUnitBinding.create(
            manifest=manifest,
            markdown_body=_body(),
            hash_rule_binding=_hash_rule(),
        )


def test_representation_hashes_have_explicit_non_comparable_scopes() -> None:
    manifest = _manifest()
    prepublication = publication_unit_representation_hash(
        manifest,
        _body(),
        _hash_rule(),
        scope="publication_unit_prepublication_representation",
    )
    final = publication_unit_representation_hash(
        manifest,
        _body(),
        _hash_rule(),
        scope="publication_unit_final_representation",
    )

    assert prepublication.value == final.value
    assert prepublication.hash_scope != final.hash_scope


def test_finalization_plan_is_immutable_and_binds_all_material_context() -> None:
    unit = PublicationUnitBinding.create(
        manifest=_manifest(),
        markdown_body=_body(),
        hash_rule_binding=_hash_rule(),
    )
    plan = PublicationFinalizationPlan.create(
        publication_finalization_plan_ref="PFP-TEST",
        publication_unit=unit,
        publication_change_set_ref="PCS-TEST",
        publication_package_ref="PPK-TEST",
        canonical_path="Knowledge/Synthetic/KO-TEST@0.2.md",
        maintenance_context_ref="synthetic-test-target",
        publisher_ref="SYNTHETIC-PUBLISHER",
        executor_ref="cpknowledge.test-isolated-publication-executor@0.1",
        publication_authority_ref="synthetic_test_publication_authority",
        review_record_refs=("RVR-CANDIDATE",),
        policy_decision_refs=("PDEC-PLANNED",),
        planned_publication_record_ref="PREC-PLANNED",
        predecessor_publication_ref=None,
        finalization_method_ref="test-isolated-snapshot-pointer@0.1",
        created_by="synthetic-test-lifecycle",
        created_at="2026-08-15T10:01:00+02:00",
        hash_rule_binding=_hash_rule(),
    )

    assert plan.knowledge_content_hash == unit.content_hash
    assert (
        plan.prepublication_representation_hash
        == unit.prepublication_representation_hash
    )
    assert plan.expected_source_publication_state == "unpublished"
    assert plan.expected_source_canonical_path is None
    assert plan.target_publication_state == "published"
    assert plan.final_representation_hash_scope == (
        "publication_unit_final_representation"
    )
    assert "knowledge_content_hash_unchanged" in plan.required_postconditions
    assert plan.plan_hash.value
    with pytest.raises(FrozenInstanceError):
        plan.canonical_path = "Knowledge/Other.md"  # type: ignore[misc]

    changed = replace(plan, canonical_path="Knowledge/Other.md")
    assert changed != plan
