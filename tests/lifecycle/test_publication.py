from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from cp_knowledge_tools.lifecycle import (
    ExpectedPriorState,
    HashRuleBinding,
    KnowledgeVersionProjectionRequest,
    KnowledgeVersionProjector,
    PublicationChangeSetBuilder,
    PublicationChangeSetBuildRequest,
    PublicationFinalizationPlan,
    PublicationOperation,
    PublicationPackageBuilder,
    PublicationPackageBuildRequest,
    PublicationReviewFactory,
    PublicationReviewValidator,
    PublicationUnitBinding,
    ReviewRecord,
)
from cp_knowledge_tools.lifecycle._common import local_ref

from .test_resolution import (
    _assessment,
    _new_identity_assessment,
    _plan,
    _registered,
    _resolve,
)


def _hash_rule() -> HashRuleBinding:
    return HashRuleBinding(
        algorithm="sha256",
        canonicalization_profile_ref="synthetic_test.canonical-json@0.1",
        approval_context_ref="synthetic_test_hash_rule_binding",
        synthetic_test_fixture=True,
    )


def _resolved(
    *,
    operation: str = "add",
    resolution_type: str = "create_new_identity",
    target_ref: str = "CLM-NEW",
):
    candidate = _registered(operation=operation)
    if resolution_type == "create_new_identity":
        assessment = _new_identity_assessment(
            candidate,
            kind="claim",
            dimensions={
                "subject": "pilot",
                "predicate": "outcome",
                "object": "promising",
            },
        )
    elif resolution_type == "map_to_existing_without_new_version":
        assessment = _assessment(candidate, material_dimensions=())
    else:
        assessment = _assessment(candidate, material_dimensions=("evidence",))
    result = _resolve(
        candidate,
        assessment,
        _plan(
            resolution_type,
            target_canonical_refs=(target_ref,),
            planned_target_versions=(
                ()
                if resolution_type == "map_to_existing_without_new_version"
                else (f"{target_ref}@planned-state",)
            ),
        ),
    )
    assert result.decision is not None
    return candidate, result.decision


def _projection(decision):
    evaluation = KnowledgeVersionProjector().evaluate(
        KnowledgeVersionProjectionRequest(
            resolution_decision=decision,
            stable_knowledge_object_ref="KO-TEST",
            prior_knowledge_object_version_ref="KO-TEST@0.1",
            prior_publication_state="unpublished",
            planned_target_knowledge_object_version_ref="KO-TEST@0.2",
            material_change=True,
            same_knowledge_object_identity=True,
        )
    )
    assert evaluation.projection is not None
    return evaluation.projection


def _prior(candidate, decision, **changes: object) -> ExpectedPriorState:
    values = {
        "stable_knowledge_object_ref": "KO-TEST",
        "knowledge_object_version_ref": "KO-TEST@0.1",
        "publication_state": "unpublished",
        "stable_identity_state": "active_unpublished",
        "subject_state_refs": ("CLM-PRIOR@0.1",),
        "expected_content_hashes": (("KO-TEST@0.1", "sha256:prior"),),
        "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
        "resolution_decision_ref": decision.resolution_decision_ref,
        "required_candidate_review_refs": ("RVR-TECH", "RVR-SOURCE"),
        "profile_context_input_refs": ("PROFILE-APPLICABILITY-NONE",),
        "policy_context_input_refs": ("POLICY-CONTEXT-PUBLISH",),
        "no_competing_change_set": True,
    }
    values.update(changes)
    return ExpectedPriorState(**values)


def _operations(candidate, decision) -> tuple[PublicationOperation, ...]:
    atomic_effect_ref = candidate.lifecycle_candidate_revision_ref
    target_ref = decision.target_canonical_refs[0]
    if decision.resolution_type == "create_new_identity":
        return (
            PublicationOperation(
                operation_type="create_identity",
                subject_refs=(target_ref,),
                target_version_refs=(),
                atomic_effect_ref=atomic_effect_ref,
            ),
            PublicationOperation(
                operation_type="publish_new_version",
                subject_refs=("KO-TEST",),
                target_version_refs=("KO-TEST@0.2",),
                atomic_effect_ref=atomic_effect_ref,
            ),
        )
    return (
        PublicationOperation(
            operation_type="publish_new_version",
            subject_refs=("KO-TEST",),
            target_version_refs=("KO-TEST@0.2",),
            atomic_effect_ref=atomic_effect_ref,
        ),
    )


