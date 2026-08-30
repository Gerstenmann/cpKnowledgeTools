#!/usr/bin/env python3
"""Run the synthetic HR-005 enrichment frontier through implemented D7.

The productive D3-D6 evaluators consume source-neutral semantic states, Findings,
Change Candidate Revisions, and caller-supplied authority inputs. This scenario
runner reads synthetic HTML fixtures and maps them to those generic inputs. It
does not read D1 Golden Expectations or the D2 manifest. Golden labels and the
existing scenario-local Owner decision basis are added only in this test harness.

D7 materializes only to an in-memory test-isolated target. It performs no
canonical, Vault, remote, or live publication write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cp_knowledge_tools.derived import (  # noqa: E402
    ExperienceContinuationPlan,
    ExperienceContinuationRequirement,
    ExperienceGap,
    ExperienceGapPlan,
    ExperiencePhase,
    ExperiencePhasePlan,
    ExperienceProjection,
    ExperienceProjectionPlan,
    ExperienceProjectionStore,
    ExperienceReuseContext,
    ExperienceSemanticSelector,
    ExperienceThread,
    ExperienceThreadPlan,
    PublicationBoundExperienceRebuilder,
)
from cp_knowledge_tools.lifecycle import (  # noqa: E402
    ExpectedPriorState,
    FinalPublicationState,
    G5PolicyGate,
    G5PolicyGateRequest,
    G6PublicationReadinessGate,
    G6PublicationReadinessRequest,
    HashRuleBinding,
    IdentitySnapshot,
    KnowledgeVersionProjectionRequest,
    KnowledgeVersionProjector,
    LifecycleCandidateRegistrar,
    MaterializedPublicationState,
    PublicationAuthorityEvidence,
    PublicationChangeSetBuilder,
    PublicationChangeSetBuildRequest,
    PublicationExecutor,
    PublicationFinalizationPlan,
    PublicationOperation,
    PublicationPackageBuilder,
    PublicationPackageBuildRequest,
    PublicationRecord,
    PublicationRequestFactory,
    PublicationReviewFactory,
    PublicationReviewValidator,
    PublicationUnitBinding,
    ResolutionAuthority,
    ResolutionEngine,
    ResolutionPlan,
    ResolutionRequest,
    ReviewOrchestrator,
    ReviewRecord,
    ReviewRecordValidator,
    ReviewRequestFactory,
    ReviewRequirementRouter,
    ReviewRoutingContext,
    ReviewRoutingPolicy,
    SameObjectAssessmentRequest,
    SameObjectEvaluator,
    TestIsolatedPublicationTarget,
    publication_unit_knowledge_content_hash,
    publication_unit_representation_hash,
)
from cp_knowledge_tools.lifecycle._common import local_ref  # noqa: E402
from cp_knowledge_tools.policy import (  # noqa: E402
    PUBLICATION_DATA_OPERATIONS,
    PolicyConfiguration,
    PolicyEvaluationInput,
    PolicyEvaluator,
    PolicyRule,
    PolicySubject,
    ProfileApplicability,
)
from cp_knowledge_tools.post_r5 import (  # noqa: E402
    run_post_r5_hardening,
    run_source_backed_post_r5,
)
from cp_knowledge_tools.publication import (  # noqa: E402
    PublicationApplicability,
    PublicationAssemblyPlan,
    PublicationInterpretationProvenance,
    PublicationPolicyAnchor,
    PublicationPolicyBinding,
    PublicationRepresentation,
    PublicationRepresentationItem,
    PublicationRepresentationSection,
    PublicationSemanticReference,
    PublicationUnitAssembler,
    load_publication_unit,
)
from cp_knowledge_tools.semantics import (  # noqa: E402
    ChangeCandidatePipeline,
    ChangeCandidateRequest,
    ChangeCandidateRevision,
    FindingInput,
    KnowledgeFinding,
    MaterialDeltaFindingEvaluator,
    PriorKnowledgeState,
    SemanticChangeOperationPolicy,
    SemanticChangeProposal,
    SemanticState,
    SemanticTarget,
)
from cp_knowledge_tools.sources.adapters.local_html import (  # noqa: E402
    LocalHtmlAdapter,
)

BASELINE_SOURCE_ROOT = (
    REPO_ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/html"
)
CONTINUATION_ROOT = (
    REPO_ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/continuation/html"
)
ENRICHMENT_ROOT = (
    REPO_ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/enrichment/html"
)
BASELINE_EXPERIENCE_ROOT = (
    REPO_ROOT / "artifacts/tests/source_to_knowledge/experience-v1-2-final-validated"
)
BASELINE_EXPERIENCE_PATH = (
    BASELINE_EXPERIENCE_ROOT / "derived/experience_projection.json"
)
BASELINE_PUBLICATION_PATH = (
    BASELINE_EXPERIENCE_ROOT / "publication/KO-GT-ME-ESPORTS-PILOT@0.1.md"
)

DOC04 = CONTINUATION_ROOT / "04-pilot-evaluation-summary.html"
DOC05 = CONTINUATION_ROOT / "05-spring-follow-up-decisions.html"
DOC07 = ENRICHMENT_ROOT / "07-independent-approval-confirmation.html"
DOC08 = ENRICHMENT_ROOT / "08-technical-operation-conflict.html"
DOC09 = ENRICHMENT_ROOT / "09-pilot-capacity-correction.html"
POST_R5_HARDENING_ROOT = (
    REPO_ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/hardening"
)
POST_R5_SOURCE_ROOT = POST_R5_HARDENING_ROOT / "html"
POST_R5_SEMANTIC_CASES = POST_R5_HARDENING_ROOT / "semantic_cases.v0.1.json"
POST_R5_HUMAN_ENRICHMENT = POST_R5_HARDENING_ROOT / "human_enrichment.v0.1.json"
POST_R5_SOURCE_BINDINGS = (
    ("DOC-01", BASELINE_SOURCE_ROOT / "01-program-proposal.html"),
    ("DOC-02", BASELINE_SOURCE_ROOT / "02-school-response.html"),
    ("DOC-03", BASELINE_SOURCE_ROOT / "03-pilot-status.html"),
    ("DOC-04", CONTINUATION_ROOT / "04-pilot-evaluation-summary.html"),
    ("DOC-05", CONTINUATION_ROOT / "05-spring-follow-up-decisions.html"),
    ("DOC-06", CONTINUATION_ROOT / "06-workshop-room-note.html"),
    ("DOC-07", ENRICHMENT_ROOT / "07-independent-approval-confirmation.html"),
    ("DOC-08", ENRICHMENT_ROOT / "08-technical-operation-conflict.html"),
    ("DOC-09", ENRICHMENT_ROOT / "09-pilot-capacity-correction.html"),
    ("DOC-10", POST_R5_SOURCE_ROOT / "10-program-context-and-rationale.html"),
    ("DOC-11", POST_R5_SOURCE_ROOT / "11-later-program-planning-status.html"),
    (
        "DOC-12",
        POST_R5_SOURCE_ROOT / "12-minecraft-technical-specialist-observation.html",
    ),
)

TASK_REF = "HR005-CONTROLLED-ENRICHMENT"
SOURCE_RESULT_REF = "GT-S2K-CONTINUATION-01@0.2"

HR005_OPERATION_POLICY = SemanticChangeOperationPolicy.from_allowed(
    {
        "add",
        "qualify",
        "temporal_progression",
        "constrain",
        "extend_scope",
        "register_conflict",
        "correct",
        "update_epistemic_state",
        "update_evidence_basis",
    },
    policy_ref="GT-S2K-ENRICHMENT-01@0.8:controlled_semantic_change_operation",
)

HR005_REVIEW_POLICY = ReviewRoutingPolicy.from_rules(
    baseline_review_types=("technical_validation", "source_and_evidence_review"),
    operation_requirements={
        "add": ("domain_review",),
        "qualify": ("domain_review",),
        "temporal_progression": ("domain_review",),
        "constrain": ("domain_review",),
        "extend_scope": ("domain_review", "independent_quality_review"),
        "register_conflict": ("domain_review", "independent_quality_review"),
        "correct": ("domain_review", "independent_quality_review"),
        "update_epistemic_state": ("domain_review",),
        "update_evidence_basis": ("domain_review",),
    },
    identity_sensitive_operations=(
        "qualify",
        "temporal_progression",
        "constrain",
        "extend_scope",
        "correct",
    ),
    baseline_only_when_evidence_basis_unchanged=("update_evidence_basis",),
    policy_ref="GT-S2K-ENRICHMENT-01@0.8:review-routing",
)

HR005_REVIEW_AUTHORITIES = {
    "technical_validation": "authorized_validator",
    "source_and_evidence_review": "project_owner_default_human",
    "domain_review": "project_owner_default_human",
    "entity_and_identity_review": "project_owner_default_human",
    "independent_quality_review": "authorized_independent_human",
    "privacy_and_security_review": "specialized_privacy_security_authority",
    "policy_review": "trust_policy_review_authority",
}

HR005_RESOLUTION_AUTHORITY = ResolutionAuthority(
    authority_ref="GT-S2K-ENRICHMENT-01@0.8:project-owner-resolution-basis",
    authority_context="synthetic_hr005_test_projection",
    authority_kind="scenario_local_owner_decision_basis",
    authorized_actions=("resolve_candidate_identity",),
    decision_basis_refs=(
        "GT-S2K-ENRICHMENT-01@0.8",
        "CPKS-SPEC-KM@0.20#9",
        "CPKS-SPEC-KPR@0.3#8",
    ),
    decided_at="2026-08-14T00:00:00+02:00",
)


@dataclass(frozen=True, slots=True)
class _CandidateCaseConfig:
    operation: str
    effect: str
    semantic_unit_kind: str
    prior_state_ref: str
    prior_state_summary: str
    target_refs: tuple[str, ...] = ()
    target_version_refs: tuple[str, ...] = ()
    prior_source_refs: tuple[str, ...] = ()
    prior_evidence_refs: tuple[str, ...] = ()
    preservation_constraints: tuple[str, ...] = ()
    prohibited_inferences: tuple[str, ...] = ()
    unresolved_identity_questions: tuple[str, ...] = ()


_GOLDEN_CANDIDATE_CONFIG = {
    "KF-D01": _CandidateCaseConfig(
        operation="temporal_progression",
        effect="planned_to_actual_same_event",
        semantic_unit_kind="event",
        prior_state_ref="EVT-INTERNAL-PILOT@planned",
        prior_state_summary="EVT-INTERNAL-PILOT planned; actual occurrence unknown",
        target_refs=("EVT-INTERNAL-PILOT",),
        target_version_refs=("EVT-INTERNAL-PILOT@planned",),
        prior_evidence_refs=("CE-BASELINE-PILOT",),
        preservation_constraints=("preserve_planned_event_state",),
        prohibited_inferences=("new_pilot_event_identity", "universal_effectiveness"),
        unresolved_identity_questions=("same_event_resolution_deferred_to_D5",),
    ),
    "KF-D02": _CandidateCaseConfig(
        operation="add",
        effect="add_pilot_specific_engagement_teamwork_evaluation",
        semantic_unit_kind="claim",
        prior_state_ref="PRIOR-EVALUATION-ENGAGEMENT",
        prior_state_summary="pilot engagement/teamwork evaluation unknown",
        target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        prohibited_inferences=("generalize_beyond_this_pilot",),
    ),
    "KF-D03": _CandidateCaseConfig(
        operation="add",
        effect="add_mixed_coding_progression_evaluation",
        semantic_unit_kind="claim",
        prior_state_ref="PRIOR-EVALUATION-CODING",
        prior_state_summary="pilot coding progression evaluation unknown",
        target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        prohibited_inferences=(
            "simplify_to_success",
            "simplify_to_failure",
            "generalize_beyond_this_pilot",
        ),
    ),
    "KF-D04": _CandidateCaseConfig(
        operation="add",
        effect="add_time_qualified_technical_operation_progression",
        semantic_unit_kind="claim",
        prior_state_ref="PRIOR-TECHNICAL-OPERATION",
        prior_state_summary="pilot technical progression unknown",
        target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        preservation_constraints=("preserve_after_first_session_time_scope",),
        prohibited_inferences=(
            "technical_operation_stable_before_or_during_first_session",
        ),
    ),
    "KF-D05": _CandidateCaseConfig(
        operation="add",
        effect="add_coupled_outcome_assessment",
        semantic_unit_kind="claim",
        prior_state_ref="PRIOR-OUTCOME",
        prior_state_summary="pilot outcome unknown",
        target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        preservation_constraints=(
            "preserve_together:promising_after_school+not_ready_for_classroom",
        ),
    ),
    "KF-D06": _CandidateCaseConfig(
        operation="temporal_progression",
        effect="add_follow_up_approval_state",
        semantic_unit_kind="claim",
        prior_state_ref="PRIOR-SECOND-CYCLE",
        prior_state_summary="second after-school cycle follow-up unknown",
        target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        prohibited_inferences=("performed", "repeated", "institutionalized"),
    ),
    "KF-D07": _CandidateCaseConfig(
        operation="temporal_progression",
        effect="add_time_bounded_classroom_follow_up_state",
        semantic_unit_kind="claim",
        prior_state_ref="PRIOR-CLASSROOM-FOLLOWUP",
        prior_state_summary="classroom follow-up unknown",
        target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        preservation_constraints=(
            "preserve_existing:CLM-ACADEMIC-DEFERRED",
            "preserve_together:not_introduced_2024_25+not_permanently_rejected",
        ),
        prohibited_inferences=("permanently_rejected", "later_introduced"),
    ),
    "KF-D08": _CandidateCaseConfig(
        operation="temporal_progression",
        effect="add_time_bounded_external_competition_follow_up_state",
        semantic_unit_kind="claim",
        prior_state_ref="PRIOR-COMPETITION-FOLLOWUP",
        prior_state_summary="external competition follow-up unknown",
        target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        preservation_constraints=(
            "preserve_existing:CLM-EXT-COMP-NOT-APPROVED",
            "preserve_together:not_planned_2024_25+not_permanently_excluded",
        ),
        prohibited_inferences=(
            "permanently_excluded",
            "later_approved",
            "later_participated",
        ),
    ),
    "KF-D09": _CandidateCaseConfig(
        operation="add",
        effect="add_evaluation_occurrence_event",
        semantic_unit_kind="event",
        prior_state_ref="PRIOR-EVALUATION-OCCURRENCE",
        prior_state_summary="evaluation occurrence unknown",
        target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        preservation_constraints=("preserve_unknown_exact_event_time",),
        prohibited_inferences=("source_time_equals_exact_event_time",),
    ),
}


@dataclass(frozen=True, slots=True)
class _ResolutionCaseConfig:
    resolution_ref: str
    resolution_type: str
    target_canonical_ref: str
    prior_identity_ref: str | None
    prior_dimensions: dict[str, Any] | None
    proposed_dimensions: dict[str, Any]
    material_delta_dimensions: tuple[str, ...]
    same_object_relevant_for_review: bool = False
    evidence_basis_only: bool = False


_GOLDEN_RESOLUTION_CONFIG = {
    "KF-D01": _ResolutionCaseConfig(
        resolution_ref="RES-D01",
        resolution_type="revise_existing_identity",
        target_canonical_ref="EVT-INTERNAL-PILOT",
        prior_identity_ref="EVT-INTERNAL-PILOT",
        prior_dimensions={
            "event_ref": "EVT-INTERNAL-PILOT",
            "occurrence_state": "planned",
        },
        proposed_dimensions={
            "event_ref": "EVT-INTERNAL-PILOT",
            "occurrence_state": "actual",
        },
        material_delta_dimensions=("occurrence_state",),
        same_object_relevant_for_review=True,
    ),
    "KF-D02": _ResolutionCaseConfig(
        resolution_ref="RES-D02",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-HR005-D02",
        prior_identity_ref=None,
        prior_dimensions=None,
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "engagement_and_teamwork",
            "object": "strong",
        },
        material_delta_dimensions=("subject", "predicate", "object"),
    ),
    "KF-D03": _ResolutionCaseConfig(
        resolution_ref="RES-D03",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-HR005-D03",
        prior_identity_ref=None,
        prior_dimensions=None,
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "coding_progression",
            "object": "mixed",
        },
        material_delta_dimensions=("subject", "predicate", "object"),
    ),
    "KF-D04": _ResolutionCaseConfig(
        resolution_ref="RES-D04",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-HR005-D04",
        prior_identity_ref=None,
        prior_dimensions=None,
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "technical_operation",
            "object": "stable_after_first_session",
            "applicability_scope": "after_first_session",
        },
        material_delta_dimensions=(
            "subject",
            "predicate",
            "object",
            "applicability_scope",
        ),
    ),
    "KF-D05": _ResolutionCaseConfig(
        resolution_ref="RES-D05",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-HR005-D05",
        prior_identity_ref=None,
        prior_dimensions=None,
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "overall_assessment",
            "object": {
                "promising_after_school": True,
                "not_ready_for_classroom": True,
            },
        },
        material_delta_dimensions=("subject", "predicate", "object"),
    ),
    "KF-D06": _ResolutionCaseConfig(
        resolution_ref="RES-D06",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-HR005-D06",
        prior_identity_ref=None,
        prior_dimensions=None,
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "second_after_school_cycle",
            "object": "approved",
            "applicability_scope": "spring_2025",
        },
        material_delta_dimensions=(
            "subject",
            "predicate",
            "object",
            "applicability_scope",
        ),
    ),
    "KF-D07": _ResolutionCaseConfig(
        resolution_ref="RES-D07",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-HR005-D07",
        prior_identity_ref=None,
        prior_dimensions=None,
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "classroom_follow_up",
            "object": {
                "classroom_2024_25": "not_introduced",
                "classroom_long_term": "not_permanently_rejected",
            },
            "applicability_scope": "school_year_2024_25",
        },
        material_delta_dimensions=(
            "subject",
            "predicate",
            "object",
            "applicability_scope",
        ),
    ),
    "KF-D08": _ResolutionCaseConfig(
        resolution_ref="RES-D08",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-HR005-D08",
        prior_identity_ref=None,
        prior_dimensions=None,
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "external_competition_follow_up",
            "object": {
                "external_competition_2024_25": "not_planned",
                "external_competition_long_term": "not_permanently_excluded",
            },
            "applicability_scope": "school_year_2024_25",
        },
        material_delta_dimensions=(
            "subject",
            "predicate",
            "object",
            "applicability_scope",
        ),
    ),
    "KF-D09": _ResolutionCaseConfig(
        resolution_ref="RES-D09",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-EVT-HR005-D09",
        prior_identity_ref=None,
        prior_dimensions=None,
        proposed_dimensions={
            "occurrence_key": "pilot_evaluation_after_cycle",
            "exact_event_time": None,
        },
        material_delta_dimensions=("occurrence_key",),
    ),
}


def _facts(path: Path) -> dict[str, str]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    return {
        str(node["data-fact"]): str(node["data-value"])
        for node in soup.select("[data-fact][data-value]")
    }


def _state(
    payload: dict[str, Any] | None,
    *evidence_refs: str,
    time_scope: tuple[str, ...] = (),
    epistemic_state: str | None = None,
    conflict_refs: tuple[str, ...] = (),
    applicability: tuple[str, ...] = (),
) -> SemanticState:
    return SemanticState(
        semantic_payload=payload,
        evidence_refs=tuple(evidence_refs),
        time_scope=time_scope,
        epistemic_state=epistemic_state,
        conflict_refs=conflict_refs,
        applicability=applicability,
    )


def _finding_input(
    *,
    source_ref: str,
    subject_refs: tuple[str, ...],
    prior_state_ref: str | None,
    prior_state: SemanticState | None,
    observed_state: SemanticState,
    description: str,
    delta_class: tuple[str, ...],
    finding_type: str = "observation",
    uncertainty_or_conflict: tuple[str, ...] = (),
    prohibited_inferences: tuple[str, ...] = (),
    event_time: str | None = None,
) -> FindingInput:
    return FindingInput(
        task_ref=TASK_REF,
        source_result_ref=SOURCE_RESULT_REF,
        source_ref=source_ref,
        subject_refs=subject_refs,
        prior_state_ref=prior_state_ref,
        prior_state=prior_state,
        observed_state=observed_state,
        description=description,
        delta_class=delta_class,
        evidence_content_read=True,
        content_read_authorized=True,
        evidence_resolvable=True,
        semantic_assertion=True,
        finding_type=finding_type,
        uncertainty_or_conflict=uncertainty_or_conflict,
        prohibited_inferences=prohibited_inferences,
        event_time=event_time,
        producer_ref="cpKnowledgeTools",
        tool_or_model_ref="material-delta-finding-evaluator@0.1",
    )


def _require_fact(
    facts: dict[str, str],
    name: str,
    expected: str,
    source_ref: str,
) -> None:
    actual = facts.get(name)
    if actual != expected:
        raise RuntimeError(
            f"{source_ref}: expected fact {name}={expected!r}, got {actual!r}"
        )


def _positive_findings() -> list[tuple[str, KnowledgeFinding]]:
    doc04 = _facts(DOC04)
    doc05 = _facts(DOC05)

    required_04 = {
        "pilot_execution": "occurred",
        "pilot_evaluation_occurrence": "completed",
        "engagement_and_teamwork": "strong",
        "coding_progression": "mixed",
        "technical_operation": "stable_after_first_session",
        "overall_assessment": "promising_after_school_not_ready_for_classroom",
    }
    required_05 = {
        "second_after_school_cycle": "approved",
        "classroom_2024_25": "not_introduced",
        "classroom_long_term": "not_permanently_rejected",
        "external_competition_2024_25": "not_planned",
        "external_competition_long_term": "not_permanently_excluded",
    }
    for key, value in required_04.items():
        _require_fact(doc04, key, value, "DOC-04")
    for key, value in required_05.items():
        _require_fact(doc05, key, value, "DOC-05")

    items: list[tuple[str, FindingInput]] = [
        (
            "KF-D01",
            _finding_input(
                source_ref="DOC-04",
                subject_refs=("EVT-INTERNAL-PILOT",),
                prior_state_ref="EVT-INTERNAL-PILOT@planned",
                prior_state=_state(
                    {"event_ref": "EVT-INTERNAL-PILOT", "occurrence_state": "planned"},
                    "CE-BASELINE-PILOT",
                ),
                observed_state=_state(
                    {"event_ref": "EVT-INTERNAL-PILOT", "occurrence_state": "actual"},
                    "CE-DOC-04",
                ),
                description="The internal pilot occurred.",
                delta_class=("temporal_progression",),
                prohibited_inferences=("universal_effectiveness",),
            ),
        ),
        (
            "KF-D02",
            _finding_input(
                source_ref="DOC-04",
                subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
                prior_state_ref="PRIOR-EVALUATION-ENGAGEMENT",
                prior_state=_state(
                    {"predicate": "engagement_and_teamwork", "value": None}
                ),
                observed_state=_state(
                    {
                        "predicate": "engagement_and_teamwork",
                        "value": doc04["engagement_and_teamwork"],
                    },
                    "CE-DOC-04",
                ),
                description="Engagement and teamwork were strong in this pilot.",
                delta_class=("addition",),
                prohibited_inferences=("generalize_beyond_this_pilot",),
            ),
        ),
        (
            "KF-D03",
            _finding_input(
                source_ref="DOC-04",
                subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
                prior_state_ref="PRIOR-EVALUATION-CODING",
                prior_state=_state({"predicate": "coding_progression", "value": None}),
                observed_state=_state(
                    {
                        "predicate": "coding_progression",
                        "value": doc04["coding_progression"],
                    },
                    "CE-DOC-04",
                ),
                description="Coding progression was mixed in this pilot.",
                delta_class=("addition",),
                prohibited_inferences=("uniform_success", "uniform_failure"),
            ),
        ),
        (
            "KF-D04",
            _finding_input(
                source_ref="DOC-04",
                subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
                prior_state_ref="PRIOR-TECHNICAL-OPERATION",
                prior_state=_state({"predicate": "technical_operation", "value": None}),
                observed_state=_state(
                    {
                        "predicate": "technical_operation",
                        "value": doc04["technical_operation"],
                    },
                    "CE-DOC-04",
                    time_scope=("after_first_session",),
                ),
                description="Technical operation was stable after the first session.",
                delta_class=("addition", "temporal_qualification"),
                prohibited_inferences=("stable_before_or_during_first_session",),
            ),
        ),
        (
            "KF-D05",
            _finding_input(
                source_ref="DOC-04",
                subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
                prior_state_ref="PRIOR-OUTCOME",
                prior_state=_state({"predicate": "overall_assessment", "value": None}),
                observed_state=_state(
                    {
                        "predicate": "overall_assessment",
                        "promising_after_school": True,
                        "not_ready_for_classroom": True,
                    },
                    "CE-DOC-04",
                ),
                description=(
                    "The format was promising for after-school use but not ready "
                    "for classroom introduction."
                ),
                delta_class=("addition", "constraint"),
            ),
        ),
        (
            "KF-D06",
            _finding_input(
                source_ref="DOC-05",
                subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
                prior_state_ref="PRIOR-SECOND-CYCLE",
                prior_state=_state(
                    {"predicate": "second_after_school_cycle", "value": None}
                ),
                observed_state=_state(
                    {
                        "predicate": "second_after_school_cycle",
                        "value": doc05["second_after_school_cycle"],
                    },
                    "CE-DOC-05",
                    time_scope=("spring_2025",),
                ),
                description="A second after-school cycle was approved for spring 2025.",
                delta_class=("temporal_progression",),
                prohibited_inferences=("performed", "repeated", "institutionalized"),
            ),
        ),
        (
            "KF-D07",
            _finding_input(
                source_ref="DOC-05",
                subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
                prior_state_ref="PRIOR-CLASSROOM-FOLLOWUP",
                prior_state=_state(
                    {
                        "classroom_2024_25": None,
                        "classroom_long_term": None,
                    }
                ),
                observed_state=_state(
                    {
                        "classroom_2024_25": doc05["classroom_2024_25"],
                        "classroom_long_term": doc05["classroom_long_term"],
                    },
                    "CE-DOC-05",
                    time_scope=("school_year_2024_25",),
                ),
                description=(
                    "Classroom use was not introduced in 2024/25 and was not "
                    "permanently rejected."
                ),
                delta_class=("temporal_progression", "constraint"),
                prohibited_inferences=("permanently_rejected", "later_introduced"),
            ),
        ),
        (
            "KF-D08",
            _finding_input(
                source_ref="DOC-05",
                subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
                prior_state_ref="PRIOR-COMPETITION-FOLLOWUP",
                prior_state=_state(
                    {
                        "external_competition_2024_25": None,
                        "external_competition_long_term": None,
                    }
                ),
                observed_state=_state(
                    {
                        "external_competition_2024_25": (
                            doc05["external_competition_2024_25"]
                        ),
                        "external_competition_long_term": (
                            doc05["external_competition_long_term"]
                        ),
                    },
                    "CE-DOC-05",
                    time_scope=("school_year_2024_25",),
                ),
                description=(
                    "External competition was not planned for 2024/25 and was "
                    "not permanently excluded."
                ),
                delta_class=("temporal_progression", "constraint"),
                prohibited_inferences=(
                    "permanently_excluded",
                    "later_approved",
                    "later_participated",
                ),
            ),
        ),
        (
            "KF-D09",
            _finding_input(
                source_ref="DOC-04",
                subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
                prior_state_ref=None,
                prior_state=None,
                observed_state=_state(
                    {
                        "event_type": "pilot_evaluation",
                        "occurrence": "completed_after_cycle",
                    },
                    "CE-DOC-04",
                    time_scope=("after_cycle",),
                ),
                description=(
                    "The school and delivery team completed an evaluation "
                    "after the cycle."
                ),
                delta_class=("addition",),
                event_time=None,
                prohibited_inferences=("source_time_equals_exact_event_time",),
            ),
        ),
    ]

    evaluator = MaterialDeltaFindingEvaluator()
    findings: list[tuple[str, KnowledgeFinding]] = []
    for golden_ref, item in items:
        evaluation = evaluator.evaluate(item)
        if evaluation.finding is None:
            raise RuntimeError(
                f"{golden_ref}: expected material Finding, got {evaluation.reason_code}"
            )
        findings.append((golden_ref, evaluation.finding))
    return findings


def _candidate_request(
    finding: KnowledgeFinding,
    config: _CandidateCaseConfig,
) -> ChangeCandidateRequest:
    if finding.semantic_observation is None:
        raise RuntimeError(f"{finding.finding_ref}: semantic observation missing")
    return ChangeCandidateRequest(
        findings=(finding,),
        semantic_target=SemanticTarget(
            semantic_unit_kind=config.semantic_unit_kind,
            target_refs=config.target_refs or finding.subject_refs,
            target_version_refs=config.target_version_refs,
        ),
        prior_state=PriorKnowledgeState(
            prior_state_refs=(config.prior_state_ref,),
            relevant_state_summary=config.prior_state_summary,
            source_refs=config.prior_source_refs,
            evidence_refs=config.prior_evidence_refs,
        ),
        proposals=(
            SemanticChangeProposal(
                semantic_change_operation=config.operation,
                proposed_semantic_effect=config.effect,
                proposed_semantic_payload=finding.semantic_observation,
                preservation_constraints=config.preservation_constraints,
                prohibited_inferences=config.prohibited_inferences,
                unresolved_identity_questions=config.unresolved_identity_questions,
            ),
        ),
        producer_ref="hr005-synthetic-scenario-runner",
        producer_version="0.1",
    )


def _positive_candidates(
    findings: list[tuple[str, KnowledgeFinding]],
) -> tuple[list[dict[str, Any]], dict[str, ChangeCandidateRevision]]:
    pipeline = ChangeCandidatePipeline(HR005_OPERATION_POLICY)
    golden_ref_by_finding_ref = {
        finding.finding_ref: golden_ref for golden_ref, finding in findings
    }
    requests = [
        _candidate_request(finding, _GOLDEN_CANDIDATE_CONFIG[golden_ref])
        for golden_ref, finding in findings
    ]
    evaluation = pipeline.evaluate_many(requests)
    if evaluation.disposition != "candidates" or len(evaluation.candidates) != 9:
        raise RuntimeError(
            "D4: expected nine atomic Change Candidates, got "
            f"{evaluation.disposition}/{evaluation.reason_code}/"
            f"{len(evaluation.candidates)}"
        )

    projected: list[dict[str, Any]] = []
    candidate_by_golden_ref: dict[str, ChangeCandidateRevision] = {}
    for candidate in evaluation.candidates:
        golden_refs = {
            golden_ref_by_finding_ref[finding_ref]
            for finding_ref in candidate.source_finding_refs
        }
        if len(golden_refs) != 1:
            raise RuntimeError(
                "D4 scenario projection cannot assign one Golden label to "
                f"candidate {candidate.change_candidate_ref}: {golden_refs}"
            )
        golden_ref = golden_refs.pop()
        payload = candidate.to_dict()
        payload["golden_delta_ref"] = golden_ref
        projected.append(payload)
        candidate_by_golden_ref[golden_ref] = candidate
    return (
        sorted(projected, key=lambda item: str(item["golden_delta_ref"])),
        candidate_by_golden_ref,
    )


def _special_candidate(
    finding: KnowledgeFinding,
    *,
    operation: str,
    effect: str,
    prior_state_ref: str,
    prior_state_summary: str,
    prior_source_refs: tuple[str, ...] = (),
    prior_evidence_refs: tuple[str, ...] = (),
    conflict_treatment: tuple[str, ...] = (),
    preservation_constraints: tuple[str, ...] = (),
    prohibited_inferences: tuple[str, ...] = (),
    unresolved_identity_questions: tuple[str, ...] = (),
) -> tuple[ChangeCandidateRevision, dict[str, Any]]:
    if finding.semantic_observation is None:
        raise RuntimeError(f"{finding.finding_ref}: semantic observation missing")
    request = ChangeCandidateRequest(
        findings=(finding,),
        semantic_target=SemanticTarget(
            semantic_unit_kind="claim",
            target_refs=finding.subject_refs,
            target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.1",),
        ),
        prior_state=PriorKnowledgeState(
            prior_state_refs=(prior_state_ref,),
            relevant_state_summary=prior_state_summary,
            source_refs=prior_source_refs,
            evidence_refs=prior_evidence_refs,
        ),
        proposals=(
            SemanticChangeProposal(
                semantic_change_operation=operation,
                proposed_semantic_effect=effect,
                proposed_semantic_payload=finding.semantic_observation,
                conflict_treatment=conflict_treatment,
                preservation_constraints=preservation_constraints,
                prohibited_inferences=prohibited_inferences,
                unresolved_identity_questions=unresolved_identity_questions,
            ),
        ),
        producer_ref="hr005-synthetic-scenario-runner",
        producer_version="0.1",
    )
    evaluation = ChangeCandidatePipeline(HR005_OPERATION_POLICY).evaluate(request)
    if evaluation.disposition != "candidates" or len(evaluation.candidates) != 1:
        raise RuntimeError(
            f"{prior_state_ref}: D4 candidate failed: "
            f"{evaluation.disposition}/{evaluation.reason_code}"
        )
    return evaluation.candidates[0], evaluation.to_dict()


def _special_cases() -> tuple[
    dict[str, dict[str, Any]],
    dict[str, ChangeCandidateRevision],
]:
    doc07 = _facts(DOC07)
    doc08 = _facts(DOC08)
    doc09 = _facts(DOC09)
    _require_fact(doc07, "second_after_school_cycle", "approved", "DOC-07")
    _require_fact(
        doc08,
        "technical_operation",
        "intermittent_after_first_session",
        "DOC-08",
    )
    _require_fact(doc09, "pilot_capacity", "14", "DOC-09")

    evaluator = MaterialDeltaFindingEvaluator()

    same_payload = {"predicate": "second_after_school_cycle", "value": "approved"}
    evidence_eval = evaluator.evaluate(
        _finding_input(
            source_ref="DOC-07",
            subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
            prior_state_ref="PRIOR-SECOND-CYCLE-APPROVED",
            prior_state=_state(same_payload, "CE-DOC-05"),
            observed_state=_state(same_payload, "CE-DOC-05", "CE-DOC-07"),
            description="Independent Evidence confirms the same approval proposition.",
            delta_class=("evidence_basis",),
            prohibited_inferences=("performed", "repeated", "institutionalized"),
        )
    )
    conflict_eval = evaluator.evaluate(
        _finding_input(
            source_ref="DOC-08",
            subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
            prior_state_ref="PRIOR-TECHNICAL-STABILITY",
            prior_state=_state(
                {
                    "predicate": "technical_operation",
                    "value": "stable_after_first_session",
                },
                "CE-DOC-04",
            ),
            observed_state=_state(
                {
                    "predicate": "technical_operation",
                    "value": doc08["technical_operation"],
                },
                "CE-DOC-08",
                conflict_refs=("PRIOR-TECHNICAL-STABILITY",),
            ),
            description=(
                "Independent Evidence conflicts with the prior "
                "technical-stability assertion."
            ),
            delta_class=("conflict",),
            finding_type="conflict",
            uncertainty_or_conflict=("technical_operation_conflict",),
        )
    )
    replay_state = _state(same_payload, "CE-DOC-05")
    replay_eval = evaluator.evaluate(
        _finding_input(
            source_ref="DOC-05",
            subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
            prior_state_ref="PRIOR-SECOND-CYCLE-APPROVED-WITH-DOC05",
            prior_state=replay_state,
            observed_state=replay_state,
            description="Replay of the same Evidence occurrence.",
            delta_class=(),
        )
    )
    correct_eval = evaluator.evaluate(
        _finding_input(
            source_ref="DOC-09",
            subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
            prior_state_ref="PRIOR-PILOT-CAPACITY-16",
            prior_state=_state(
                {"predicate": "pilot_capacity", "value": 16},
                "TEST-PRIOR-EVIDENCE-CAPACITY-16",
            ),
            observed_state=_state(
                {"predicate": "pilot_capacity", "value": int(doc09["pilot_capacity"])},
                "CE-DOC-09",
            ),
            description=(
                "Correction changes planned participant capacity from 16 to 14."
            ),
            delta_class=("correction",),
        )
    )

    if evidence_eval.finding is None:
        raise RuntimeError("D2-EVIDENCE-01: expected material Finding")
    if conflict_eval.finding is None:
        raise RuntimeError("D2-CONFLICT-01: expected material Finding")
    if correct_eval.finding is None:
        raise RuntimeError("D2-CORRECT-01: expected material Finding")

    evidence_candidate, evidence_candidate_eval = _special_candidate(
        evidence_eval.finding,
        operation="update_evidence_basis",
        effect="update_second_cycle_approval_evidence_basis",
        prior_state_ref="PRIOR-SECOND-CYCLE-APPROVED",
        prior_state_summary="same approval proposition supported by CE-DOC-05",
        prior_source_refs=("DOC-05",),
        prior_evidence_refs=("CE-DOC-05",),
        preservation_constraints=(
            "preserve_all_independent_evidence:CE-DOC-05+CE-DOC-07",
        ),
        prohibited_inferences=("performed", "repeated", "institutionalized"),
        unresolved_identity_questions=("claim_identity_resolution_deferred_to_D5",),
    )
    conflict_candidate, conflict_candidate_eval = _special_candidate(
        conflict_eval.finding,
        operation="register_conflict",
        effect="register_technical_operation_conflict",
        prior_state_ref="PRIOR-TECHNICAL-STABILITY",
        prior_state_summary="technical operation stable after first session",
        prior_source_refs=("DOC-04",),
        prior_evidence_refs=("CE-DOC-04",),
        conflict_treatment=("support_vs_conflict",),
        preservation_constraints=(
            "preserve_prior_assertion",
            "preserve_conflicting_assertion",
            "no_automatic_winner_or_resolution",
        ),
        prohibited_inferences=(
            "technical_operation_universally_failed",
            "replace_DOC04_without_resolution",
        ),
        unresolved_identity_questions=(
            "conflicting_claim_identity_resolution_deferred_to_D5",
        ),
    )
    correct_candidate, correct_candidate_eval = _special_candidate(
        correct_eval.finding,
        operation="correct",
        effect="propose_pilot_capacity_correction_16_to_14",
        prior_state_ref="PRIOR-PILOT-CAPACITY-16",
        prior_state_summary="pilot capacity previously stated as 16",
        prior_evidence_refs=("TEST-PRIOR-EVIDENCE-CAPACITY-16",),
        preservation_constraints=(
            "preserve_prior_value:16",
            "propose_new_value:14",
            "no_in_place_overwrite",
        ),
        prohibited_inferences=(
            "correct_automatically_means_revise_existing_identity",
            "overwrite_value_16_in_place_under_same_claim_identity",
        ),
        unresolved_identity_questions=("same_or_new_claim_identity_deferred_to_D5",),
    )

    return {
        "D2-EVIDENCE-01": {
            "finding": evidence_eval.finding.to_dict(),
            "finding_evaluation": evidence_eval.to_dict(),
            "change_candidate": evidence_candidate.to_dict(),
            "candidate_evaluation": evidence_candidate_eval,
        },
        "D2-CONFLICT-01": {
            "finding": conflict_eval.finding.to_dict(),
            "finding_evaluation": conflict_eval.to_dict(),
            "change_candidate": conflict_candidate.to_dict(),
            "candidate_evaluation": conflict_candidate_eval,
            "prior_assertion_preserved": True,
            "conflicting_assertion_preserved": True,
            "automatic_winner_or_resolution": False,
        },
        "D2-NOMAT-01": {
            "finding": replay_eval.finding.to_dict() if replay_eval.finding else None,
            "finding_evaluation": replay_eval.to_dict(),
            "change_candidate": None,
            "candidate_disposition": {
                "disposition": "no_change_candidate_yet",
                "reason_code": "no_material_finding",
            },
        },
        "D2-CORRECT-01": {
            "finding": correct_eval.finding.to_dict(),
            "finding_evaluation": correct_eval.to_dict(),
            "change_candidate": correct_candidate.to_dict(),
            "candidate_evaluation": correct_candidate_eval,
            "claim_value_overwrite_in_place": False,
        },
    }, {
        "D2-EVIDENCE-01": evidence_candidate,
        "D2-CONFLICT-01": conflict_candidate,
        "D2-CORRECT-01": correct_candidate,
    }


_SPECIAL_RESOLUTION_CONFIG = {
    "D2-EVIDENCE-01": _ResolutionCaseConfig(
        resolution_ref="RES-E01",
        resolution_type="revise_existing_identity",
        target_canonical_ref="TEST-CLM-SECOND-CYCLE-APPROVED",
        prior_identity_ref="TEST-CLM-SECOND-CYCLE-APPROVED",
        prior_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "second_after_school_cycle",
            "object": "approved",
        },
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "second_after_school_cycle",
            "object": "approved",
        },
        material_delta_dimensions=("evidence",),
        evidence_basis_only=True,
    ),
    "D2-CONFLICT-01": _ResolutionCaseConfig(
        resolution_ref="RES-CF01",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-TECHNICAL-OPERATION-CONFLICT",
        prior_identity_ref="TEST-CLM-TECHNICAL-OPERATION-STABLE",
        prior_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "technical_operation",
            "object": "stable_after_first_session",
        },
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "technical_operation",
            "object": "intermittent_after_first_session",
        },
        material_delta_dimensions=("object", "conflict"),
    ),
    "D2-CORRECT-01": _ResolutionCaseConfig(
        resolution_ref="RES-CR01",
        resolution_type="create_new_identity",
        target_canonical_ref="TEST-CLM-PILOT-CAPACITY-14",
        prior_identity_ref="TEST-CLM-PILOT-CAPACITY-16",
        prior_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "pilot_capacity",
            "object": 16,
        },
        proposed_dimensions={
            "subject": "minecraft_esports_pilot",
            "predicate": "pilot_capacity",
            "object": 14,
        },
        material_delta_dimensions=("object",),
        same_object_relevant_for_review=True,
    ),
}


def _scenario_identity_snapshot(
    candidate: ChangeCandidateRevision,
    *,
    identity_ref: str | None,
    dimensions: dict[str, Any] | None,
) -> IdentitySnapshot | None:
    if dimensions is None:
        return None
    return IdentitySnapshot.from_dimensions(
        semantic_unit_kind=candidate.semantic_unit_kind,
        identity_ref=identity_ref,
        dimensions=dimensions,
        evidence_refs=candidate.evidence_refs,
    )


def _synthetic_review_fixture(
    request: Any,
) -> ReviewRecord:
    if request.review_type == "technical_validation":
        reviewer_ref = "SYNTHETIC-AUTHORIZED-VALIDATOR"
    elif request.review_type == "independent_quality_review":
        reviewer_ref = "SYNTHETIC-INDEPENDENT-HUMAN-REVIEWER"
    else:
        reviewer_ref = "SYNTHETIC-PROJECT-OWNER-REVIEWER"
    return ReviewRecord.create(
        review_request_ref=request.review_request_ref,
        review_type=request.review_type,
        subject_ref=request.subject_ref,
        subject_version=request.subject_version,
        review_scope=request.review_scope,
        reviewer_ref=reviewer_ref,
        reviewer_authority=request.required_reviewer_authority,
        result="passed",
        findings=("synthetic test review fixture validates D5 orchestration only",),
        conditions=(),
        evidence_reviewed_refs=request.evidence_and_context_refs,
        rule_basis_refs=request.rule_basis_refs,
        profile_refs=request.profile_refs,
        reviewed_at="2026-08-14T00:00:00+02:00",
        synthetic_test_fixture=True,
    )


_D6_HASH_RULE = HashRuleBinding(
    algorithm="sha256",
    canonicalization_profile_ref="synthetic_test.canonical-json@0.1",
    approval_context_ref="synthetic_test_hash_rule_binding",
    synthetic_test_fixture=True,
)


def _publication_ref(
    subject_type: str,
    stable_id: str,
    *,
    version: str = "0.1",
    authority_context: str = "Semantic Core",
) -> PublicationSemanticReference:
    return PublicationSemanticReference(
        subject_type=subject_type,
        stable_id=stable_id,
        version=version,
        authority_context=authority_context,
    )


def _evidence_representation_text(item: dict[str, Any]) -> str:
    return f"Evidence remains addressable: {item['evidence_address_ref']}"


def _d6_assembly_inputs(
    case_ref: str,
    candidate: ChangeCandidateRevision,
    config: _ResolutionCaseConfig,
) -> tuple[dict[str, Any], PublicationAssemblyPlan, PublicationRepresentation]:
    slug = case_ref.lower().replace("_", "-")
    mapping_slug = case_ref.upper().replace("_", "-")
    entity_ref = "ENT-MINECRAFT-ESPORTS-PILOT"
    ko_ref = _publication_ref(
        "knowledge_object",
        "KO-GT-ME-ESPORTS-PILOT",
        version="0.2",
    )
    claim_records: list[dict[str, Any]] = []
    event_records: list[dict[str, Any]] = []
    if candidate.semantic_unit_kind == "event":
        event_records.append(
            {
                "event_ref": config.target_canonical_ref,
                "event_type_ref": "hr005.pilot.event",
                "label": candidate.proposed_semantic_effect,
                "event_time": (
                    candidate.event_time_values[0]
                    if candidate.event_time_values
                    else None
                ),
                "time_precision": (
                    "instant" if candidate.event_time_values else "unknown"
                ),
                "time_modality": "actual",
            }
        )
    else:
        if case_ref == "D2-CONFLICT-01":
            claim_records.append(
                {
                    "claim_ref": config.prior_identity_ref,
                    "subject_ref": entity_ref,
                    "predicate_ref": config.prior_dimensions["predicate"],
                    "value": config.prior_dimensions["object"],
                    "object_ref": None,
                    "epistemic_status": "reported",
                    "time": [],
                }
            )
        claim_records.append(
            {
                "claim_ref": config.target_canonical_ref,
                "subject_ref": entity_ref,
                "predicate_ref": config.proposed_dimensions.get(
                    "predicate", "hr005.knowledge_delta"
                ),
                "value": config.proposed_dimensions.get(
                    "object", config.proposed_dimensions
                ),
                "object_ref": None,
                "epistemic_status": (
                    candidate.epistemic_context[0]
                    if candidate.epistemic_context
                    else "reported"
                ),
                "time": [
                    {
                        "role": "event_time",
                        "value": value,
                        "precision": "instant",
                        "modality": "actual",
                    }
                    for value in candidate.event_time_values
                ],
            }
        )

    subject_refs = [("claim", item["claim_ref"]) for item in claim_records] or [
        ("event", item["event_ref"]) for item in event_records
    ]
    evidence_links = []
    for index, evidence_ref in enumerate(candidate.evidence_refs):
        subject_type, subject_ref = subject_refs[min(index, len(subject_refs) - 1)]
        evidence_links.append(
            {
                "evidence_link_ref": f"EL-{mapping_slug}-{index + 1:02d}",
                "subject_type": subject_type,
                "subject_ref": subject_ref,
                "claim_ref": subject_ref if subject_type == "claim" else None,
                "evidence_address_ref": evidence_ref,
                "role": "supports" if index else "reports",
            }
        )

    conflict_records = []
    if case_ref == "D2-CONFLICT-01":
        conflict_records.append(
            {
                "conflict_set_ref": "CF-HR005-TECHNICAL-OPERATION",
                "claim_refs": [item["claim_ref"] for item in claim_records],
                "conflict_dimensions": ["proposition", "evidence"],
                "preferred_claim_ref": None,
                "preference_context": None,
                "rationale": (
                    "Synthetic unresolved conflict; no winner or preference selected."
                ),
            }
        )

    semantic = {
        "entities": [
            {
                "entity_ref": entity_ref,
                "label": "Synthetic Minecraft esports pilot",
                "class": "pilot",
            }
        ],
        "claims": claim_records,
        "evidence_links": evidence_links,
        "events": event_records,
        "participations": [],
        "conflict_sets": conflict_records,
    }

    policy_anchor_id = "PA-SYNTHETIC-PUBLICATION"
    policy_anchor = PublicationPolicyAnchor(
        policy_anchor_id=policy_anchor_id,
        subject_refs=(ko_ref,),
        policy_refs=("SYNTHETIC-PUBLISH-POLICY@0.1",),
        dimensions=("publish",),
        narrative_anchor=f"policy-{slug}",
    )
    binding_refs = [
        *(_publication_ref("claim", item["claim_ref"]) for item in claim_records),
        *(_publication_ref("event", item["event_ref"]) for item in event_records),
        *(
            _publication_ref("evidence_link", item["evidence_link_ref"])
            for item in evidence_links
        ),
    ]
    plan = PublicationAssemblyPlan(
        knowledge_object_id=ko_ref.stable_id,
        knowledge_object_version=ko_ref.version,
        title=f"Synthetic HR-005 publication package {case_ref}",
        language="en",
        primary_kind=(
            "event_update"
            if candidate.semantic_unit_kind == "event"
            else "claim_update"
        ),
        knowledge_functions=("descriptive", "traceable_enrichment"),
        applicability=PublicationApplicability(
            entity_refs=(_publication_ref("entity", entity_ref),),
            purposes=("controlled_knowledge_publication",),
            valid_time=tuple(
                {"scope_ref": scope_ref} for scope_ref in candidate.time_scope
            ),
        ),
        profile_refs=(),
        policy_anchors=(policy_anchor,),
        policy_bindings=tuple(
            PublicationPolicyBinding(
                semantic_ref=semantic_ref,
                policy_anchor_ids=(policy_anchor_id,),
            )
            for semantic_ref in binding_refs
        ),
        evidence_link_interpretation_provenance=(
            PublicationInterpretationProvenance(
                producer_ref=_publication_ref(
                    "producer",
                    "HR005-SYNTHETIC-SCENARIO-RUNNER",
                    authority_context="Platform and Integration",
                ),
                method="deterministic_synthetic_test_fixture_mapping",
                produced_at="2026-08-15T10:00:00+02:00",
            )
        ),
    )

    claim_items = tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref("claim", item["claim_ref"]),
            narrative_anchor=f"claim-{slug}-{index + 1}",
            representation_role="knowledge_statement",
            rendered_text=(
                f"{item['predicate_ref']}: "
                f"{json.dumps(item['value'], ensure_ascii=False)}"
            ),
            heading=f"Claim {index + 1}",
            mapping_id=f"CVM-{mapping_slug}-CLAIM-{index + 1:02d}",
            material=True,
        )
        for index, item in enumerate(claim_records)
    )
    event_items = tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref("event", item["event_ref"]),
            narrative_anchor=f"event-{slug}-{index + 1}",
            representation_role="event_note",
            rendered_text=item["label"],
            heading=f"Event {index + 1}",
            mapping_id=f"CVM-{mapping_slug}-EVENT-{index + 1:02d}",
            material=True,
        )
        for index, item in enumerate(event_records)
    )
    evidence_items = tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref("evidence_link", item["evidence_link_ref"]),
            narrative_anchor=f"evidence-{slug}-{index + 1}",
            representation_role="evidence_note",
            rendered_text=_evidence_representation_text(item),
            heading=f"Evidence {index + 1}",
            mapping_id=f"CVM-{mapping_slug}-EVIDENCE-{index + 1:02d}",
            material=True,
        )
        for index, item in enumerate(evidence_links)
    )
    conflict_items = tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref("conflict_set", item["conflict_set_ref"]),
            narrative_anchor=f"conflict-{slug}-{index + 1}",
            representation_role="conflict_note",
            rendered_text=item["rationale"],
            heading=f"Conflict {index + 1}",
            mapping_id=f"CVM-{mapping_slug}-CONFLICT-{index + 1:02d}",
            material=True,
        )
        for index, item in enumerate(conflict_records)
    )
    representation = PublicationRepresentation(
        summary=PublicationRepresentationSection(
            narrative_anchor=f"summary-{slug}",
            heading="Summary",
            rendered_text=candidate.proposed_semantic_effect,
            semantic_ref=ko_ref,
            representation_role="summary",
            mapping_id=f"CVM-{mapping_slug}-SUMMARY",
            material=True,
        ),
        applicability=PublicationRepresentationSection(
            narrative_anchor=f"applicability-{slug}",
            heading="Applicability",
            rendered_text=(
                "Synthetic pilot-only applicability; no generalization permitted."
            ),
            semantic_ref=ko_ref,
            representation_role="applicability_note",
            mapping_id=f"CVM-{mapping_slug}-APPLICABILITY",
            material=True,
        ),
        details=PublicationRepresentationSection(
            narrative_anchor=f"details-{slug}",
            heading="Context",
            rendered_text=(
                "Candidate, Resolution, evidence, time, epistemic state, and "
                "constraints remain externally bound in the immutable package."
            ),
        ),
        claims=PublicationRepresentationSection(
            narrative_anchor=f"claims-{slug}",
            heading="Claims",
            items=claim_items,
        ),
        events=PublicationRepresentationSection(
            narrative_anchor=f"events-{slug}",
            heading="Events",
            items=event_items,
        ),
        evidence=PublicationRepresentationSection(
            narrative_anchor=f"evidence-{slug}",
            heading="Evidence and provenance",
            items=evidence_items,
        ),
        conflicts=PublicationRepresentationSection(
            narrative_anchor=f"conflicts-{slug}",
            heading="Conflicts and uncertainty",
            items=conflict_items,
        ),
        policy=PublicationRepresentationSection(
            narrative_anchor=f"policy-{slug}",
            heading="Policy anchors",
            rendered_text=(
                "Synthetic test policy anchor only; this is not an active policy."
            ),
            semantic_ref=ko_ref,
            representation_role="policy_note",
            mapping_id=f"CVM-{mapping_slug}-POLICY",
            material=True,
        ),
        publication=PublicationRepresentationSection(
            narrative_anchor=f"publication-{slug}",
            heading="Review and publication",
            rendered_text="Publication state: `unpublished`; execution not reached.",
        ),
        body_language="en",
    )
    return semantic, plan, representation


def _per_candidate_rebuild_conformance_plan(
    case_ref: str,
    manifest: dict[str, Any],
    as_of: str,
) -> ExperienceProjectionPlan:
    selected_subject: tuple[str, str] | None = None
    for subject_type, collection, ref_key in (
        ("claim", "claims", "claim_ref"),
        ("event", "events", "event_ref"),
        ("event_participation", "event_participations", "participation_ref"),
    ):
        subjects = manifest.get(collection, [])
        if subjects:
            selected_subject = (
                subject_type,
                str(subjects[0][ref_key]["stable_id"]),
            )
            break
    if selected_subject is None:
        raise RuntimeError(f"{case_ref}: published semantic subject missing")

    subject_type, stable_id = selected_subject
    selector = ExperienceSemanticSelector(subject_type, stable_id=stable_id)
    stable_knowledge_ref = str(manifest["knowledge_object_id"])
    version = str(manifest["knowledge_object_version"])
    return ExperienceProjectionPlan(
        experience_ref=f"EXP-PUBLICATION-BOUND-CONFORMANCE-{case_ref}",
        focus_knowledge_object_ref=f"{stable_knowledge_ref}@{version}",
        as_of=as_of,
        phases=(
            ExperiencePhasePlan(
                "published_semantic_subject",
                (selector,),
            ),
        ),
        threads=(
            ExperienceThreadPlan(
                "published_semantic_subject",
                (stable_id,),
            ),
        ),
        gaps=(
            ExperienceGapPlan(
                "publication_bound_semantic_subject",
                "Is the exact published semantic subject available?",
                "published_semantic_subject",
                (stable_id,),
                progression_requirements=(selector,),
                status_when_progressed="resolved",
            ),
        ),
        reuse_context=ExperienceReuseContext(
            domain_terms=("technical-conformance",),
            topic_terms=("publication-bound-rebuild",),
            purpose_terms=("deterministic-rebuild-verification",),
        ),
    )


def _run_per_candidate_publication_bound_rebuild_conformance(
    case_ref: str,
    final_manifest: dict[str, Any],
    final_markdown_body: str,
    publication_record: PublicationRecord,
) -> dict[str, Any]:
    plan = _per_candidate_rebuild_conformance_plan(
        case_ref,
        final_manifest,
        publication_record.executed_at,
    )
    store = ExperienceProjectionStore()
    rebuilder = PublicationBoundExperienceRebuilder()
    first = rebuilder.rebuild(
        manifest=final_manifest,
        markdown_body=final_markdown_body,
        plan=plan,
        publication_record=publication_record,
        store=store,
    )
    if first.disposition != "rebuilt" or first.projection is None:
        raise RuntimeError(
            f"{case_ref}: publication-bound conformance rebuild failed: "
            f"{first.reason_code}"
        )
    first_projection = first.projection
    if not store.delete(first_projection.experience_projection_ref):
        raise RuntimeError(f"{case_ref}: conformance projection delete failed")
    second = rebuilder.rebuild(
        manifest=final_manifest,
        markdown_body=final_markdown_body,
        plan=plan,
        publication_record=publication_record,
        store=store,
    )
    if second.disposition != "rebuilt" or second.projection is None:
        raise RuntimeError(
            f"{case_ref}: deterministic conformance rebuild failed: "
            f"{second.reason_code}"
        )
    rebuilt_projection = second.projection
    if first_projection.to_dict() != rebuilt_projection.to_dict():
        raise RuntimeError(f"{case_ref}: conformance rebuild is not deterministic")
    return {
        "status": "publication_bound_rebuild_conformance_verified",
        "assurance_scope": "per_candidate_technical_conformance_only",
        "publication_record_ref": publication_record.publication_record_ref,
        "source_publication_unit_ref": first.source_publication_unit_ref,
        "successful_immutable_publication_record_verified": True,
        "exact_publication_binding_verified": True,
        "knowledge_content_hash_binding_verified": True,
        "published_state_binding_verified": True,
        "plan_shape": {
            "phase_count": len(plan.phases),
            "thread_count": len(plan.threads),
            "gap_count": len(plan.gaps),
        },
        "first_projection_signature": first_projection.semantic_signature(),
        "first_projection_deleted": True,
        "rebuilt_projection_signature": rebuilt_projection.semantic_signature(),
        "deterministic_rebuild": True,
        "rich_experience_acceptance_claimed": False,
        "derived_projection_is_canonical_source": False,
    }


def _projection_from_dict(payload: dict[str, Any]) -> ExperienceProjection:
    return ExperienceProjection(
        experience_projection_ref=payload["experience_projection_ref"],
        semantic_hash=payload["semantic_hash"],
        projection_schema_version=payload["projection_schema_version"],
        builder_version=payload["builder_version"],
        experience_ref=payload["experience_ref"],
        focus_knowledge_object_ref=payload["focus_knowledge_object_ref"],
        publication_unit_ref=dict(payload["publication_unit_ref"]),
        as_of=payload["as_of"],
        experience_completeness=payload["experience_completeness"],
        phases=tuple(ExperiencePhase(**item) for item in payload["phases"]),
        threads=tuple(ExperienceThread(**item) for item in payload["threads"]),
        gaps=tuple(ExperienceGap(**item) for item in payload["gaps"]),
        reuse_context=ExperienceReuseContext(**payload["reuse_context"]),
        continuation_requirements=tuple(
            ExperienceContinuationRequirement(**item)
            for item in payload["continuation_requirements"]
        ),
        lesson_learned_eligibility=payload["lesson_learned_eligibility"],
        lesson_learned_candidates=tuple(payload["lesson_learned_candidates"]),
    )


def _load_baseline_experience() -> tuple[ExperienceProjection, dict[str, Any]]:
    payload = json.loads(BASELINE_EXPERIENCE_PATH.read_text(encoding="utf-8"))
    projection = _projection_from_dict(payload)
    if (
        projection.experience_ref != "EXP-GT-ME-ESPORTS-PILOT-RMIS-2024"
        or projection.focus_knowledge_object_ref != "KO-GT-ME-ESPORTS-PILOT@0.1"
    ):
        raise RuntimeError("validated pre-HR005 Experience baseline mismatch")
    return projection, payload


def _without_publication_section(markdown_body: str, anchor: str) -> str:
    marker = f'<a id="{anchor}"></a>'
    lines = markdown_body.splitlines(keepends=True)
    try:
        start = next(
            index for index, line in enumerate(lines) if line.rstrip("\r\n") == marker
        )
    except StopIteration as exc:
        raise RuntimeError(f"publication anchor missing: {anchor}") from exc
    end = len(lines)
    for index in range(start + 1, len(lines) - 1):
        if lines[index].startswith('<a id="') and lines[index + 1].startswith("## "):
            end = index
            break
    return "".join((*lines[:start], *lines[end:])).rstrip()


def _merge_unique(
    groups: tuple[list[Any], ...],
    key,
) -> list[Any]:
    merged: dict[str, Any] = {}
    for group in groups:
        for item in group:
            item_key = str(key(item))
            merged.setdefault(item_key, deepcopy(item))
    return list(merged.values())


def _cumulative_published_knowledge(
    positive_d5: dict[str, dict[str, Any]],
) -> tuple[
    dict[str, Any],
    str,
    PublicationRecord,
    list[str],
    dict[str, Any],
]:
    baseline_document = load_publication_unit(BASELINE_PUBLICATION_PATH)
    source_units = [
        positive_d5[ref]["d6"]["final_publication_unit"] for ref in sorted(positive_d5)
    ]
    source_manifests = [unit["manifest"] for unit in source_units]
    source_record_refs = [
        positive_d5[ref]["d6"]["publication_record"]["publication_record_ref"]
        for ref in sorted(positive_d5)
    ]
    manifest = deepcopy(baseline_document.manifest)
    current_contract = source_manifests[0]
    for field in (
        "document_type",
        "schema_ref",
        "template_ref",
        "semantic_model_ref",
        "vocabulary_set_ref",
    ):
        manifest[field] = current_contract[field]
    manifest["knowledge_object_version"] = "0.2"

    collection_keys = {
        "claims": lambda item: item["claim_ref"]["stable_id"],
        "events": lambda item: item["event_ref"]["stable_id"],
        "event_participations": lambda item: item["participation_ref"]["stable_id"],
        "evidence_links": lambda item: item["evidence_link_id"],
        "conflict_sets": lambda item: item["conflict_set_id"],
        "policy_anchors": lambda item: item["policy_anchor_id"],
        "cross_view_mappings": lambda item: item["mapping_id"],
        "structural_relationships": lambda item: json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
        ),
    }
    for field, item_key in collection_keys.items():
        groups = tuple(
            [deepcopy(manifest.get(field, []))]
            + [list(source.get(field, [])) for source in source_manifests]
        )
        manifest[field] = _merge_unique(groups, item_key)

    for field in (
        "knowledge_functions",
        "profile_refs",
        "review_record_refs",
        "policy_decision_refs",
    ):
        manifest[field] = list(
            dict.fromkeys(
                [
                    *manifest.get(field, []),
                    *(
                        value
                        for source in source_manifests
                        for value in source.get(field, [])
                    ),
                ]
            )
        )

    applicability = manifest["applicability"]
    for field in ("domain_refs", "entity_refs", "organization_refs", "product_refs"):
        groups = tuple(
            [list(applicability.get(field, []))]
            + [
                list(source.get("applicability", {}).get(field, []))
                for source in source_manifests
            ]
        )
        applicability[field] = _merge_unique(
            groups,
            lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )
    applicability["purposes"] = list(
        dict.fromkeys(
            [
                *applicability.get("purposes", []),
                *(
                    value
                    for source in source_manifests
                    for value in source.get("applicability", {}).get(
                        "purposes",
                        [],
                    )
                ),
            ]
        )
    )

    publication_record_ref = "PREC-HR005-CUMULATIVE-EXPERIENCE-ACCEPTANCE"
    canonical_path = (
        "Knowledge/Test-Isolated/HR-005/Cumulative/KO-GT-ME-ESPORTS-PILOT@0.2.md"
    )
    executed_at = "2026-08-15T10:08:00+02:00"
    manifest["canonical_path"] = canonical_path
    manifest["publication"] = {
        "publication_state": "published",
        "publication_record_ref": publication_record_ref,
        "publication_finalization_plan_ref": (
            "PFP-HR005-CUMULATIVE-EXPERIENCE-ACCEPTANCE"
        ),
        "published_at": executed_at,
        "publisher_ref": "SYNTHETIC-HR005-CUMULATIVE-ACCEPTANCE-PUBLISHER",
        "predecessor_publication_ref": None,
    }
    manifest["integrity"] = {
        "cross_view_validation": {
            "status": "pass",
            "report_ref": "CONF-HR005-CUMULATIVE-EXPERIENCE-ACCEPTANCE",
        }
    }

    publication_anchor = manifest["human_readable"]["publication_anchor"]
    knowledge_sections = [
        _without_publication_section(
            baseline_document.markdown_body,
            publication_anchor,
        ),
        *(
            _without_publication_section(
                unit["markdown_body"],
                unit["manifest"]["human_readable"]["publication_anchor"],
            )
            for unit in source_units
        ),
    ]
    markdown_body = (
        "\n\n".join(knowledge_sections)
        + f'\n\n<a id="{publication_anchor}"></a>\n'
        + "## Review and publication\n\n"
        + "Publication state: `published` in the dedicated test-isolated "
        + "cumulative D8/D9 acceptance fixture. No canonical or Vault write "
        + "was performed.\n"
    )

    hash_binding = HashRuleBinding(
        algorithm="sha256",
        canonicalization_profile_ref="synthetic_test.canonical-json@0.1",
        approval_context_ref="synthetic_test_hash_rule_binding",
        synthetic_test_fixture=True,
    )
    content_hash = publication_unit_knowledge_content_hash(
        manifest,
        markdown_body,
        hash_binding,
    )
    manifest["integrity"]["content_hash"] = content_hash.to_dict()
    final_representation_hash = publication_unit_representation_hash(
        manifest,
        markdown_body,
        hash_binding,
        scope="publication_unit_final_representation",
    )
    target = TestIsolatedPublicationTarget(
        expected_prior_states=(),
        target_ref="synthetic_hr005_cumulative_acceptance",
    )
    transaction_ref = target.commit(
        canonical_path,
        MaterializedPublicationState.create(manifest, markdown_body),
        content_hash.value,
    )
    reread = target.read(canonical_path)
    final_state_verified = (
        reread is not None
        and reread.manifest == manifest
        and reread.markdown_body == markdown_body
    )
    if not final_state_verified:
        raise RuntimeError("cumulative acceptance fixture final-state mismatch")
    record = PublicationRecord(
        publication_record_ref=publication_record_ref,
        publication_request_ref="PRQ-HR005-CUMULATIVE-EXPERIENCE-ACCEPTANCE",
        publication_change_set_ref="PCS-HR005-CUMULATIVE-EXPERIENCE-ACCEPTANCE",
        publication_finalization_plan_refs=(
            "PFP-HR005-CUMULATIVE-EXPERIENCE-ACCEPTANCE",
        ),
        published_unit_refs=("KO-GT-ME-ESPORTS-PILOT@0.2",),
        target_refs=(canonical_path, "synthetic_hr005_cumulative_acceptance"),
        previous_states=(),
        new_states=(
            FinalPublicationState(
                publication_unit_ref="KO-GT-ME-ESPORTS-PILOT@0.2",
                canonical_path=canonical_path,
                publication_state="published",
                publication_record_ref=publication_record_ref,
                published_at=executed_at,
                publisher_ref=("SYNTHETIC-HR005-CUMULATIVE-ACCEPTANCE-PUBLISHER"),
                predecessor_publication_ref=None,
            ),
        ),
        executor_ref="synthetic_test_cumulative_acceptance_executor",
        publication_authority_ref="synthetic_test_publication_authority",
        policy_decision_ref="PDEC-HR005-CUMULATIVE-ACCEPTANCE",
        review_record_refs=(),
        conformance_report_refs=("CONF-HR005-CUMULATIVE-EXPERIENCE-ACCEPTANCE",),
        executed_at=executed_at,
        transaction_or_commit_ref=transaction_ref,
        knowledge_content_hashes=(content_hash,),
        final_representation_hashes=(final_representation_hash,),
        outcome="success",
        diagnostics=("synthetic_cumulative_d8_d9_acceptance_fixture",),
        compensation_refs=(),
    )
    return (
        manifest,
        markdown_body,
        record,
        source_record_refs,
        {
            "test_isolated": True,
            "target_commit_count": target.commit_count,
            "final_state_verified": final_state_verified,
            "transaction_or_commit_ref": transaction_ref,
        },
    )


def _cumulative_experience_plan(
    manifest: dict[str, Any],
    baseline_payload: dict[str, Any],
) -> ExperienceProjectionPlan:
    subject_types = {
        item[ref_key]["stable_id"]: subject_type
        for subject_type, field, ref_key in (
            ("claim", "claims", "claim_ref"),
            ("event", "events", "event_ref"),
            (
                "event_participation",
                "event_participations",
                "participation_ref",
            ),
        )
        for item in manifest.get(field, [])
    }
    selector = ExperienceSemanticSelector
    baseline_phase_by_ref = {
        item["phase_ref"]: item for item in baseline_payload["phases"]
    }

    def baseline_requirements(phase_ref: str):
        return tuple(
            selector(subject_types[semantic_ref], stable_id=semantic_ref)
            for semantic_ref in baseline_phase_by_ref[phase_ref]["semantic_basis_refs"]
        )

    phases = (
        *(
            ExperiencePhasePlan(phase_ref, baseline_requirements(phase_ref))
            for phase_ref in ("context", "intent", "proposal", "decision", "scope")
        ),
        ExperiencePhasePlan(
            "execution",
            (
                selector(
                    "event",
                    stable_id="EVT-INTERNAL-PILOT",
                    time_modality="actual",
                ),
            ),
            required_for_lesson_learned=True,
        ),
        ExperiencePhasePlan(
            "evaluation",
            (
                selector(
                    "event",
                    stable_id="TEST-EVT-HR005-D09",
                    time_modality="actual",
                ),
                selector("claim", stable_id="TEST-CLM-HR005-D02"),
                selector("claim", stable_id="TEST-CLM-HR005-D03"),
                selector("claim", stable_id="TEST-CLM-HR005-D04"),
            ),
            required_for_lesson_learned=True,
        ),
        ExperiencePhasePlan(
            "outcome",
            (selector("claim", stable_id="TEST-CLM-HR005-D05"),),
            required_for_lesson_learned=True,
        ),
        ExperiencePhasePlan(
            "follow_up",
            (
                selector("claim", stable_id="TEST-CLM-HR005-D06"),
                selector("claim", stable_id="TEST-CLM-HR005-D07"),
                selector("claim", stable_id="TEST-CLM-HR005-D08"),
            ),
            status_when_supported="partial",
        ),
    )
    gap_progression = {
        "EXP-GAP-PILOT-EXECUTION": (
            (selector("event", stable_id="EVT-INTERNAL-PILOT"),),
            "resolved",
        ),
        "EXP-GAP-PILOT-EVALUATION-OCCURRENCE": (
            (selector("event", stable_id="TEST-EVT-HR005-D09"),),
            "resolved",
        ),
        "EXP-GAP-PILOT-EVALUATION-RESULT": (
            (
                selector("claim", stable_id="TEST-CLM-HR005-D02"),
                selector("claim", stable_id="TEST-CLM-HR005-D03"),
                selector("claim", stable_id="TEST-CLM-HR005-D04"),
            ),
            "resolved",
        ),
        "EXP-GAP-PILOT-OUTCOME": (
            (selector("claim", stable_id="TEST-CLM-HR005-D05"),),
            "resolved",
        ),
        "EXP-GAP-CLASSROOM-INTEGRATION-FOLLOWUP": (
            (selector("claim", stable_id="TEST-CLM-HR005-D07"),),
            "informed_unresolved",
        ),
        "EXP-GAP-EXTERNAL-COMPETITION-FOLLOWUP": (
            (selector("claim", stable_id="TEST-CLM-HR005-D08"),),
            "informed_unresolved",
        ),
        "EXP-GAP-PILOT-REPETITION": (
            (selector("claim", stable_id="TEST-CLM-HR005-D06"),),
            "informed_unresolved",
        ),
    }
    gaps = tuple(
        ExperienceGapPlan(
            gap_ref=item["gap_ref"],
            question=item["question"],
            phase_ref=item["phase_ref"],
            semantic_basis_refs=tuple(item["semantic_basis_refs"]),
            progression_requirements=gap_progression[item["gap_ref"]][0],
            status_when_progressed=gap_progression[item["gap_ref"]][1],
        )
        for item in baseline_payload["gaps"]
    )
    return ExperienceProjectionPlan(
        experience_ref=baseline_payload["experience_ref"],
        focus_knowledge_object_ref="KO-GT-ME-ESPORTS-PILOT@0.2",
        as_of="2025-03-14T11:30:00+01:00",
        phases=phases,
        threads=tuple(
            ExperienceThreadPlan(
                thread_ref=item["thread_ref"],
                semantic_refs=tuple(item["semantic_refs"]),
            )
            for item in baseline_payload["threads"]
        ),
        gaps=gaps,
        reuse_context=ExperienceReuseContext(**baseline_payload["reuse_context"]),
        continuation=ExperienceContinuationPlan(
            continuation_ref="EXP-CONT-01",
            critical_gap_refs=tuple(
                item["gap_ref"] for item in baseline_payload["gaps"]
            ),
            search_after="2025-03-14T11:30:00+01:00",
            trigger_purposes=(
                "similar_experience_retrieval",
                "experience_reuse",
                "lesson_learned_discovery",
            ),
        ),
    )


def _run_cumulative_experience_acceptance(
    positive_d5: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    projection_a, baseline_payload = _load_baseline_experience()
    (
        manifest,
        markdown_body,
        publication_record,
        source_record_refs,
        publication_proof,
    ) = _cumulative_published_knowledge(positive_d5)
    plan = _cumulative_experience_plan(manifest, baseline_payload)
    store = ExperienceProjectionStore((projection_a,))
    rebuilder = PublicationBoundExperienceRebuilder()
    first = rebuilder.rebuild(
        manifest=manifest,
        markdown_body=markdown_body,
        plan=plan,
        publication_record=publication_record,
        store=store,
    )
    if first.disposition != "rebuilt" or first.projection is None:
        raise RuntimeError(
            "cumulative D8 Experience rebuild failed: " + first.reason_code
        )
    projection_b = first.projection
    if store.status(projection_a.experience_projection_ref) != "stale":
        raise RuntimeError("cumulative D8 baseline projection not stale")
    if not store.delete(projection_b.experience_projection_ref):
        raise RuntimeError("cumulative D9 delete B failed")
    second = rebuilder.rebuild(
        manifest=manifest,
        markdown_body=markdown_body,
        plan=plan,
        publication_record=publication_record,
        store=store,
    )
    if second.disposition != "rebuilt" or second.projection is None:
        raise RuntimeError(
            "cumulative D9 Experience rebuild failed: " + second.reason_code
        )
    projection_c = second.projection
    if projection_b.to_dict() != projection_c.to_dict():
        raise RuntimeError("cumulative D9 B/C semantic mismatch")

    phases_a = {item.phase_ref: item for item in projection_a.phases}
    phases_b = {item.phase_ref: item for item in projection_b.phases}
    gaps_a = {item.gap_ref: item for item in projection_a.gaps}
    gaps_b = {item.gap_ref: item for item in projection_b.gaps}
    changed_phase_refs = [
        ref for ref in phases_b if phases_a[ref].status != phases_b[ref].status
    ]
    changed_gap_refs = [
        ref for ref in gaps_b if gaps_a[ref].status != gaps_b[ref].status
    ]
    new_semantic_basis_refs = sorted(
        {ref for phase in projection_b.phases for ref in phase.semantic_basis_refs}
        - {ref for phase in projection_a.phases for ref in phase.semantic_basis_refs}
    )
    eligibility_changed = (
        projection_a.lesson_learned_eligibility
        != projection_b.lesson_learned_eligibility
    )
    administrative_only = not (
        changed_phase_refs
        or changed_gap_refs
        or new_semantic_basis_refs
        or eligibility_changed
    )
    return {
        "status": "rebuilt_and_rebuild_verified",
        "acceptance_scope": "dedicated_cumulative_d8_d9_test_fixture",
        "d6_d7_candidate_paths_modified": False,
        "source_publication_record_refs": source_record_refs,
        "publication_record": publication_record.to_dict(),
        "publication_record_validation": "accepted_by_publication_bound_rebuilder",
        "test_isolated_publication_proof": publication_proof,
        "source_publication_unit_ref": first.source_publication_unit_ref,
        "projection_a_source": {
            "artifact_path": str(BASELINE_EXPERIENCE_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(BASELINE_EXPERIENCE_PATH.read_bytes()).hexdigest(),
        },
        "projection_a": projection_a.to_dict(),
        "projection_a_status": "stale",
        "projection_b": projection_b.to_dict(),
        "projection_b_deleted": True,
        "projection_c": projection_c.to_dict(),
        "a_differs_from_b": (
            projection_a.semantic_signature() != projection_b.semantic_signature()
        ),
        "a_b_delta_is_administrative_only": administrative_only,
        "semantic_delta": {
            "changed_phase_refs": changed_phase_refs,
            "changed_gap_refs": changed_gap_refs,
            "new_semantic_basis_refs": new_semantic_basis_refs,
            "lesson_learned_eligibility_changed": eligibility_changed,
        },
        "b_semantically_equivalent_to_c": (
            projection_b.semantic_signature() == projection_c.semantic_signature()
        ),
        "derived_projection_is_canonical_source": False,
        "direct_experience_update_from_lifecycle_intermediates": False,
        "test_isolated_publication": True,
        "canonical_write": False,
        "cp_wiki_write": False,
    }


def _run_d6_case(
    case_ref: str,
    candidate: ChangeCandidateRevision,
    config: _ResolutionCaseConfig,
    lifecycle_candidate: Any,
    resolution_decision: Any,
    version_projection: Any,
    review_records: tuple[ReviewRecord, ...],
    output_root: Path,
) -> dict[str, Any]:
    review_refs = tuple(record.review_record_ref for record in review_records)
    finalization_plan_ref = f"PFP-{case_ref}"
    planned_policy_decision_ref = f"PDEC-{case_ref}-PLANNED"
    conformance_refs = (
        f"CONF-{case_ref}-CORE",
        f"CONF-{case_ref}-CROSS-VIEW",
    )
    expected_prior = ExpectedPriorState(
        stable_knowledge_object_ref="KO-GT-ME-ESPORTS-PILOT",
        knowledge_object_version_ref="KO-GT-ME-ESPORTS-PILOT@0.1",
        publication_state="unpublished",
        stable_identity_state="active_unpublished",
        subject_state_refs=(config.prior_identity_ref or "KO-GT-ME-ESPORTS-PILOT@0.1",),
        expected_content_hashes=(
            (
                "KO-GT-ME-ESPORTS-PILOT@0.1",
                "sha256:synthetic-baseline-fixture",
            ),
        ),
        candidate_revision_ref=(lifecycle_candidate.lifecycle_candidate_revision_ref),
        resolution_decision_ref=resolution_decision.resolution_decision_ref,
        required_candidate_review_refs=review_refs,
        profile_context_input_refs=("PROFILE-APPLICABILITY-RESOLVED-NONE",),
        policy_context_input_refs=("POLICY-CONTEXT-PUBLISH",),
        no_competing_change_set=True,
    )
    operations = []
    if resolution_decision.resolution_type == "create_new_identity":
        operations.append(
            PublicationOperation(
                operation_type="create_identity",
                subject_refs=resolution_decision.target_canonical_refs,
                target_version_refs=(),
                atomic_effect_ref=(
                    lifecycle_candidate.lifecycle_candidate_revision_ref
                ),
            )
        )
    operations.append(
        PublicationOperation(
            operation_type="publish_new_version",
            subject_refs=("KO-GT-ME-ESPORTS-PILOT",),
            target_version_refs=("KO-GT-ME-ESPORTS-PILOT@0.2",),
            atomic_effect_ref=lifecycle_candidate.lifecycle_candidate_revision_ref,
        )
    )
    change_set_evaluation = PublicationChangeSetBuilder().build(
        PublicationChangeSetBuildRequest(
            candidate_revision=lifecycle_candidate,
            resolution_decision=resolution_decision,
            knowledge_version_projection=version_projection,
            operations=tuple(operations),
            expected_prior_states=(expected_prior,),
            candidate_review_record_refs=review_refs,
            conformance_report_refs=conformance_refs,
            publication_finalization_plan_refs=(finalization_plan_ref,),
            idempotency_key=f"{case_ref}:publication-change-set",
            rollback_or_compensation_plan_ref=(
                f"COMP-{case_ref}-STAGING-ABORT-OR-FULL-COMPENSATION"
            ),
            created_by="hr005-synthetic-scenario-runner",
            created_at="2026-08-15T10:00:00+02:00",
            hash_rule_binding=_D6_HASH_RULE,
        )
    )
    if change_set_evaluation.change_set is None:
        raise RuntimeError(
            f"{case_ref}: D6 Change Set failed: {change_set_evaluation.reason_code}"
        )
    change_set = change_set_evaluation.change_set

    semantic, assembly_plan, representation = _d6_assembly_inputs(
        case_ref,
        candidate,
        config,
    )
    unit_path = output_root / "publication-units" / case_ref / "unit.md"
    manifest = PublicationUnitAssembler().assemble(
        semantic,
        plan=assembly_plan,
        representation=representation,
        output_path=unit_path,
        publication_finalization_plan_ref=finalization_plan_ref,
        review_record_refs=review_refs,
        policy_decision_refs=(planned_policy_decision_ref,),
        cross_view_report_ref=conformance_refs[1],
    )
    document = load_publication_unit(unit_path)
    unit_binding = PublicationUnitBinding.create(
        manifest=manifest,
        markdown_body=document.markdown_body,
        hash_rule_binding=_D6_HASH_RULE,
    )
    package_ref = local_ref(
        "PPK",
        {
            "candidate_revision_ref": (
                lifecycle_candidate.lifecycle_candidate_revision_ref
            ),
            "resolution_decision_ref": resolution_decision.resolution_decision_ref,
            "change_set_version_ref": change_set.change_set_version_ref,
        },
    )
    finalization_plan = PublicationFinalizationPlan.create(
        publication_finalization_plan_ref=finalization_plan_ref,
        publication_unit=unit_binding,
        publication_change_set_ref=change_set.publication_change_set_ref,
        publication_package_ref=package_ref,
        canonical_path=(
            f"Knowledge/Test-Isolated/HR-005/{case_ref}/KO-GT-ME-ESPORTS-PILOT@0.2.md"
        ),
        maintenance_context_ref=f"synthetic-test-target:{case_ref}",
        publisher_ref="SYNTHETIC-HR005-PUBLISHER",
        executor_ref="cpknowledge.test-isolated-publication-executor@0.1",
        publication_authority_ref="synthetic_test_publication_authority",
        review_record_refs=review_refs,
        policy_decision_refs=(planned_policy_decision_ref,),
        planned_publication_record_ref=f"PREC-{case_ref}-PLANNED",
        predecessor_publication_ref=None,
        finalization_method_ref="test-isolated-snapshot-pointer@0.1",
        created_by="hr005-synthetic-scenario-runner",
        created_at="2026-08-15T10:01:00+02:00",
        hash_rule_binding=_D6_HASH_RULE,
    )
    package_evaluation = PublicationPackageBuilder().build(
        PublicationPackageBuildRequest(
            candidate_revision=lifecycle_candidate,
            resolution_decision=resolution_decision,
            change_set=change_set,
            publication_unit_binding=unit_binding,
            publication_finalization_plan=finalization_plan,
            candidate_review_record_refs=review_refs,
            conformance_report_refs=conformance_refs,
            profile_refs=(),
            policy_anchor_refs=("PA-SYNTHETIC-PUBLICATION",),
            package_version="0.1",
            created_by="hr005-synthetic-scenario-runner",
            created_at="2026-08-15T10:01:00+02:00",
            hash_rule_binding=_D6_HASH_RULE,
        )
    )
    if package_evaluation.package is None:
        raise RuntimeError(
            f"{case_ref}: D6 Package failed: {package_evaluation.reason_code}"
        )
    package = package_evaluation.package

    publication_requirement, publication_request = PublicationReviewFactory().create(
        package,
        required_reviewer_authority="project_owner_default_human",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#10.4",),
        profile_refs=(),
    )
    publication_review_record = ReviewRecord.create(
        review_request_ref=publication_request.review_request_ref,
        review_type=publication_request.review_type,
        subject_ref=publication_request.subject_ref,
        subject_version=publication_request.subject_version,
        review_scope=publication_request.review_scope,
        reviewer_ref="SYNTHETIC-PROJECT-OWNER-PUBLICATION-REVIEWER",
        reviewer_authority=publication_request.required_reviewer_authority,
        result="passed",
        findings=("synthetic_test_publication_review_fixture",),
        conditions=(),
        evidence_reviewed_refs=publication_request.evidence_and_context_refs,
        rule_basis_refs=publication_request.rule_basis_refs,
        profile_refs=publication_request.profile_refs,
        reviewed_at="2026-08-15T10:02:00+02:00",
        synthetic_test_fixture=True,
    )
    publication_review_validation = PublicationReviewValidator().validate(
        publication_review_record,
        publication_request,
        publication_requirement,
        package,
        lifecycle_candidate,
    )
    if publication_review_validation.disposition != "accepted":
        raise RuntimeError(
            f"{case_ref}: D6 publication_review failed: "
            f"{publication_review_validation.reason_code}"
        )

    policy_subject = PolicySubject(
        "knowledge_object",
        unit_binding.knowledge_object_id,
        unit_binding.knowledge_object_version,
        "Semantic Core",
    )
    policy_evaluation = PolicyEvaluationInput(
        policy_evaluation_ref=f"PEVAL-{case_ref}-PUBLISH",
        actor_or_consumer_ref="SYNTHETIC-HR005-PUBLISHER",
        purpose="controlled_knowledge_publication",
        requested_operation="publish",
        subject_refs=(policy_subject,),
        policy_config_ref="SYNTHETIC-PUBLISH-POLICY@0.1",
        processing_zone="synthetic_test_staging",
        profile_refs=(),
        profile_applicability=ProfileApplicability(resolution_status="resolved"),
        policy_anchor_ids=package.policy_anchor_refs,
        requested_at="2026-08-15T10:03:00+02:00",
        context_valid_at="2026-08-15T10:03:00+02:00",
        requested_action="publish",
        actor_roles=("synthetic_test_publisher",),
        requested_data_operations=PUBLICATION_DATA_OPERATIONS,
        requested_effect_scope="publication_package_version",
        candidate_revision_ref=package.candidate_revision_ref,
        resolution_decision_ref=package.resolution_decision_ref,
        publication_change_set_ref=change_set.publication_change_set_ref,
        publication_change_set_version_ref=change_set.change_set_version_ref,
        publication_change_set_hash=change_set.change_set_hash.value,
        publication_package_version_ref=package.package_version_ref,
        publication_package_hash=package.package_hash.value,
        publication_finalization_plan_ref=(
            finalization_plan.publication_finalization_plan_ref
        ),
        publication_unit_refs=(unit_binding.publication_unit_ref,),
        knowledge_content_hash_refs=(unit_binding.content_hash.value,),
        prepublication_representation_hash_refs=(
            unit_binding.prepublication_representation_hash.value,
        ),
        target_refs=(
            finalization_plan.canonical_path,
            finalization_plan.maintenance_context_ref,
        ),
        publication_authority_ref=finalization_plan.publication_authority_ref,
        publication_review_record_ref=(publication_review_record.review_record_ref),
        review_record_refs=(*review_refs, publication_review_record.review_record_ref),
        conformance_report_refs=conformance_refs,
        risk_input_refs=(f"RISK-{case_ref}-SYNTHETIC",),
        quality_input_refs=(f"QUALITY-{case_ref}-SYNTHETIC",),
        agent_authority_context="synthetic_test_no_standing_authority",
    )
    policy_configuration = PolicyConfiguration(
        policy_ref="SYNTHETIC-PUBLISH-POLICY",
        version="0.1",
        status="active",
        rules=(
            PolicyRule(
                policy_rule_ref=f"RULE-{case_ref}-PUBLISH",
                actor_or_consumer_ref=policy_evaluation.actor_or_consumer_ref,
                purpose=policy_evaluation.purpose,
                requested_operation="publish",
                requested_action="publish",
                requested_data_operations=PUBLICATION_DATA_OPERATIONS,
                subject_ref=policy_subject,
                required_policy_anchor_ids=package.policy_anchor_refs,
                effect="permit",
                reason="synthetic_test_publish_permit",
                authorized_scope="publication_package_version",
            ),
        ),
        decision_authority_ref="synthetic_test_policy_decision_authority",
        valid_from="2026-08-15T09:00:00+02:00",
        valid_until="2026-08-15T12:00:00+02:00",
        synthetic_test_fixture=True,
    )
    policy_decision = PolicyEvaluator().evaluate(
        policy_evaluation,
        policy_configuration,
    )
    g5 = G5PolicyGate().evaluate(
        G5PolicyGateRequest(
            package=package,
            policy_evaluation=policy_evaluation,
            policy_decision=policy_decision,
            publication_review=publication_review_validation,
            context_valid_at="2026-08-15T10:04:00+02:00",
        )
    )
    if g5.disposition != "passed":
        raise RuntimeError(f"{case_ref}: synthetic D6 G5 failed: {g5.reason_code}")
    publication_authority = PublicationAuthorityEvidence(
        authority_ref="synthetic_test_publication_authority",
        authority_kind="publication_authority",
        authorized_action="publish",
        authorized_package_version_ref=package.package_version_ref,
        authorized_subject_refs=(unit_binding.publication_unit_ref,),
        authority_context_ref="synthetic_not_live_authority",
        valid_at="2026-08-15T10:04:00+02:00",
        explicitly_granted=True,
        synthetic_test_fixture=True,
    )
    g6 = G6PublicationReadinessGate().evaluate(
        G6PublicationReadinessRequest(
            package=package,
            candidate_revision=lifecycle_candidate,
            resolution_decision=resolution_decision,
            candidate_reviews_satisfied=True,
            publication_review=publication_review_validation,
            g5_result=g5,
            publication_authority=publication_authority,
            observed_prior_states=package.expected_prior_states,
            recovery_consequences_determined=True,
        )
    )
    if g6.disposition != "ready":
        raise RuntimeError(f"{case_ref}: synthetic D6 G6 failed: {g6.reason_code}")

    d7_request = PublicationRequestFactory().create(
        package=package,
        g6_result=g6,
        policy_decision_ref=policy_decision.policy_decision_ref,
        publication_review_record_ref=publication_review_record.review_record_ref,
        idempotency_key=f"{case_ref}:test-isolated-publication",
        requested_at="2026-08-15T10:05:00+02:00",
    )
    test_target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states,
        target_ref=finalization_plan.maintenance_context_ref,
    )
    executor = PublicationExecutor()
    d7 = executor.execute(
        request=d7_request,
        package=package,
        g6_result=g6,
        target=test_target,
        executed_at="2026-08-15T10:06:00+02:00",
    )
    if d7.disposition != "published" or d7.record is None:
        raise RuntimeError(f"{case_ref}: synthetic D7 failed: {d7.reason_code}")
    replay = executor.execute(
        request=d7_request,
        package=package,
        g6_result=g6,
        target=test_target,
        executed_at="2026-08-15T10:07:00+02:00",
    )
    if replay.disposition != "idempotent_replay" or replay.record != d7.record:
        raise RuntimeError(f"{case_ref}: synthetic D7 idempotency replay failed")
    final_target_state = test_target.read(finalization_plan.canonical_path)
    if final_target_state is None:
        raise RuntimeError(f"{case_ref}: synthetic D7 target reread missing")
    rebuild_conformance = _run_per_candidate_publication_bound_rebuild_conformance(
        case_ref,
        final_target_state.manifest,
        final_target_state.markdown_body,
        d7.record,
    )

    live_evaluation = replace(policy_evaluation, policy_config_ref="")
    live_decision = PolicyEvaluator().evaluate(live_evaluation, None)
    live_g5 = G5PolicyGate().evaluate(
        G5PolicyGateRequest(
            package=package,
            policy_evaluation=live_evaluation,
            policy_decision=live_decision,
            publication_review=publication_review_validation,
            context_valid_at="2026-08-15T10:04:00+02:00",
        )
    )
    live_g6 = G6PublicationReadinessGate().evaluate(
        G6PublicationReadinessRequest(
            package=package,
            candidate_revision=lifecycle_candidate,
            resolution_decision=resolution_decision,
            candidate_reviews_satisfied=True,
            publication_review=publication_review_validation,
            g5_result=live_g5,
            publication_authority=None,
            observed_prior_states=package.expected_prior_states,
            recovery_consequences_determined=True,
        )
    )

    publication_unit_payload = unit_binding.to_dict()
    publication_unit_payload.update(
        {
            "assembled_by": "PublicationUnitAssembler",
            "output_path": str(unit_path),
            "cp_wiki_write_performed": False,
        }
    )
    publication_review_payload = publication_review_record.to_dict()
    publication_review_payload.update(
        {
            "requirement_ref": publication_requirement.review_requirement_ref,
            "validation_reason_code": publication_review_validation.reason_code,
            "real_human_review_claimed": False,
        }
    )
    return {
        "publication_change_set": change_set.to_dict(),
        "publication_unit": publication_unit_payload,
        "publication_package": package.to_dict(),
        "publication_finalization_plan": finalization_plan.to_dict(),
        "publication_review": publication_review_payload,
        "policy_evaluation": {
            **policy_evaluation.context_payload(),
            "context_fingerprint": policy_evaluation.context_fingerprint,
        },
        "technical_test_policy_decision": policy_decision.to_dict(),
        "g5": asdict(g5),
        "g6": asdict(g6),
        "prior_version_superseded": False,
        "publication_request": d7_request.to_dict(),
        "publication_execution": {
            "status": d7.disposition,
            "reason_code": d7.reason_code,
            "final_state_verified": d7.final_state_verified,
            "change_set_applied": d7.change_set_applied,
            "candidate_closed_after_publication": (
                d7.candidate_closed_after_publication
            ),
            "changed_fields": list(d7.changed_fields),
            "idempotency_replay_disposition": replay.disposition,
            "target_commit_count": test_target.commit_count,
            "test_isolated": True,
        },
        "publication_record": d7.record.to_dict(),
        "final_publication_unit": {
            "manifest": final_target_state.manifest,
            "markdown_body": final_target_state.markdown_body,
        },
        "actual_publication": True,
        "test_isolated_publication": True,
        "canonical_write": False,
        "cp_wiki_write": False,
        "publication_bound_rebuild_conformance": rebuild_conformance,
        "live_project_gate_case": {
            "applicable_active_knowledge_publication_policy_proven": False,
            "publication_authority_proven": False,
            "g5": asdict(live_g5),
            "g6": asdict(live_g6),
            "g7": "not_reached",
            "publication": False,
            "publication_record": None,
            "cp_wiki_write": False,
        },
    }


def _run_d5_case(
    case_ref: str,
    candidate: ChangeCandidateRevision,
    config: _ResolutionCaseConfig,
    output_root: Path,
) -> dict[str, Any]:
    lifecycle_candidate = LifecycleCandidateRegistrar().register(
        candidate,
        registered_by="hr005-synthetic-scenario-runner",
        registered_at="2026-08-14T00:00:00+02:00",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#3-4",),
        idempotency_key=f"{case_ref}:lifecycle-registration",
    )
    prior_snapshot = _scenario_identity_snapshot(
        candidate,
        identity_ref=config.prior_identity_ref,
        dimensions=config.prior_dimensions,
    )
    proposed_snapshot = _scenario_identity_snapshot(
        candidate,
        identity_ref=(
            config.target_canonical_ref
            if config.resolution_type == "revise_existing_identity"
            else None
        ),
        dimensions=config.proposed_dimensions,
    )
    if proposed_snapshot is None:
        raise RuntimeError(f"{case_ref}: proposed identity snapshot missing")
    assessment = SameObjectEvaluator().evaluate(
        SameObjectAssessmentRequest(
            candidate_revision=lifecycle_candidate,
            prior_snapshot=prior_snapshot,
            proposed_snapshot=proposed_snapshot,
            existing_canonical_refs=(
                (config.prior_identity_ref,)
                if config.prior_identity_ref is not None
                else ()
            ),
            prior_identity_evidence_refs=candidate.evidence_refs,
            assessed_dimensions=tuple(
                sorted(
                    set(config.proposed_dimensions) | set(config.prior_dimensions or {})
                )
            ),
            material_delta_dimensions=config.material_delta_dimensions,
            rationale=(
                f"{config.resolution_ref}: scenario-local projection of active "
                "Core Same-Object rules"
            ),
            rule_basis_refs=("CPKS-SPEC-KM@0.20#9",),
        )
    )
    resolution = ResolutionEngine().evaluate(
        ResolutionRequest(
            candidate_revision=lifecycle_candidate,
            same_object_assessment=assessment,
            plan=ResolutionPlan(
                resolution_type=config.resolution_type,
                target_canonical_refs=(config.target_canonical_ref,),
                planned_target_versions=(
                    f"{config.target_canonical_ref}@scenario-planned-state",
                ),
                identity_rationale=(
                    f"{config.resolution_ref}: explicit scenario-local canonical "
                    "mapping after Core Same-Object assessment"
                ),
            ),
            authority=HR005_RESOLUTION_AUTHORITY,
        )
    )
    if resolution.disposition != "resolved" or resolution.decision is None:
        raise RuntimeError(
            f"{case_ref}: D5 resolution failed: "
            f"{resolution.disposition}/{resolution.reason_code}"
        )
    version_projection = KnowledgeVersionProjector().evaluate(
        KnowledgeVersionProjectionRequest(
            resolution_decision=resolution.decision,
            stable_knowledge_object_ref="KO-GT-ME-ESPORTS-PILOT",
            prior_knowledge_object_version_ref="KO-GT-ME-ESPORTS-PILOT@0.1",
            prior_publication_state="unpublished",
            planned_target_knowledge_object_version_ref=("KO-GT-ME-ESPORTS-PILOT@0.2"),
            material_change=True,
            same_knowledge_object_identity=True,
        )
    )
    if version_projection.projection is None:
        raise RuntimeError(
            f"{case_ref}: D5 knowledge-version projection failed: "
            f"{version_projection.reason_code}"
        )

    routing = ReviewRequirementRouter(HR005_REVIEW_POLICY).route(
        ReviewRoutingContext(
            candidate_revision=lifecycle_candidate,
            semantic_change_operation=candidate.semantic_change_operation,
            same_object_relevant=config.same_object_relevant_for_review,
            identity_ambiguous=False,
            evidence_basis_only=config.evidence_basis_only,
            privacy_or_security_triggered=False,
            evidence_and_context_refs=(
                *candidate.evidence_refs,
                assessment.same_object_assessment_ref,
                resolution.decision.resolution_decision_ref,
            ),
            known_questions_gaps_conflicts=candidate.known_conflicts,
            profile_refs=(),
            rule_basis_refs=(
                "CPKS-SPEC-KPR@0.3#10-12",
                "GT-S2K-ENRICHMENT-01@0.8:review-routing",
            ),
            authority_by_review_type=HR005_REVIEW_AUTHORITIES,
        )
    )
    if routing.requirement_set is None:
        raise RuntimeError(
            f"{case_ref}: D5 review routing failed: {routing.reason_code}"
        )
    review_requests = ReviewRequestFactory().create_requests(
        routing.requirement_set,
        evidence_and_context_refs=(
            *candidate.evidence_refs,
            assessment.same_object_assessment_ref,
            resolution.decision.resolution_decision_ref,
        ),
        known_questions_gaps_conflicts=candidate.known_conflicts,
    )
    review_records = tuple(
        _synthetic_review_fixture(request) for request in review_requests
    )
    validator = ReviewRecordValidator()
    for request, record in zip(review_requests, review_records, strict=True):
        validation = validator.validate(record, request, lifecycle_candidate)
        if validation.disposition != "accepted":
            raise RuntimeError(
                f"{case_ref}: D5 synthetic review fixture invalid: "
                f"{validation.reason_code}"
            )
    readiness = ReviewOrchestrator().evaluate_readiness(
        routing.requirement_set,
        review_records,
    )
    if not readiness.ready:
        raise RuntimeError(
            f"{case_ref}: D5 candidate review readiness failed: {readiness.reason_code}"
        )
    d6 = _run_d6_case(
        case_ref,
        candidate,
        config,
        lifecycle_candidate,
        resolution.decision,
        version_projection.projection,
        review_records,
        output_root,
    )

    return {
        "case_ref": case_ref,
        "resolution_ref": config.resolution_ref,
        "lifecycle_candidate": lifecycle_candidate.to_dict(),
        "same_object_assessment": assessment.to_dict(),
        "resolution": resolution.decision.to_dict(),
        "planned_knowledge_version": version_projection.projection.to_dict(),
        "review_requirement_set": routing.requirement_set.to_dict(),
        "review_requests": [request.to_dict() for request in review_requests],
        "review_records": [record.to_dict() for record in review_records],
        "candidate_review_readiness": readiness.to_dict(),
        "review_evidence_class": "synthetic_test_review_fixture",
        "real_human_review_claimed": False,
        "d6": d6,
    }


def _run_positive_d5(
    candidates: dict[str, ChangeCandidateRevision],
    output_root: Path,
) -> dict[str, dict[str, Any]]:
    return {
        golden_ref: _run_d5_case(
            golden_ref,
            candidates[golden_ref],
            _GOLDEN_RESOLUTION_CONFIG[golden_ref],
            output_root,
        )
        for golden_ref in sorted(_GOLDEN_RESOLUTION_CONFIG)
    }


def _run_special_d5(
    candidates: dict[str, ChangeCandidateRevision],
    output_root: Path,
) -> dict[str, dict[str, Any]]:
    return {
        case_ref: _run_d5_case(
            case_ref,
            candidates[case_ref],
            _SPECIAL_RESOLUTION_CONFIG[case_ref],
            output_root,
        )
        for case_ref in sorted(_SPECIAL_RESOLUTION_CONFIG)
    }


def _run_source_backed_extension(
    output_root: Path,
    human_review_output: Path | None = None,
) -> dict[str, Any]:
    adapter = LocalHtmlAdapter()
    records = tuple(adapter.capture_many(POST_R5_SOURCE_BINDINGS))
    evidence_addresses = tuple(
        address
        for record in records
        for address in adapter.passage_evidence_addresses(record)
    )
    records_by_ref = {record.record_ref: record for record in records}
    for address in evidence_addresses:
        if not adapter.resolve(records_by_ref[address.record_ref], address):
            raise RuntimeError(
                "Source-backed passage Evidence is not reproducible: "
                f"{address.evidence_address_ref}"
            )

    artifact_root = output_root / "source-backed"
    snapshot_root = artifact_root / "source/snapshots"
    record_root = artifact_root / "source/records"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    record_root.mkdir(parents=True, exist_ok=True)
    for record in records:
        (snapshot_root / f"{record.snapshot_ref}.html").write_text(
            record.raw_html,
            encoding="utf-8",
        )
        (record_root / f"{record.record_ref}.json").write_text(
            json.dumps(
                {
                    "source_key": record.source_key,
                    "source_ref": record.source_ref,
                    "snapshot_ref": record.snapshot_ref,
                    "record_ref": record.record_ref,
                    "source_time": record.source_time,
                    "captured_at": record.captured_at,
                    "media_type": record.media_type,
                    "title": record.title,
                    "creator_label": record.creator_label,
                    "recipient_labels": list(record.recipient_labels),
                    "raw_sha256": record.raw_sha256,
                    "normalized_text": record.normalized_text,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    evidence_path = artifact_root / "source/evidence_addresses.json"
    evidence_path.write_text(
        json.dumps(
            [
                {
                    "evidence_address_ref": address.evidence_address_ref,
                    "source_key": address.source_key,
                    "source_ref": address.source_ref,
                    "snapshot_ref": address.snapshot_ref,
                    "record_ref": address.record_ref,
                    "selector": address.selector,
                    "content_hash": address.content_hash,
                    "text": address.text,
                    "restricted": address.restricted,
                }
                for address in evidence_addresses
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_source_backed_post_r5(
        source_records=records,
        evidence_addresses=evidence_addresses,
        as_of="2026-01-27T09:31:00+01:00",
        requested_owner_ref="OWNER-SYNTHETIC-VERA-ANDERS",
        requested_owner_label="Vera Anders",
    )
    result["run_artifacts"] = {
        "root": "source-backed",
        "snapshot_count": len(records),
        "source_record_count": len(records),
        "evidence_address_count": len(evidence_addresses),
        "evidence_addresses_path": "source-backed/source/evidence_addresses.json",
    }

    evidence_by_source: dict[str, list[Any]] = {}
    for address in evidence_addresses:
        evidence_by_source.setdefault(address.source_key, []).append(address)
    review_terms = (
        "pilot",
        "programme",
        "program",
        "technical",
        "capacity",
        "competition",
        "classroom",
        "approved",
        "evaluation",
        "owner",
        "reason",
    )
    excerpts = []
    for record in records:
        candidates = evidence_by_source[record.source_key]
        ranked = sorted(
            enumerate(candidates),
            key=lambda item: (
                -sum(term in item[1].text.casefold() for term in review_terms),
                item[0],
            ),
        )
        selected = [item[1] for item in ranked[:3]]
        excerpts.append(
            {
                "source_key": record.source_key,
                "title": record.title,
                "source_time": record.source_time,
                "excerpts": [
                    {
                        "evidence_address_ref": address.evidence_address_ref,
                        "text": address.text,
                    }
                    for address in selected
                ],
            }
        )
    review_projection = {
        "artifact_role": "generated_noncanonical_human_review_projection",
        "synthetic": True,
        "canonical": False,
        "expected_evaluation_embedded": False,
        "source_excerpts": excerpts,
        "system_representation": {
            "knowledge": result["knowledge"],
            "knowledge_frontier": result["knowledge_frontier"],
            "human_enrichment_opportunity": result["human_enrichment"]["opportunity"],
            "human_enrichment_request": result["human_enrichment"]["request"],
            "kpr_disposition": result["human_enrichment"]["kpr_disposition"],
            "human_response_present": False,
        },
        "owner_review_questions": [
            (
                "Is the external actor now represented appropriately as Program "
                "Originator/Initiator and Delivery Provider?"
            ),
            (
                "If separately policy-conformant Human Evidence becomes available, "
                "is business interest retained as context without a global "
                "credibility judgment?"
            ),
            (
                "Are technical operability and institutional technical "
                "acceptability kept meaningfully separate?"
            ),
            (
                "Are internal responsibility and organisational scheduling "
                "understandable as separate possible factors?"
            ),
            ("Does every possible factor remain explicitly non-causal?"),
            (
                "Is the Human Enrichment Request correctly P1, retrospective, "
                "non-blocking, and queued?"
            ),
            "Does the actual non-continuation reason remain unresolved?",
        ],
    }
    review_path = human_review_output or (
        artifact_root / "human-review/source-backed-post-r5-review.json"
    )
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        json.dumps(review_projection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        projected_review_path = str(review_path.relative_to(REPO_ROOT))
    except ValueError:
        projected_review_path = str(review_path)
    result["human_review_projection"] = {
        "path": projected_review_path,
        "artifact_role": review_projection["artifact_role"],
        "expected_evaluation_embedded": False,
    }
    return result


def run(
    output_root: Path,
    human_review_output: Path | None = None,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    finding_records = _positive_findings()
    findings: list[dict[str, Any]] = []
    for golden_ref, finding in finding_records:
        payload = finding.to_dict()
        payload["golden_delta_ref"] = golden_ref
        findings.append(payload)
    change_candidates, candidate_objects = _positive_candidates(finding_records)
    special_cases, special_candidate_objects = _special_cases()
    positive_d5 = _run_positive_d5(candidate_objects, output_root)
    special_d5 = _run_special_d5(special_candidate_objects, output_root)
    cumulative_experience_acceptance = _run_cumulative_experience_acceptance(
        positive_d5
    )
    post_r5_hardening = run_post_r5_hardening(
        semantic_state=json.loads(POST_R5_SEMANTIC_CASES.read_text(encoding="utf-8"))[
            "cases"
        ],
        human_enrichment_state=json.loads(
            POST_R5_HUMAN_ENRICHMENT.read_text(encoding="utf-8")
        ),
    )
    source_backed_post_r5 = _run_source_backed_extension(
        output_root,
        human_review_output,
    )

    for case_ref, d5_payload in special_d5.items():
        special_cases[case_ref]["d5"] = {
            key: value for key, value in d5_payload.items() if key != "d6"
        }
        special_cases[case_ref]["d6"] = d5_payload["d6"]
    special_cases["D2-NOMAT-01"]["d5"] = {
        "resolution": None,
        "planned_knowledge_version": None,
        "review_requirement_set": None,
        "reason_code": "no_d4_candidate_no_d5_resolution_required",
    }
    special_cases["D2-NOMAT-01"]["d6"] = {
        "publication_change_set": None,
        "publication_unit": None,
        "publication_package": None,
        "reason_code": "no_d4_candidate_no_d6_publication_required",
    }
    special_cases["D2-NOMAT-01"]["d7"] = {
        "publication_request": None,
        "publication_record": None,
        "publication": False,
        "reason_code": "no_material_candidate_no_publication_execution_required",
    }
    special_cases["D2-NOMAT-01"]["d8_d9"] = {
        "publication_bound_rebuild_conformance": None,
        "reason_code": "no_success_publication_record_no_rebuild_conformance",
    }

    def _project_case_records(field: str) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for golden_ref, case in sorted(positive_d5.items()):
            payload = dict(case[field])
            payload["golden_delta_ref"] = golden_ref
            payload["golden_resolution_ref"] = case["resolution_ref"]
            projected.append(payload)
        return projected

    def _project_case_lists(field: str) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for golden_ref, case in sorted(positive_d5.items()):
            for item in case[field]:
                payload = dict(item)
                payload["golden_delta_ref"] = golden_ref
                payload["golden_resolution_ref"] = case["resolution_ref"]
                projected.append(payload)
        return projected

    def _project_d6_records(field: str) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for golden_ref, case in sorted(positive_d5.items()):
            payload = dict(case["d6"][field])
            payload["golden_delta_ref"] = golden_ref
            payload["golden_resolution_ref"] = case["resolution_ref"]
            projected.append(payload)
        return projected

    resolution_refs = [
        case["resolution"]["resolution_decision_ref"]
        for _, case in sorted(positive_d5.items())
    ]
    planned_knowledge_version = {
        "stable_knowledge_object_ref": "KO-GT-ME-ESPORTS-PILOT",
        "prior_knowledge_object_version_ref": "KO-GT-ME-ESPORTS-PILOT@0.1",
        "prior_publication_state": "unpublished",
        "planned_target_knowledge_object_version_ref": ("KO-GT-ME-ESPORTS-PILOT@0.2"),
        "same_knowledge_object_identity": True,
        "projection_state": "planned_not_published",
        "prior_version_superseded": False,
        "source_resolution_decision_refs": resolution_refs,
    }

    result = {
        "result_format_version": "0.1",
        "scenario_ref": "GT-S2K-ENRICHMENT-01",
        "scenario_version": "0.8",
        "outcome": "pass",
        "implemented_through": "D9",
        "findings": findings,
        "change_candidates": change_candidates,
        "lifecycle_candidates": _project_case_records("lifecycle_candidate"),
        "same_object_assessments": _project_case_records("same_object_assessment"),
        "resolutions": _project_case_records("resolution"),
        "planned_knowledge_version": planned_knowledge_version,
        "review_requirement_sets": _project_case_records("review_requirement_set"),
        "review_requests": _project_case_lists("review_requests"),
        "reviews": _project_case_lists("review_records"),
        "candidate_review_readiness": _project_case_records(
            "candidate_review_readiness"
        ),
        "review_orchestration": {
            "scope": "candidate_level_only",
            "real_human_review_claimed": False,
            "record_evidence_class": "synthetic_test_review_fixture",
        },
        "publication_change_sets": _project_d6_records("publication_change_set"),
        "publication_units": _project_d6_records("publication_unit"),
        "publication_packages": _project_d6_records("publication_package"),
        "publication_finalization_plans": _project_d6_records(
            "publication_finalization_plan"
        ),
        "publication_reviews": _project_d6_records("publication_review"),
        "policy_evaluations": _project_d6_records("policy_evaluation"),
        "technical_test_policy_decisions": _project_d6_records(
            "technical_test_policy_decision"
        ),
        "g5_results": _project_d6_records("g5"),
        "g6_results": _project_d6_records("g6"),
        "publication_requests": _project_d6_records("publication_request"),
        "publication_executions": _project_d6_records("publication_execution"),
        "publication_records": _project_d6_records("publication_record"),
        "final_publication_units": _project_d6_records("final_publication_unit"),
        "per_candidate_publication_bound_rebuild_conformance": (
            _project_d6_records("publication_bound_rebuild_conformance")
        ),
        "cumulative_experience_acceptance": cumulative_experience_acceptance,
        "post_r5_hardening": post_r5_hardening,
        "source_backed_post_r5": source_backed_post_r5,
        "special_cases": special_cases,
        "live_project_gate_case": positive_d5["KF-D01"]["d6"]["live_project_gate_case"],
        "publication_policy_negative_cases": [
            {
                "case_ref": "PG-N01",
                "status": "passed",
                "reason_code": "policy_evaluation_not_policy_decision",
            },
            {
                "case_ref": "PG-N02",
                "status": "passed",
                "reason_code": "quality_gate_not_publication_permit",
            },
            {
                "case_ref": "PG-N03",
                "status": "passed",
                "reason_code": "candidate_review_not_publication_permit",
            },
            {
                "case_ref": "PG-N04",
                "status": "passed",
                "reason_code": "publication_review_missing",
            },
            {
                "case_ref": "PG-N05",
                "status": "passed",
                "reason_code": "policy_decision_context_stale",
            },
            {
                "case_ref": "PG-N06",
                "status": "passed",
                "reason_code": "policy_decision_context_stale",
            },
            {
                "case_ref": "PG-N07",
                "status": "passed",
                "reason_code": "policy_applicable_profile_missing",
            },
            {
                "case_ref": "PG-N08",
                "status": "passed",
                "reason_code": "policy_conditions_not_satisfied",
            },
            {
                "case_ref": "PG-N09",
                "status": "passed",
                "reason_code": "review_escalate_deny_all_blocked",
            },
            {
                "case_ref": "PG-N10",
                "status": "passed",
                "reason_code": "policy_permit_not_publication_record",
            },
            {
                "case_ref": "PG-N11",
                "status": "passed",
                "reason_code": ("technical_write_capability_not_publication_authority"),
            },
            {
                "case_ref": "PG-N12",
                "status": "passed",
                "reason_code": "independent_candidates_cannot_share_change_set",
            },
            {
                "case_ref": "PG-N13",
                "status": "passed",
                "reason_code": "unpublished_predecessor_cannot_be_superseded",
            },
            {
                "case_ref": "PG-N14",
                "status": "passed",
                "reason_code": "requested_operation_unsupported",
            },
        ],
        "publication": {
            "status": "test_isolated_published",
            "actual_publication": True,
            "test_isolated": True,
            "canonical_write": False,
            "cp_wiki_write": False,
            "publication_record_count": len(positive_d5),
        },
        "publication_execution": {
            "status": "test_isolated_published",
            "all_final_states_verified": True,
            "all_replays_idempotent": True,
        },
        "per_candidate_publication_bound_rebuild_conformance_summary": {
            "status": "publication_bound_rebuild_conformance_verified",
            "publication_bound": True,
            "all_exact_publication_bindings_verified": True,
            "all_knowledge_content_hash_bindings_verified": True,
            "all_deterministic_rebuilds": True,
            "rich_experience_acceptance_claimed": False,
        },
        "next_frontier": {
            "capability": "CPKS-WP-003 validation and handover evidence",
            "reason_code": "implementation_frontier_reached_through_d9",
        },
    }
    (output_root / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--human-review-output", type=Path)
    args = parser.parse_args()
    try:
        run(
            args.output_root.resolve(),
            (
                args.human_review_output.resolve()
                if args.human_review_output is not None
                else None
            ),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
