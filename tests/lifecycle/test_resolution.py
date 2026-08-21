from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from cp_knowledge_tools.lifecycle import (
    RESOLUTION_TYPES,
    IdentitySnapshot,
    KnowledgeVersionProjectionRequest,
    KnowledgeVersionProjector,
    LifecycleCandidateRegistrar,
    ResolutionAuthority,
    ResolutionEngine,
    ResolutionPlan,
    ResolutionRequest,
    SameObjectAssessmentRequest,
    SameObjectEvaluator,
)
from cp_knowledge_tools.semantics import ChangeCandidateRevision

CORE_RULES = ("CPKS-SPEC-KM@0.20#9",)
KPR_RULES = ("CPKS-SPEC-KPR@0.3#8",)


def _change_candidate(
    *,
    operation: str = "add",
    semantic_unit_kind: str = "claim",
    payload: str = '{"object":"strong","predicate":"engagement","subject":"pilot"}',
    prior_payload: str | None = None,
    revision_ref: str = "CCR-TEST-REV-1",
    producer_provenance: tuple[str, ...] = ("synthetic-producer",),
) -> ChangeCandidateRevision:
    return ChangeCandidateRevision(
        change_candidate_ref="CCL-TEST",
        candidate_revision_ref=revision_ref,
        candidate_revision="local-test",
        semantic_unit_kind=semantic_unit_kind,
        target_refs=("KO-TEST",),
        target_version_refs=("KO-TEST@0.1",),
        prior_state_refs=("PRIOR-TEST",),
        relevant_state_summary="synthetic prior state",
        semantic_change_operation=operation,
        proposed_semantic_effect="synthetic semantic effect",
        _proposed_semantic_payload_json=payload,
        _prior_semantic_payload_json=prior_payload,
        source_finding_refs=("FND-TEST",),
        source_refs=("SOURCE-TEST",),
        evidence_refs=("EVIDENCE-TEST",),
        time_scope=(),
        event_time_values=(),
        event_time_unknown=False,
        epistemic_context=(),
        known_conflicts=(),
        relevant_constraints=(),
        preservation_constraints=(),
        prohibited_inferences=(),
        unresolved_identity_questions=(),
        producer_provenance=producer_provenance,
        operation_policy_ref="TEST-OPERATION-POLICY",
    )


def _registered(**candidate_kwargs: object):
    return LifecycleCandidateRegistrar().register(
        _change_candidate(**candidate_kwargs),
        registered_by="synthetic-lifecycle-test",
        registered_at="2026-08-15T02:00:00+02:00",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#3-4",),
        idempotency_key="TEST-REGISTRATION",
    )


def _snapshot(
    *,
    kind: str = "claim",
    identity_ref: str | None = "CLM-TEST",
    dimensions: dict[str, object] | None = None,
) -> IdentitySnapshot:
    return IdentitySnapshot.from_dimensions(
        semantic_unit_kind=kind,
        identity_ref=identity_ref,
        dimensions=dimensions
        or {"subject": "pilot", "predicate": "engagement", "object": "strong"},
        evidence_refs=("IDENTITY-EVIDENCE",),
    )


def _assessment(
    candidate=None,
    *,
    prior: IdentitySnapshot | None = None,
    proposed: IdentitySnapshot | None = None,
    material_dimensions: tuple[str, ...] = ("evidence",),
    unresolved: tuple[str, ...] = (),
):
    candidate = candidate or _registered()
    return SameObjectEvaluator().evaluate(
        SameObjectAssessmentRequest(
            candidate_revision=candidate,
            prior_snapshot=prior if prior is not None else _snapshot(),
            proposed_snapshot=proposed if proposed is not None else _snapshot(),
            existing_canonical_refs=("CLM-TEST",),
            prior_identity_evidence_refs=("IDENTITY-EVIDENCE",),
            assessed_dimensions=("subject", "predicate", "object"),
            material_delta_dimensions=material_dimensions,
            rationale="synthetic Core same-object assessment",
            rule_basis_refs=CORE_RULES,
            unresolved_identity_questions=unresolved,
        )
    )