def _change_set(
    *,
    operation: str = "add",
    resolution_type: str = "create_new_identity",
):
    candidate, decision = _resolved(
        operation=operation,
        resolution_type=resolution_type,
    )
    request = PublicationChangeSetBuildRequest(
        candidate_revision=candidate,
        resolution_decision=decision,
        knowledge_version_projection=_projection(decision),
        operations=_operations(candidate, decision),
        expected_prior_states=(_prior(candidate, decision),),
        candidate_review_record_refs=("RVR-TECH", "RVR-SOURCE"),
        conformance_report_refs=("CONF-CORE", "CONF-CROSS-VIEW"),
        publication_finalization_plan_refs=("PFP-TEST",),
        idempotency_key="TEST-CHANGE-SET",
        rollback_or_compensation_plan_ref="COMP-STAGING-ABORT",
        created_by="synthetic-test-lifecycle",
        created_at="2026-08-15T10:00:00+02:00",
        hash_rule_binding=_hash_rule(),
    )
    evaluation = PublicationChangeSetBuilder().build(request)
    assert evaluation.change_set is not None
    return candidate, decision, evaluation.change_set


def _unit_binding() -> PublicationUnitBinding:
    return PublicationUnitBinding.create(
        manifest={
            "document_type": "knowledge_object_publication_unit",
            "schema_ref": "CPKS-SPEC-KM-PU@0.2",
            "template_ref": "CPKS-TPL-KM-PU@0.2",
            "semantic_model_ref": "CPKS-SPEC-KM@0.20",
            "vocabulary_set_ref": "CPKS-SPEC-KM-VOC@0.1",
            "knowledge_object_id": "KO-TEST",
            "knowledge_object_version": "0.2",
            "title": "Synthetic publication unit",
            "language": "en",
            "canonical_path": None,
            "primary_kind": "descriptive",
            "knowledge_functions": ["descriptive"],
            "applicability": {"purposes": ["testing"]},
            "profile_refs": [],
            "claims": [{"claim_ref": {"stable_id": "CLM-NEW"}}],
            "events": [],
            "event_participations": [],
            "evidence_links": [
                {
                    "evidence_link_id": "EL-TEST",
                    "subject_ref": {"stable_id": "CLM-NEW"},
                    "evidence_address_ref": {"stable_id": "EA-TEST"},
                    "role": "supports",
                }
            ],
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
            "review_record_refs": ["RVR-TECH", "RVR-SOURCE"],
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
        },
        markdown_body=(
            "# Synthetic publication unit\n\n"
            '<a id="details"></a>\n'
            "## Details\n\n"
            "Synthetic knowledge.\n\n"
            '<a id="publication"></a>\n'
            "## Review and publication\n\n"
            "Unpublished; finalization plan PFP-TEST.\n"
        ),
        hash_rule_binding=_hash_rule(),
    )


