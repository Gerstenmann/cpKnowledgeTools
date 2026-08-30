from dataclasses import replace

import pytest

from cp_knowledge_tools.reuse import (
    CandidateSource,
    CapabilityNeed,
    ResearchWorkspace,
    inspect_candidate,
    inspect_internal,
    integration_handover,
    research_gate,
    to_json,
    validate_assessment,
)
from cp_knowledge_tools.reuse.models import (
    COMPARISON_DIMENSIONS,
    CandidateComparison,
    DependencyAcceptanceState,
    ResearchQuestion,
    ReuseAssessment,
    ReuseDisposition,
    ReuseError,
)


def test_build_strategy_with_use_primitive(candidate, target, decisions):
    need = CapabilityNeed("Normalize values", ("normalize",))
    internal = inspect_internal(target, need)
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        facts = inspect_candidate(snapshot)
        store = decisions(snapshot)
        store.decision = replace(store.decision, disposition=ReuseDisposition.USE)
        assessment = ReuseAssessment(
            "assessment-test",
            need,
            ResearchQuestion("Which normalization primitive?"),
            research_gate(
                internal,
                internal_sufficient=False,
                rationale="No internal implementation.",
            ),
            internal,
            (facts,),
            (
                CandidateComparison(
                    snapshot.candidate_id,
                    tuple(
                        (dimension, "Explicit synthetic evaluation")
                        for dimension in COMPARISON_DIMENSIONS
                    ),
                    hard_constraint_findings=("No network at runtime",),
                ),
            ),
            (store.decision,),
            ReuseDisposition.BUILD,
            "Build orchestration; use primitive.",
            "No existing primitive",
            "Small new function possible",
            "One serious synthetic candidate; compare against BUILD and constraints.",
        )
        assert not validate_assessment(assessment)
        assert '"overall_strategy": "BUILD"' in to_json(assessment)
        assert validate_assessment(replace(assessment, decisions=()))
        assert validate_assessment(replace(assessment, comparison=()))
        handover = integration_handover(
            facts,
            store,
            assessment_id="assessment-test",
            integration_boundary="application normalize port",
            dependency_specification="fixture==1.0; lock resolved artifacts",
            verification_steps=("verify interpreter", "test wrapper behavior"),
        )
        assert handover.environment_preflight_required
        assert not (target / "pyproject.toml").exists()
        store.decision = replace(
            store.decision,
            disposition=ReuseDisposition.WRAP,
            acceptance=DependencyAcceptanceState.REVIEW_REQUIRED,
        )
        with pytest.raises(ReuseError):
            integration_handover(
                facts,
                store,
                assessment_id="assessment-test",
                integration_boundary="port",
                dependency_specification="fixture==1.0",
                verification_steps=("test",),
            )


def test_open_conditions_block_adoption(candidate, target, decisions):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        store.decision = replace(
            store.decision,
            disposition=ReuseDisposition.WRAP,
            acceptance=DependencyAcceptanceState.ACCEPTED_WITH_CONDITIONS,
            conditions=("Resolve material native-code dependency",),
            unresolved_conditions=("Resolve material native-code dependency",),
        )
        with pytest.raises(ReuseError):
            integration_handover(
                inspect_candidate(snapshot),
                store,
                assessment_id="assessment-test",
                integration_boundary="port",
                dependency_specification="fixture==1.0",
                verification_steps=("test",),
            )


def test_multiple_candidates_have_independent_dispositions(
    candidate, target, decisions, git_repo
):
    alternative = git_repo(
        "alternative", {"README.md": "Different design; no adoption"}
    )
    need = CapabilityNeed("Choose a normalization strategy", ("normalize",))
    internal = inspect_internal(target, need)
    with ResearchWorkspace(target) as work:
        first = inspect_candidate(work.acquire(CandidateSource.local(candidate)))
        second = inspect_candidate(work.acquire(CandidateSource.local(alternative)))
        first_decision = decisions(first.snapshot).decision
        second_decision = replace(
            decisions(second.snapshot).decision,
            disposition=ReuseDisposition.REJECT,
            acceptance=DependencyAcceptanceState.REJECTED,
            rationale="No functional implementation or license evidence",
        )
        comparisons = tuple(
            CandidateComparison(
                f.snapshot.candidate_id,
                tuple(
                    (d, "Explicit independent fixture comparison")
                    for d in COMPARISON_DIMENSIONS
                ),
            )
            for f in (first, second)
        )
        assessment = ReuseAssessment(
            "assessment-test",
            need,
            ResearchQuestion("Which option fits?"),
            research_gate(
                internal,
                internal_sufficient=False,
                rationale="Target has no implementation",
            ),
            internal,
            (first, second),
            comparisons,
            (first_decision, second_decision),
            ReuseDisposition.BUILD,
            "Build orchestration; ADAPT the selected primitive",
            "No internal alternative",
            "A new implementation is possible",
            "Two different synthetic approaches compared",
        )
        assert first.snapshot.candidate_id != second.snapshot.candidate_id
        assert not validate_assessment(assessment)