def _authority(**changes: object) -> ResolutionAuthority:
    values = {
        "authority_ref": "SCENARIO-OWNER-DECISION-BASIS",
        "authority_context": "synthetic_test_projection",
        "authority_kind": "scenario_local_owner_decision_basis",
        "authorized_actions": ("resolve_candidate_identity",),
        "decision_basis_refs": ("GT-S2K-ENRICHMENT-01@0.8",),
        "decided_at": "2026-08-15T02:00:00+02:00",
    }
    values.update(changes)
    return ResolutionAuthority(**values)


def _plan(
    resolution_type: str = "revise_existing_identity",
    **changes: object,
) -> ResolutionPlan:
    values = {
        "resolution_type": resolution_type,
        "target_canonical_refs": ("CLM-TEST",),
        "planned_target_versions": ("CLM-TEST@state-2",),
        "identity_rationale": "explicit Core-based synthetic rationale",
    }
    values.update(changes)
    return ResolutionPlan(**values)


def _resolve(candidate=None, assessment=None, plan=None, authority=None):
    candidate = candidate or _registered()
    assessment = assessment if assessment is not None else _assessment(candidate)
    return ResolutionEngine().evaluate(
        ResolutionRequest(
            candidate_revision=candidate,
            same_object_assessment=assessment,
            plan=plan or _plan(),
            authority=authority or _authority(),
        )
    )


def test_lifecycle_registration_preserves_d4_lineage_and_is_idempotent() -> None:
    first = _registered()
    second = _registered()

    assert first == second
    assert first.lifecycle_candidate_ref != first.source_change_candidate_ref
    assert first.source_change_candidate_ref == "CCL-TEST"
    assert first.source_change_candidate_revision_ref == "CCR-TEST-REV-1"
    assert first.source_finding_refs == ("FND-TEST",)
    assert first.evidence_refs == ("EVIDENCE-TEST",)
    assert first.non_canonical is True
    assert first.contract_version == "0.1"


def test_claim_same_proposition_with_new_evidence_keeps_identity() -> None:
    assessment = _assessment(material_dimensions=("evidence",))

    assert assessment.disposition == "assessed"
    assert assessment.result == "same_identity"


def test_claim_material_value_change_requires_new_identity() -> None:
    assessment = _assessment(
        prior=_snapshot(
            dimensions={"subject": "pilot", "predicate": "capacity", "object": 16}
        ),
        proposed=_snapshot(
            identity_ref=None,
            dimensions={"subject": "pilot", "predicate": "capacity", "object": 14},
        ),
        material_dimensions=("object",),
    )

    assert assessment.result == "new_identity_required"
    assert "object" in assessment.changed_identity_dimensions


def test_event_planned_to_actual_same_occurrence_keeps_event_identity() -> None:
    candidate = _registered(
        operation="temporal_progression", semantic_unit_kind="event"
    )
    prior = _snapshot(
        kind="event",
        identity_ref="EVT-PILOT",
        dimensions={"occurrence_key": "pilot-2024", "state": "planned"},
    )
    proposed = _snapshot(
        kind="event",
        identity_ref="EVT-PILOT",
        dimensions={"occurrence_key": "pilot-2024", "state": "actual"},
    )
    assessment = _assessment(
        candidate,
        prior=prior,
        proposed=proposed,
        material_dimensions=("state",),
    )

    assert assessment.result == "same_identity"


def test_different_event_occurrence_requires_new_identity() -> None:
    candidate = _registered(
        operation="temporal_progression", semantic_unit_kind="event"
    )
    assessment = _assessment(
        candidate,
        prior=_snapshot(
            kind="event",
            identity_ref="EVT-ONE",
            dimensions={"occurrence_key": "cycle-1"},
        ),
        proposed=_snapshot(
            kind="event",
            identity_ref=None,
            dimensions={"occurrence_key": "cycle-2"},
        ),
        material_dimensions=("occurrence_key",),
    )

    assert assessment.result == "new_identity_required"