def _package():
    candidate, decision, change_set = _change_set()
    unit = _unit_binding()
    package_ref = local_ref(
        "PPK",
        {
            "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
            "resolution_decision_ref": decision.resolution_decision_ref,
            "change_set_version_ref": change_set.change_set_version_ref,
        },
    )
    plan = PublicationFinalizationPlan.create(
        publication_finalization_plan_ref="PFP-TEST",
        publication_unit=unit,
        publication_change_set_ref=change_set.publication_change_set_ref,
        publication_package_ref=package_ref,
        canonical_path="Knowledge/Synthetic/KO-TEST@0.2.md",
        maintenance_context_ref="synthetic-test-target",
        publisher_ref="SYNTHETIC-PUBLISHER",
        executor_ref="cpknowledge.test-isolated-publication-executor@0.1",
        publication_authority_ref="synthetic_test_publication_authority",
        review_record_refs=("RVR-TECH", "RVR-SOURCE"),
        policy_decision_refs=("PDEC-PLANNED",),
        planned_publication_record_ref="PREC-PLANNED",
        predecessor_publication_ref=None,
        finalization_method_ref="test-isolated-snapshot-pointer@0.1",
        created_by="synthetic-test-lifecycle",
        created_at="2026-08-15T10:01:00+02:00",
        hash_rule_binding=_hash_rule(),
    )
    evaluation = PublicationPackageBuilder().build(
        PublicationPackageBuildRequest(
            candidate_revision=candidate,
            resolution_decision=decision,
            change_set=change_set,
            publication_unit_binding=unit,
            publication_finalization_plan=plan,
            candidate_review_record_refs=("RVR-TECH", "RVR-SOURCE"),
            conformance_report_refs=("CONF-CORE", "CONF-CROSS-VIEW"),
            profile_refs=(),
            policy_anchor_refs=("PA-SYNTHETIC",),
            package_version="0.1",
            created_by="synthetic-test-lifecycle",
            created_at="2026-08-15T10:01:00+02:00",
            hash_rule_binding=_hash_rule(),
        )
    )
    assert evaluation.package is not None
    return candidate, decision, evaluation.package


def test_one_candidate_revision_builds_one_atomic_deterministic_change_set() -> None:
    candidate, decision, change_set = _change_set()
    _, _, repeated = _change_set()

    assert change_set == repeated
    assert change_set.candidate_ref == candidate.lifecycle_candidate_ref
    assert (
        change_set.candidate_revision_ref == candidate.lifecycle_candidate_revision_ref
    )
    assert change_set.resolution_decision_ref == decision.resolution_decision_ref
    assert {item.operation_type for item in change_set.operations} == {
        "create_identity",
        "publish_new_version",
    }
    assert {item.atomic_effect_ref for item in change_set.operations} == {
        candidate.lifecycle_candidate_revision_ref
    }
    assert change_set.atomic is True
    assert change_set.change_set_hash.value
    assert change_set.policy_decision_ref is None
    assert change_set.publication_authority_ref is None
    assert change_set.state == "awaiting_reviews"
    assert "supersede_version" not in {
        item.operation_type for item in change_set.operations
    }


def test_revise_existing_identity_publishes_new_version_without_new_identity() -> None:
    _, _, change_set = _change_set(
        operation="update_evidence_basis",
        resolution_type="revise_existing_identity",
    )

    assert [item.operation_type for item in change_set.operations] == [
        "publish_new_version"
    ]


def test_map_to_existing_without_new_version_has_no_publication_change_set() -> None:
    candidate, decision = _resolved(
        operation="update_evidence_basis",
        resolution_type="map_to_existing_without_new_version",
    )
    evaluation = PublicationChangeSetBuilder().build(
        PublicationChangeSetBuildRequest(
            candidate_revision=candidate,
            resolution_decision=decision,
            knowledge_version_projection=None,
            operations=(),
            expected_prior_states=(),
            candidate_review_record_refs=("RVR-TECH",),
            conformance_report_refs=("CONF-CORE",),
            idempotency_key="TEST-NO-MATERIAL",
            rollback_or_compensation_plan_ref=None,
            created_by="synthetic-test-lifecycle",
            created_at="2026-08-15T10:00:00+02:00",
            hash_rule_binding=_hash_rule(),
        )
    )

    assert evaluation.disposition == "not_required"
    assert evaluation.reason_code == "resolution_has_no_material_publication"
    assert evaluation.change_set is None


