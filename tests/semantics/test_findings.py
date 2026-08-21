from __future__ import annotations

from cp_knowledge_tools.semantics import (
    FindingInput,
    MaterialDeltaFindingEvaluator,
    SemanticState,
)


def _input(
    *,
    prior: SemanticState | None,
    observed: SemanticState,
    content_read: bool = True,
    authorized: bool = True,
    resolvable: bool = True,
    semantic_assertion: bool = True,
    prohibited: tuple[str, ...] = (),
    attempted: tuple[str, ...] = (),
    event_time: str | None = None,
) -> FindingInput:
    return FindingInput(
        task_ref="TEST-HR005-D3",
        source_result_ref="TEST-CONTINUATION-RESULT",
        source_ref="TEST-SOURCE",
        subject_refs=("TEST-SUBJECT",),
        prior_state_ref="TEST-PRIOR" if prior is not None else None,
        prior_state=prior,
        observed_state=observed,
        description="synthetic material-delta test",
        delta_class=("test",),
        evidence_content_read=content_read,
        content_read_authorized=authorized,
        evidence_resolvable=resolvable,
        semantic_assertion=semantic_assertion,
        prohibited_inferences=prohibited,
        attempted_inferences=attempted,
        event_time=event_time,
    )


def test_new_semantic_state_creates_non_canonical_finding() -> None:
    observed = SemanticState(
        semantic_payload={"predicate": "pilot_execution", "value": "occurred"},
        evidence_refs=("E-1",),
    )

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(prior=None, observed=observed)
    )

    assert result.disposition == "finding"
    assert result.material_delta_dimensions == ("semantic",)
    assert result.finding is not None
    assert result.finding.material_delta is True
    assert result.finding.non_canonical is True
    assert result.finding.evidence_refs == ("E-1",)


def test_same_proposition_with_new_independent_evidence_is_material() -> None:
    payload = {"predicate": "second_cycle", "value": "approved"}
    prior = SemanticState(
        semantic_payload=payload,
        evidence_refs=("CE-DOC-05",),
    )
    observed = SemanticState(
        semantic_payload=payload,
        evidence_refs=("CE-DOC-05", "CE-DOC-07"),
    )

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(prior=prior, observed=observed)
    )

    assert result.disposition == "finding"
    assert result.material_delta_dimensions == ("evidence",)
    assert result.finding is not None
    assert result.finding.semantic_observation == payload


def test_same_evidence_replay_has_no_material_delta() -> None:
    state = SemanticState(
        semantic_payload={"predicate": "second_cycle", "value": "approved"},
        evidence_refs=("CE-DOC-05",),
    )

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(prior=state, observed=state)
    )

    assert result.disposition == "no_finding"
    assert result.reason_code == "no_material_semantic_delta"
    assert result.finding is None


def test_content_not_read_produces_no_finding() -> None:
    observed = SemanticState({"predicate": "x", "value": 1}, ("E-1",))

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(prior=None, observed=observed, content_read=False)
    )

    assert result.reason_code == "evidence_content_not_read"
    assert result.finding is None


def test_content_not_authorized_produces_no_finding() -> None:
    observed = SemanticState({"predicate": "x", "value": 1}, ("E-1",))

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(prior=None, observed=observed, authorized=False)
    )

    assert result.reason_code == "evidence_content_not_authorized"
    assert result.finding is None


def test_unresolvable_evidence_produces_no_finding() -> None:
    observed = SemanticState({"predicate": "x", "value": 1}, ("E-1",))

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(prior=None, observed=observed, resolvable=False)
    )

    assert result.reason_code == "evidence_not_resolvable"
    assert result.finding is None


def test_run_state_without_semantic_assertion_produces_no_finding() -> None:
    observed = SemanticState(
        {"technical_run_state": "candidate_scope_exhausted"},
        ("E-1",),
    )

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(prior=None, observed=observed, semantic_assertion=False)
    )

    assert result.reason_code == "input_is_not_semantic_assertion"
    assert result.finding is None


def test_prohibited_inference_is_blocked() -> None:
    observed = SemanticState(
        {"predicate": "second_cycle", "value": "approved"},
        ("CE-DOC-05",),
    )

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(
            prior=None,
            observed=observed,
            prohibited=("performed",),
            attempted=("performed",),
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "finding_epistemic_or_scope_overreach"
    assert result.finding is None


def test_unknown_event_time_is_preserved_as_unknown() -> None:
    observed = SemanticState(
        {"event_type": "pilot_evaluation", "occurrence": "completed_after_cycle"},
        ("CE-DOC-04",),
    )

    result = MaterialDeltaFindingEvaluator().evaluate(
        _input(prior=None, observed=observed, event_time=None)
    )

    assert result.finding is not None
    assert result.finding.event_time is None