def test_new_event_preserves_unknown_exact_time_as_assessed_but_not_changed() -> None:
    candidate = _registered(operation="add", semantic_unit_kind="event")
    assessment = SameObjectEvaluator().evaluate(
        SameObjectAssessmentRequest(
            candidate_revision=candidate,
            prior_snapshot=None,
            proposed_snapshot=_snapshot(
                kind="event",
                identity_ref=None,
                dimensions={
                    "occurrence_key": "evaluation-after-cycle",
                    "exact_time": None,
                },
            ),
            existing_canonical_refs=(),
            prior_identity_evidence_refs=(),
            assessed_dimensions=("occurrence_key", "exact_time"),
            material_delta_dimensions=("occurrence_key",),
            rationale="synthetic new event with unknown exact time",
            rule_basis_refs=CORE_RULES,
        )
    )

    assert assessment.result == "new_identity_required"
    assert "exact_time" in assessment.assessed_dimensions
    assert "exact_time" not in assessment.changed_identity_dimensions


def test_unknown_identity_fails_closed_without_resolution() -> None:
    candidate = _registered()
    assessment = _assessment(candidate, unresolved=("target_identity_ambiguous",))
    result = _resolve(candidate, assessment)

    assert assessment.result == "ambiguous_or_unresolved"
    assert result.disposition == "unresolved"
    assert result.reason_code == "same_object_assessment_unresolved"
    assert result.decision is None


def _new_identity_assessment(candidate, *, kind: str, dimensions: dict[str, object]):
    return SameObjectEvaluator().evaluate(
        SameObjectAssessmentRequest(
            candidate_revision=candidate,
            prior_snapshot=None,
            proposed_snapshot=_snapshot(
                kind=kind,
                identity_ref=None,
                dimensions=dimensions,
            ),
            existing_canonical_refs=(),
            prior_identity_evidence_refs=("IDENTITY-EVIDENCE",),
            assessed_dimensions=tuple(sorted(dimensions)),
            material_delta_dimensions=tuple(sorted(dimensions)),
            rationale="new semantic subject after explicit Core assessment",
            rule_basis_refs=CORE_RULES,
        )
    )


@pytest.mark.parametrize(
    (
        "resolution_ref",
        "operation",
        "kind",
        "same_occurrence",
        "resolution_type",
        "target_ref",
    ),
    [
        (
            "RES-D01",
            "temporal_progression",
            "event",
            True,
            "revise_existing_identity",
            "EVT-INTERNAL-PILOT",
        ),
        ("RES-D02", "add", "claim", False, "create_new_identity", "CLM-D02"),
        ("RES-D03", "add", "claim", False, "create_new_identity", "CLM-D03"),
        ("RES-D04", "add", "claim", False, "create_new_identity", "CLM-D04"),
        ("RES-D05", "add", "claim", False, "create_new_identity", "CLM-D05"),
        (
            "RES-D06",
            "temporal_progression",
            "claim",
            False,
            "create_new_identity",
            "CLM-D06",
        ),
        (
            "RES-D07",
            "temporal_progression",
            "claim",
            False,
            "create_new_identity",
            "CLM-D07",
        ),
        (
            "RES-D08",
            "temporal_progression",
            "claim",
            False,
            "create_new_identity",
            "CLM-D08",
        ),
        ("RES-D09", "add", "event", False, "create_new_identity", "EVT-D09"),
    ],
)
def test_res_d01_through_d09_golden_resolution_matrix(
    resolution_ref: str,
    operation: str,
    kind: str,
    same_occurrence: bool,
    resolution_type: str,
    target_ref: str,
) -> None:
    candidate = _registered(operation=operation, semantic_unit_kind=kind)
    if same_occurrence:
        assessment = _assessment(
            candidate,
            prior=_snapshot(
                kind="event",
                identity_ref=target_ref,
                dimensions={"event_ref": target_ref, "state": "planned"},
            ),
            proposed=_snapshot(
                kind="event",
                identity_ref=target_ref,
                dimensions={"event_ref": target_ref, "state": "actual"},
            ),
            material_dimensions=("state",),
        )
    else:
        dimensions = (
            {"occurrence_key": f"{resolution_ref}-occurrence"}
            if kind == "event"
            else {
                "subject": "pilot",
                "predicate": f"{resolution_ref}-predicate",
                "object": f"{resolution_ref}-value",
            }
        )
        assessment = _new_identity_assessment(
            candidate,
            kind=kind,
            dimensions=dimensions,
        )
    result = _resolve(
        candidate,
        assessment,
        _plan(
            resolution_type,
            target_canonical_refs=(target_ref,),
            planned_target_versions=(f"{target_ref}@planned-state",),
            identity_rationale=f"{resolution_ref} explicit Core assessment",
        ),
    )

    assert result.disposition == "resolved"
    assert result.decision is not None
    assert result.decision.resolution_type == resolution_type
    assert result.decision.target_canonical_refs == (target_ref,)
    assert result.decision.same_object_assessment_ref == (
        assessment.same_object_assessment_ref
    )