@pytest.mark.parametrize(
    ("case_ref", "request_change", "reason_code"),
    [
        (
            "CHANGESET-N01",
            {"additional_candidate_revision_refs": ("LCR-INDEPENDENT",)},
            "independent_candidates_cannot_share_change_set",
        ),
        (
            "CHANGESET-N02",
            {"candidate_review_record_refs": ()},
            "candidate_reviews_missing",
        ),
        (
            "CHANGESET-N03",
            {"rollback_or_compensation_plan_ref": None},
            "rollback_or_compensation_plan_missing",
        ),
    ],
)
def test_change_set_contract_failures_are_structured(
    case_ref: str,
    request_change: dict[str, object],
    reason_code: str,
) -> None:
    candidate, decision = _resolved()
    request = PublicationChangeSetBuildRequest(
        candidate_revision=candidate,
        resolution_decision=decision,
        knowledge_version_projection=_projection(decision),
        operations=_operations(candidate, decision),
        expected_prior_states=(_prior(candidate, decision),),
        candidate_review_record_refs=("RVR-TECH", "RVR-SOURCE"),
        conformance_report_refs=("CONF-CORE",),
        publication_finalization_plan_refs=("PFP-TEST",),
        idempotency_key="TEST-INVALID",
        rollback_or_compensation_plan_ref="COMP-STAGING-ABORT",
        created_by="synthetic-test-lifecycle",
        created_at="2026-08-15T10:00:00+02:00",
        hash_rule_binding=_hash_rule(),
    )
    evaluation = PublicationChangeSetBuilder().build(replace(request, **request_change))

    assert case_ref.startswith("CHANGESET-N")
    assert evaluation.disposition == "blocked"
    assert evaluation.reason_code == reason_code
    assert evaluation.change_set is None


@pytest.mark.parametrize(
    ("request_change", "reason_code"),
    [
        ({"candidate_revision": None}, "candidate_revision_missing"),
        ({"resolution_decision": None}, "resolution_decision_missing"),
    ],
)
def test_change_set_missing_primary_bindings_are_structured(
    request_change: dict[str, object],
    reason_code: str,
) -> None:
    candidate, decision = _resolved()
    request = PublicationChangeSetBuildRequest(
        candidate_revision=candidate,
        resolution_decision=decision,
        knowledge_version_projection=_projection(decision),
        operations=_operations(candidate, decision),
        expected_prior_states=(_prior(candidate, decision),),
        candidate_review_record_refs=("RVR-TECH", "RVR-SOURCE"),
        conformance_report_refs=("CONF-CORE",),
        publication_finalization_plan_refs=("PFP-TEST",),
        idempotency_key="TEST-MISSING-BINDING",
        rollback_or_compensation_plan_ref="COMP-STAGING-ABORT",
        created_by="synthetic-test-lifecycle",
        created_at="2026-08-15T10:00:00+02:00",
        hash_rule_binding=_hash_rule(),
    )

    evaluation = PublicationChangeSetBuilder().build(replace(request, **request_change))

    assert evaluation.disposition == "blocked"
    assert evaluation.reason_code == reason_code


def test_change_set_idempotency_key_rejects_different_request_fingerprint() -> None:
    candidate, decision, change_set = _change_set()
    request = PublicationChangeSetBuildRequest(
        candidate_revision=candidate,
        resolution_decision=decision,
        knowledge_version_projection=_projection(decision),
        operations=_operations(candidate, decision),
        expected_prior_states=(_prior(candidate, decision),),
        candidate_review_record_refs=("RVR-TECH", "RVR-SOURCE"),
        conformance_report_refs=("CONF-CORE", "CONF-CROSS-VIEW"),
        publication_finalization_plan_refs=("PFP-TEST",),
        idempotency_key="TEST-CHANGE-SET",
        rollback_or_compensation_plan_ref="COMP-STAGING-ABORT",
        created_by="synthetic-test-lifecycle",
        created_at="2026-08-15T10:00:00+02:00",
        hash_rule_binding=_hash_rule(),
        existing_idempotency_fingerprint=change_set.request_fingerprint,
    )
    repeated = PublicationChangeSetBuilder().build(request)
    conflict = PublicationChangeSetBuilder().build(
        replace(request, existing_idempotency_fingerprint="different-fingerprint")
    )

    assert repeated.disposition == "built"
    assert repeated.change_set == change_set
    assert conflict.disposition == "blocked"
    assert conflict.reason_code == "idempotency_conflict"


def test_candidate_and_resolution_from_different_revisions_are_blocked() -> None:
    candidate, decision = _resolved()
    other_candidate, _ = _resolved(operation="correct")
    evaluation = PublicationChangeSetBuilder().build(
        PublicationChangeSetBuildRequest(
            candidate_revision=other_candidate,
            resolution_decision=decision,
            knowledge_version_projection=_projection(decision),
            operations=_operations(candidate, decision),
            expected_prior_states=(_prior(candidate, decision),),
            candidate_review_record_refs=("RVR-TECH", "RVR-SOURCE"),
            conformance_report_refs=("CONF-CORE",),
            publication_finalization_plan_refs=("PFP-TEST",),
            idempotency_key="TEST-MISMATCH",
            rollback_or_compensation_plan_ref="COMP-STAGING-ABORT",
            created_by="synthetic-test-lifecycle",
            created_at="2026-08-15T10:00:00+02:00",
            hash_rule_binding=_hash_rule(),
        )
    )

    assert evaluation.disposition == "blocked"
    assert evaluation.reason_code == "resolution_candidate_revision_mismatch"


def test_pg_n13_correct_does_not_map_to_supersede_unpublished_baseline() -> None:
    candidate, decision = _resolved(operation="correct")
    operations = (
        *_operations(candidate, decision),
        PublicationOperation(
            operation_type="supersede_version",
            subject_refs=("KO-TEST",),
            target_version_refs=("KO-TEST@0.1",),
            atomic_effect_ref=candidate.lifecycle_candidate_revision_ref,
        ),
    )
    evaluation = PublicationChangeSetBuilder().build(
        PublicationChangeSetBuildRequest(
            candidate_revision=candidate,
            resolution_decision=decision,
            knowledge_version_projection=_projection(decision),
            operations=operations,
            expected_prior_states=(_prior(candidate, decision),),
            candidate_review_record_refs=("RVR-TECH", "RVR-SOURCE"),
            conformance_report_refs=("CONF-CORE",),
            publication_finalization_plan_refs=("PFP-TEST",),
            idempotency_key="PG-N13",
            rollback_or_compensation_plan_ref="COMP-STAGING-ABORT",
            created_by="synthetic-test-lifecycle",
            created_at="2026-08-15T10:00:00+02:00",
            hash_rule_binding=_hash_rule(),
        )
    )

    assert evaluation.disposition == "blocked"
    assert evaluation.reason_code == "unpublished_predecessor_cannot_be_superseded"


def test_publication_unit_binding_and_package_are_immutable_and_deterministic() -> None:
    candidate, decision, package = _package()
    _, _, repeated = _package()

    assert package == repeated
    assert package.candidate_revision_ref == candidate.lifecycle_candidate_revision_ref
    assert package.resolution_decision_ref == decision.resolution_decision_ref
    assert package.publication_unit_binding.publication_state == "unpublished"
    assert package.publication_unit_binding.knowledge_object_version == "0.2"
    assert package.publication_unit_binding.content_hash.value
    assert package.publication_finalization_plan.publication_finalization_plan_ref == (
        "PFP-TEST"
    )
    assert package.publication_finalization_plan.plan_hash.value
    assert package.package_hash.value
    assert package.state == "awaiting_publication_review"
    assert package.execution_performed is False
    assert package.publication_performed is False
    with pytest.raises(FrozenInstanceError):
        package.state = "published"  # type: ignore[misc]


def test_package_blocks_publication_unit_version_not_bound_by_change_set() -> None:
    candidate, decision, change_set = _change_set()
    wrong_unit = replace(_unit_binding(), knowledge_object_version="0.3")
    evaluation = PublicationPackageBuilder().build(
        PublicationPackageBuildRequest(
            candidate_revision=candidate,
            resolution_decision=decision,
            change_set=change_set,
            publication_unit_binding=wrong_unit,
            candidate_review_record_refs=("RVR-TECH", "RVR-SOURCE"),
            conformance_report_refs=("CONF-CORE",),
            profile_refs=(),
            policy_anchor_refs=("PA-SYNTHETIC",),
            package_version="0.1",
            created_by="synthetic-test-lifecycle",
            created_at="2026-08-15T10:01:00+02:00",
            hash_rule_binding=_hash_rule(),
        )
    )

    assert evaluation.disposition == "blocked"
    assert evaluation.reason_code == "publication_unit_version_resolution_mismatch"