@pytest.mark.parametrize(
    ("case_ref", "operation", "assessment_kind", "resolution_type"),
    [
        ("RES-E01", "update_evidence_basis", "same", "revise_existing_identity"),
        (
            "RES-NM01",
            "update_evidence_basis",
            "no_material",
            "map_to_existing_without_new_version",
        ),
        ("RES-CF01", "register_conflict", "new", "create_new_identity"),
        ("RES-CR01", "correct", "new", "create_new_identity"),
        ("RES-CR02", "update_evidence_basis", "same", "revise_existing_identity"),
        ("RES-EP01", "update_epistemic_state", "same", "revise_existing_identity"),
    ],
)
def test_resolution_special_cases(
    case_ref: str,
    operation: str,
    assessment_kind: str,
    resolution_type: str,
) -> None:
    candidate = _registered(operation=operation)
    if assessment_kind == "new":
        assessment = _assessment(
            candidate,
            prior=_snapshot(
                dimensions={"subject": "pilot", "predicate": "capacity", "object": 16}
            ),
            proposed=_snapshot(
                identity_ref=None,
                dimensions={"subject": "pilot", "predicate": "capacity", "object": 14},
            ),
            material_dimensions=("object",),
        )
        target = f"CLM-{case_ref}-NEW"
    else:
        assessment = _assessment(
            candidate,
            material_dimensions=(
                () if assessment_kind == "no_material" else ("evidence",)
            ),
        )
        target = "CLM-TEST"
    result = _resolve(
        candidate,
        assessment,
        _plan(
            resolution_type,
            target_canonical_refs=(target,),
            planned_target_versions=(
                ()
                if resolution_type == "map_to_existing_without_new_version"
                else (f"{target}@state-2",)
            ),
            overwrites_existing_claim=False,
        ),
    )

    assert result.disposition == "resolved", case_ref
    assert result.decision is not None
    assert result.decision.resolution_type == resolution_type


def test_active_kpr_resolution_type_set_is_not_reinvented() -> None:
    assert RESOLUTION_TYPES == {
        "create_new_identity",
        "revise_existing_identity",
        "map_to_existing_without_new_version",
        "merge_into_existing",
        "merge_into_new_identity",
        "split_into_new_identities",
        "retract_existing_version",
        "close_without_canonicalization",
    }


@pytest.mark.parametrize(
    ("ref", "operation", "resolution_type", "reason_code"),
    [
        (
            "RES-N01",
            "add",
            "create_new_identity",
            "block_same_object_assessment_required",
        ),
        (
            "RES-N02",
            "correct",
            "revise_existing_identity",
            "block_same_object_assessment_required",
        ),
        (
            "RES-N03",
            "temporal_progression",
            "revise_existing_identity",
            "block_same_object_assessment_required",
        ),
    ],
)
def test_resolution_never_maps_operations_without_same_object_assessment(
    ref: str,
    operation: str,
    resolution_type: str,
    reason_code: str,
) -> None:
    candidate = _registered(operation=operation)
    result = ResolutionEngine().evaluate(
        ResolutionRequest(
            candidate_revision=candidate,
            same_object_assessment=None,
            plan=_plan(resolution_type),
            authority=_authority(),
        )
    )

    assert ref.startswith("RES-N")
    assert result.disposition == "blocked"
    assert result.reason_code == reason_code