def test_publication_review_binds_exact_package_change_set_and_unit_hashes() -> None:
    candidate, _, package = _package()
    requirement, request = PublicationReviewFactory().create(
        package,
        required_reviewer_authority="project_owner_default_human",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#10.4",),
        profile_refs=(),
    )
    record = ReviewRecord.create(
        review_request_ref=request.review_request_ref,
        review_type=request.review_type,
        subject_ref=request.subject_ref,
        subject_version=request.subject_version,
        review_scope=request.review_scope,
        reviewer_ref="SYNTHETIC-PROJECT-OWNER",
        reviewer_authority=request.required_reviewer_authority,
        result="passed",
        findings=("synthetic package binding fixture",),
        conditions=(),
        evidence_reviewed_refs=request.evidence_and_context_refs,
        rule_basis_refs=request.rule_basis_refs,
        profile_refs=request.profile_refs,
        reviewed_at="2026-08-15T10:02:00+02:00",
        synthetic_test_fixture=True,
    )
    validation = PublicationReviewValidator().validate(
        record,
        request,
        requirement,
        package,
        candidate,
    )

    assert requirement.review_type == "publication_review"
    assert requirement.subject_ref == package.publication_package_ref
    assert requirement.subject_version == package.package_version_ref
    assert validation.disposition == "accepted"
    assert validation.reason_code == "publication_review_valid"
    assert validation.synthetic_test_publication_review_fixture is True
    assert validation.policy_permit_claimed is False
    assert validation.publication_authority_claimed is False
    assert (
        f"publication_finalization_plan_hash:"
        f"{package.publication_finalization_plan.plan_hash.value}"
        in request.evidence_and_context_refs
    )
    assert (
        f"publication_unit_knowledge_content_hash:"
        f"{package.publication_unit_binding.content_hash.value}"
        in request.evidence_and_context_refs
    )
    assert (
        f"publication_unit_prepublication_representation_hash:"
        f"{package.publication_unit_binding.prepublication_representation_hash.value}"
        in request.evidence_and_context_refs
    )


def test_changed_finalization_plan_invalidates_publication_review() -> None:
    candidate, _, package = _package()
    requirement, request = PublicationReviewFactory().create(
        package,
        required_reviewer_authority="project_owner_default_human",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#10.4",),
        profile_refs=(),
    )
    record = ReviewRecord.create(
        review_request_ref=request.review_request_ref,
        review_type=request.review_type,
        subject_ref=request.subject_ref,
        subject_version=request.subject_version,
        review_scope=request.review_scope,
        reviewer_ref="SYNTHETIC-PROJECT-OWNER",
        reviewer_authority=request.required_reviewer_authority,
        result="passed",
        findings=("synthetic package binding fixture",),
        conditions=(),
        evidence_reviewed_refs=request.evidence_and_context_refs,
        rule_basis_refs=request.rule_basis_refs,
        profile_refs=request.profile_refs,
        reviewed_at="2026-08-15T10:02:00+02:00",
        synthetic_test_fixture=True,
    )
    changed_package = replace(
        package,
        publication_finalization_plan=replace(
            package.publication_finalization_plan,
            canonical_path="Knowledge/Changed/KO-TEST@0.2.md",
        ),
    )

    validation = PublicationReviewValidator().validate(
        record,
        request,
        requirement,
        changed_package,
        candidate,
    )

    assert validation.disposition == "blocked"
    assert validation.reason_code == "publication_review_stale"