@pytest.mark.parametrize(
    ("ref", "candidate", "assessment", "plan", "authority", "reason_code"),
    [
        (
            "RES-N04",
            _registered(operation="correct"),
            _assessment(
                _registered(operation="correct"),
                prior=_snapshot(
                    dimensions={
                        "subject": "pilot",
                        "predicate": "capacity",
                        "object": 16,
                    }
                ),
                proposed=_snapshot(
                    identity_ref=None,
                    dimensions={
                        "subject": "pilot",
                        "predicate": "capacity",
                        "object": 14,
                    },
                ),
                material_dimensions=("object",),
            ),
            _plan("revise_existing_identity"),
            _authority(),
            "resolution_type_conflicts_with_same_object_assessment",
        ),
        (
            "RES-N05",
            _registered(operation="update_evidence_basis"),
            _assessment(_registered(operation="update_evidence_basis")),
            _plan("create_new_identity", target_canonical_refs=("CLM-NEW",)),
            _authority(),
            "resolution_type_conflicts_with_same_object_assessment",
        ),
        (
            "RES-N06",
            _registered(operation="register_conflict"),
            _assessment(
                _registered(operation="register_conflict"),
                prior=_snapshot(),
                proposed=_snapshot(
                    identity_ref=None,
                    dimensions={
                        "subject": "pilot",
                        "predicate": "operation",
                        "object": "unstable",
                    },
                ),
                material_dimensions=("object", "conflict"),
            ),
            _plan(
                "create_new_identity",
                target_canonical_refs=("CLM-CONFLICTING",),
                overwrites_existing_claim=True,
            ),
            _authority(),
            "conflict_overwrite_forbidden",
        ),
        (
            "RES-N07",
            _registered(),
            _assessment(),
            _plan(attempts_in_place_knowledge_mutation=True),
            _authority(),
            "material_knowledge_object_state_in_place_forbidden",
        ),
        (
            "RES-N08",
            _registered(),
            _assessment(),
            _plan("map_to_existing_without_new_version", planned_target_versions=()),
            _authority(),
            "material_delta_requires_new_version",
        ),
        (
            "RES-N09",
            _registered(),
            _assessment(),
            _plan(
                attempts_predecessor_supersession=True,
                predecessor_publication_state="unpublished",
            ),
            _authority(),
            "unpublished_predecessor_cannot_be_superseded",
        ),
        (
            "RES-N10",
            _registered(),
            _assessment(),
            _plan(foreign_authority_effects=("policy_permit",)),
            _authority(),
            "resolution_foreign_authority_effect_forbidden",
        ),
        (
            "RES-N11",
            _registered(),
            _assessment(),
            _plan(),
            _authority(
                authorized_actions=(
                    "resolve_candidate_identity",
                    "permit_policy",
                    "publish",
                )
            ),
            "resolution_authority_scope_escalation_forbidden",
        ),
        (
            "RES-N12",
            _registered(),
            _assessment(),
            _plan(originated_from_review=True),
            _authority(),
            "review_cannot_create_resolution_decision",
        ),
    ],
)
def test_resolution_negative_contracts(
    ref: str,
    candidate,
    assessment,
    plan,
    authority,
    reason_code: str,
) -> None:
    result = _resolve(candidate, assessment, plan, authority)

    assert ref.startswith("RES-N")
    assert result.disposition == "blocked"
    assert result.reason_code == reason_code
    assert result.decision is None


def test_resolution_is_deterministic_immutable_and_revision_bound() -> None:
    candidate = _registered()
    assessment = _assessment(candidate)
    first = _resolve(candidate, assessment)
    second = _resolve(candidate, assessment)

    assert first == second
    assert first.decision is not None
    assert (
        first.decision.candidate_revision_ref
        == candidate.lifecycle_candidate_revision_ref
    )
    assert first.decision.candidate_ref == candidate.lifecycle_candidate_ref
    assert first.decision.resolution_decision_ref.startswith("RDL-")
    assert first.decision.identity_scope == "implementation_local_non_canonical"
    with pytest.raises(FrozenInstanceError):
        first.decision.resolution_type = "create_new_identity"  # type: ignore[misc]