def test_internally_stale_finalization_plan_invalidates_publication_review() -> None:
    candidate, _, package = _package()
    requirement, request = PublicationReviewFactory().create(
        package,
        required_reviewer_authority="project_owner_default_human",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#publication-review",),
        profile_refs=(),
    )
    record = ReviewRecord.create(
        review_request_ref=request.review_request_ref,
        review_type=request.review_type,
        subject_ref=request.subject_ref,
        subject_version=request.subject_version,
        review_scope=request.review_scope,
        reviewer_ref="SYNTHETIC-PROJECT-OWNER",
        reviewer_authority=request.required_reviewer_authority,
        result="passed",
        findings=("synthetic package binding fixture",),
        conditions=(),
        evidence_reviewed_refs=request.evidence_and_context_refs,
        rule_basis_refs=request.rule_basis_refs,
        profile_refs=request.profile_refs,
        reviewed_at="2026-08-15T10:02:00+02:00",
        synthetic_test_fixture=True,
    )
    changed_package = replace(
        package,
        publication_finalization_plan=replace(
            package.publication_finalization_plan,
            finalization_method_ref="changed-method@0.1",
        ),
    )

    validation = PublicationReviewValidator().validate(
        record,
        request,
        requirement,
        changed_package,
        candidate,
    )

    assert validation.disposition == "blocked"
    assert validation.reason_code == "publication_review_stale"


def test_materially_changed_package_invalidates_prior_publication_review() -> None:
    candidate, _, package = _package()
    requirement, request = PublicationReviewFactory().create(
        package,
        required_reviewer_authority="project_owner_default_human",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#10.4",),
        profile_refs=(),
    )
    record = ReviewRecord.create(
        review_request_ref=request.review_request_ref,
        review_type=request.review_type,
        subject_ref=request.subject_ref,
        subject_version=request.subject_version,
        review_scope=request.review_scope,
        reviewer_ref="SYNTHETIC-PROJECT-OWNER",
        reviewer_authority=request.required_reviewer_authority,
        result="passed",
        findings=("synthetic package binding fixture",),
        conditions=(),
        evidence_reviewed_refs=request.evidence_and_context_refs,
        rule_basis_refs=request.rule_basis_refs,
        profile_refs=request.profile_refs,
        reviewed_at="2026-08-15T10:02:00+02:00",
        synthetic_test_fixture=True,
    )
    changed_package = replace(
        package,
        publication_unit_binding=replace(
            package.publication_unit_binding,
            content_hash=replace(
                package.publication_unit_binding.content_hash,
                value="different-unit-hash",
            ),
        ),
    )
    validation = PublicationReviewValidator().validate(
        record,
        request,
        requirement,
        changed_package,
        candidate,
    )

    assert validation.disposition == "blocked"
    assert validation.reason_code == "publication_review_stale"


def test_changed_reviewed_change_set_hash_invalidates_publication_review() -> None:
    candidate, _, package = _package()
    requirement, request = PublicationReviewFactory().create(
        package,
        required_reviewer_authority="project_owner_default_human",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#10.4",),
        profile_refs=(),
    )
    record = ReviewRecord.create(
        review_request_ref=request.review_request_ref,
        review_type=request.review_type,
        subject_ref=request.subject_ref,
        subject_version=request.subject_version,
        review_scope=request.review_scope,
        reviewer_ref="SYNTHETIC-PROJECT-OWNER",
        reviewer_authority=request.required_reviewer_authority,
        result="passed",
        findings=("synthetic package binding fixture",),
        conditions=(),
        evidence_reviewed_refs=request.evidence_and_context_refs,
        rule_basis_refs=request.rule_basis_refs,
        profile_refs=request.profile_refs,
        reviewed_at="2026-08-15T10:02:00+02:00",
        synthetic_test_fixture=True,
    )
    changed_package = replace(
        package,
        change_set=replace(
            package.change_set,
            change_set_hash=replace(
                package.change_set.change_set_hash,
                value="different-change-set-hash",
            ),
        ),
    )

    validation = PublicationReviewValidator().validate(
        record,
        request,
        requirement,
        changed_package,
        candidate,
    )

    assert validation.disposition == "blocked"
    assert validation.reason_code == "publication_review_stale"


def test_d6_package_contains_no_execution_or_publication_record() -> None:
    _, _, package = _package()
    payload = package.to_dict()

    assert payload["execution_performed"] is False
    assert payload["publication_performed"] is False
    assert "publication_request" not in payload
    assert "publication_record" not in payload
    assert "executor_ref" not in payload