def test_materially_different_candidate_revision_cannot_reuse_resolution() -> None:
    rev1 = _registered(revision_ref="CCR-REV-1")
    rev2 = _registered(revision_ref="CCR-REV-2")
    rev1_assessment = _assessment(rev1)

    result = _resolve(rev2, rev1_assessment)

    assert result.disposition == "blocked"
    assert result.reason_code == "same_object_assessment_revision_mismatch"


def test_resolution_authority_is_explicit_and_not_codex_self_authorization() -> None:
    result = _resolve(authority=_authority(authority_kind="development_agent"))

    assert result.disposition == "blocked"
    assert result.reason_code == "resolution_authority_missing"


def test_resolution_decision_contains_no_review_policy_or_publication_effect() -> None:
    result = _resolve()
    assert result.decision is not None
    payload = result.decision.to_dict()

    assert payload["review_record_refs"] == []
    assert payload["policy_context_refs"] == []
    assert "policy_decision" not in payload
    assert "publication_change_set" not in payload
    assert "publication_record" not in payload


def test_material_resolution_projects_new_version_without_publication() -> None:
    result = _resolve()
    assert result.decision is not None
    projection = KnowledgeVersionProjector().evaluate(
        KnowledgeVersionProjectionRequest(
            resolution_decision=result.decision,
            stable_knowledge_object_ref="KO-TEST",
            prior_knowledge_object_version_ref="KO-TEST@0.1",
            prior_publication_state="unpublished",
            planned_target_knowledge_object_version_ref="KO-TEST@0.2",
            material_change=True,
            same_knowledge_object_identity=True,
        )
    )

    assert projection.disposition == "projected"
    assert projection.projection is not None
    assert projection.projection.new_version_required is True
    assert projection.projection.planned_target_knowledge_object_version_ref == (
        "KO-TEST@0.2"
    )
    assert projection.projection.prior_version_effect == "unchanged"
    assert projection.projection.publication_status == "not_performed"


def test_no_material_resolution_projects_no_new_version() -> None:
    candidate = _registered()
    assessment = _assessment(candidate, material_dimensions=())
    result = _resolve(
        candidate,
        assessment,
        _plan(
            "map_to_existing_without_new_version",
            planned_target_versions=(),
        ),
    )
    assert result.decision is not None
    projection = KnowledgeVersionProjector().evaluate(
        KnowledgeVersionProjectionRequest(
            resolution_decision=result.decision,
            stable_knowledge_object_ref="KO-TEST",
            prior_knowledge_object_version_ref="KO-TEST@0.1",
            prior_publication_state="unpublished",
            planned_target_knowledge_object_version_ref=None,
            material_change=False,
            same_knowledge_object_identity=True,
        )
    )

    assert projection.projection is not None
    assert projection.projection.new_version_required is False
    assert projection.projection.planned_target_knowledge_object_version_ref is None


def test_projection_blocks_unpublished_supersession_and_in_place_mutation() -> None:
    result = _resolve()
    assert result.decision is not None
    base = KnowledgeVersionProjectionRequest(
        resolution_decision=result.decision,
        stable_knowledge_object_ref="KO-TEST",
        prior_knowledge_object_version_ref="KO-TEST@0.1",
        prior_publication_state="unpublished",
        planned_target_knowledge_object_version_ref="KO-TEST@0.2",
        material_change=True,
        same_knowledge_object_identity=True,
    )

    supersession = KnowledgeVersionProjector().evaluate(
        replace(base, attempts_predecessor_supersession=True)
    )
    in_place = KnowledgeVersionProjector().evaluate(
        replace(base, attempts_in_place_mutation=True)
    )

    assert supersession.reason_code == "unpublished_predecessor_cannot_be_superseded"
    assert in_place.reason_code == "material_knowledge_object_state_in_place_forbidden"
