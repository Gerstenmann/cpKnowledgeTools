"""Independent consumer-resolution checks using the real Policy evaluation path.

Policies here are exact, explicitly synthetic fixtures, not production authority
or a replacement evaluator. Authorization precedes Source integrity inspection.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path

import pytest

from cp_knowledge_tools.policy import (
    PolicyCondition,
    PolicyConfiguration,
    PolicyDecisionValidator,
    PolicyEvaluationInput,
    PolicyEvaluator,
    PolicyRule,
    PolicySubject,
    ProfileApplicability,
)
from cp_knowledge_tools.sources.adapters.local_html import LocalHtmlAdapter
from cp_knowledge_tools.sources.models import (
    CapturedSource,
    EvidenceAddress,
    ResolutionResult,
    Selector,
)

CONSUMER = "SYNTHETIC-SOURCE-READER"
PURPOSE = "synthetic_source_review"
POLICY = "SYNTHETIC-SOURCE-RESOLUTION-POLICY"
SOURCE_ANCHOR = "PA-SYNTHETIC-SNAPSHOT"
SCOPE = "synthetic_source_resolution"
NOW = "2026-08-31T10:00:00+02:00"
CONTENT_OPERATIONS = ("resolve_evidence", "read_content")
METADATA_OPERATIONS = ("resolve_evidence", "read_metadata")


def _capture(tmp_path: Path, html: str) -> CapturedSource:
    path = tmp_path / "resolution.html"
    path.write_text(html, encoding="utf-8")
    return LocalHtmlAdapter().capture(
        "synthetic-resolution-source",
        path,
        captured_at=NOW,
        policy_refs=(SOURCE_ANCHOR,),
    )


@pytest.fixture(params=("html", "pdf"))
def source(tmp_path: Path, request):
    if request.param == "pdf":
        from cp_knowledge_tools.sources.adapters.local_pdf import LocalPdfAdapter
        from tests.sources.pdf_fixture import digital_pdf

        adapter = LocalPdfAdapter()
        path = tmp_path / "resolution.pdf"
        path.write_bytes(digital_pdf(("Public fixture passage.",)))
        captured = adapter.capture(
            "synthetic-resolution-source",
            path,
            captured_at=NOW,
            policy_refs=(SOURCE_ANCHOR,),
        )
        address = adapter.evidence_address(captured, ["Public fixture passage."])
        return adapter, captured, address
    adapter = LocalHtmlAdapter()
    captured = _capture(tmp_path, "<article><p>Public fixture passage.</p></article>")
    address = adapter.evidence_address(captured, ["Public fixture passage."])
    return adapter, captured, address


def _subjects(address: EvidenceAddress) -> tuple[PolicySubject, ...]:
    return (
        PolicySubject(
            "evidence_address", address.evidence_address_ref, "1", "Source and Evidence"
        ),
        PolicySubject(
            "source_snapshot", address.snapshot_ref, "1", "Source and Evidence"
        ),
    )


def _evaluation(
    subjects: tuple[PolicySubject, ...],
    *,
    operations: tuple[str, ...] = CONTENT_OPERATIONS,
    anchors: tuple[str, ...] = (SOURCE_ANCHOR,),
) -> PolicyEvaluationInput:
    return PolicyEvaluationInput(
        policy_evaluation_ref="PEVAL-SYNTHETIC-SOURCE-RESOLUTION",
        actor_or_consumer_ref=CONSUMER,
        purpose=PURPOSE,
        requested_operation=None,
        requested_action="resolve_evidence",
        requested_data_operations=operations,
        requested_effect_scope=SCOPE,
        subject_refs=subjects,
        policy_config_ref=f"{POLICY}@1",
        processing_zone="local_synthetic_test",
        profile_refs=(),
        profile_applicability=ProfileApplicability(resolution_status="resolved"),
        policy_anchor_ids=anchors,
        requested_at=NOW,
        context_valid_at=NOW,
    )


def _configuration(
    subjects: tuple[PolicySubject, ...],
    *,
    operations: tuple[str, ...] = CONTENT_OPERATIONS,
    anchors: tuple[str, ...] = (SOURCE_ANCHOR,),
    effect: str = "permit",
    conditions: tuple[PolicyCondition, ...] = (),
) -> PolicyConfiguration:
    return PolicyConfiguration(
        policy_ref=POLICY,
        version="1",
        status="active",
        rules=tuple(
            PolicyRule(
                policy_rule_ref=f"SYNTHETIC-RESOLUTION-RULE-{index}",
                actor_or_consumer_ref=CONSUMER,
                purpose=PURPOSE,
                requested_operation=None,
                requested_action="resolve_evidence",
                requested_data_operations=operations,
                subject_ref=subject,
                required_policy_anchor_ids=anchors,
                effect=effect,
                reason=f"synthetic_exact_scope_{effect}",
                authorized_scope=SCOPE,
                conditions=conditions,
            )
            for index, subject in enumerate(subjects)
        ),
        decision_authority_ref="SYNTHETIC-TEST-POLICY-OWNER",
        valid_from="2026-08-31T09:00:00+02:00",
        valid_until="2026-08-31T11:00:00+02:00",
        synthetic_test_fixture=True,
    )


def _resolve(adapter, captured, address, evaluation, decision, **request):
    return adapter.resolve_content(
        captured,
        address,
        consumer_ref=request.get("consumer_ref", CONSUMER),
        purpose=request.get("purpose", PURPOSE),
        mode=request.get("mode", "content"),
        evaluation=evaluation,
        decision=decision,
    )


def _assert_private_denial(result: ResolutionResult) -> None:
    assert asdict(result) == {
        "status": "not_authorized",
        "content": None,
        "diagnostic_code": None,
    }


@pytest.mark.parametrize(
    ("mode", "operations", "expected_content"),
    [
        ("content", CONTENT_OPERATIONS, "Public fixture passage."),
        ("metadata_only", METADATA_OPERATIONS, None),
    ],
)
def test_exact_policy_permits_only_the_requested_resolution_mode(
    source, mode, operations, expected_content
):
    adapter, captured, address = source
    subjects = _subjects(address)
    evaluation = _evaluation(subjects, operations=operations)
    decision = PolicyEvaluator().evaluate(
        evaluation, _configuration(subjects, operations=operations)
    )
    assert decision.result == "permit"
    binding = PolicyDecisionValidator().validate(decision, evaluation)
    assert binding.disposition == "valid"

    result = _resolve(adapter, captured, address, evaluation, decision, mode=mode)

    assert result.status == "resolved"
    assert result.content == expected_content
    other_mode = "metadata_only" if mode == "content" else "content"
    _assert_private_denial(
        _resolve(adapter, captured, address, evaluation, decision, mode=other_mode)
    )


@pytest.mark.parametrize(
    "request_changes",
    [
        {"consumer_ref": "OTHER-CONSUMER"},
        {"consumer_ref": ""},
        {"purpose": "another_purpose"},
        {"purpose": ""},
        {"mode": "export"},
    ],
)
def test_consumer_purpose_and_mode_cannot_reuse_an_unrelated_permit(
    source, request_changes
):
    adapter, captured, address = source
    subjects = _subjects(address)
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(evaluation, _configuration(subjects))

    _assert_private_denial(
        _resolve(adapter, captured, address, evaluation, decision, **request_changes)
    )


def test_denials_do_not_inspect_or_disclose_source_existence(source, monkeypatch):
    adapter, captured, address = source
    subjects = _subjects(address)
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(
        evaluation, _configuration(subjects, effect="deny")
    )
    assert decision.result == "deny"

    def forbidden_integrity_lookup(*args, **kwargs):
        pytest.fail("Source integrity was inspected before authorization")

    monkeypatch.setattr(adapter, "resolve", forbidden_integrity_lookup)
    for supplied_address in (
        address,
        replace(address, evidence_address_ref="EVA-DOES-NOT-EXIST"),
    ):
        for supplied_capture in (
            captured,
            replace(captured, raw_content=b"not-the-snapshot-content"),
        ):
            for supplied_evaluation, supplied_decision in (
                (None, None),
                (evaluation, None),
                (None, decision),
                (evaluation, decision),
            ):
                _assert_private_denial(
                    _resolve(
                        adapter,
                        supplied_capture,
                        supplied_address,
                        supplied_evaluation,
                        supplied_decision,
                    )
                )


@pytest.mark.parametrize(
    ("subject_index", "field", "wrong_value"),
    [
        (0, "stable_id", "EVA-ANOTHER-ADDRESS"),
        (1, "stable_id", "SNAP-ANOTHER-SNAPSHOT"),
        (0, "version", "999"),
        (1, "version", "999"),
        (0, "authority_context", "Semantic Core"),
        (1, "authority_context", "Semantic Core"),
        (0, "subject_type", "claim"),
        (1, "subject_type", "source_record"),
    ],
)
def test_permit_for_different_subject_contract_cannot_resolve_source(
    source, subject_index, field, wrong_value
):
    adapter, captured, address = source
    subjects = list(_subjects(address))
    subjects[subject_index] = replace(subjects[subject_index], **{field: wrong_value})
    subjects = tuple(subjects)
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(evaluation, _configuration(subjects))
    # A real, internally consistent permit for another subject is still unusable.
    assert decision.result == "permit"
    binding = PolicyDecisionValidator().validate(decision, evaluation)
    assert binding.disposition == "valid"

    _assert_private_denial(_resolve(adapter, captured, address, evaluation, decision))


@pytest.mark.parametrize("retained_subject", [0, 1])
def test_evidence_and_snapshot_subjects_are_both_required(source, retained_subject):
    adapter, captured, address = source
    subjects = (_subjects(address)[retained_subject],)
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(evaluation, _configuration(subjects))
    assert decision.result == "permit"

    _assert_private_denial(_resolve(adapter, captured, address, evaluation, decision))


@pytest.mark.parametrize(
    "changes",
    [
        {"context_valid_at": "2026-08-31T12:00:00+02:00"},
        {"processing_zone": "another_zone"},
        {"policy_anchor_ids": (SOURCE_ANCHOR, "PA-EXTRA")},
        {"requested_effect_scope": "broader_scope"},
    ],
)
def test_stale_evaluation_cannot_reuse_a_previous_policy_decision(source, changes):
    adapter, captured, address = source
    subjects = _subjects(address)
    original = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(original, _configuration(subjects))
    changed = replace(original, **changes)
    assert PolicyDecisionValidator().validate(decision, changed).disposition == "stale"

    _assert_private_denial(_resolve(adapter, captured, address, changed, decision))


def test_policy_permit_cannot_omit_a_snapshot_anchor(source):
    adapter, captured, address = source
    subjects = _subjects(address)
    evaluation = _evaluation(subjects, anchors=())
    decision = PolicyEvaluator().evaluate(
        evaluation, _configuration(subjects, anchors=())
    )
    assert decision.result == "permit"

    _assert_private_denial(_resolve(adapter, captured, address, evaluation, decision))


@pytest.mark.parametrize("effect", ["deny", "review", "escalate", "conditions"])
def test_non_permit_policy_outcomes_never_resolve_content(source, effect):
    adapter, captured, address = source
    subjects = _subjects(address)
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(
        evaluation, _configuration(subjects, effect=effect)
    )
    assert decision.result == effect

    _assert_private_denial(_resolve(adapter, captured, address, evaluation, decision))


def test_unimplemented_redaction_condition_does_not_grant_content(source):
    adapter, captured, address = source
    subjects = _subjects(address)
    condition = PolicyCondition(
        condition_ref="PCOND-SYNTHETIC-REDACTION",
        condition_type="redaction",
        subject_refs=subjects,
        responsible_context="synthetic_test_policy_owner",
        required_evidence_refs=("REDACTION-EVIDENCE",),
        fulfilment_evidence_refs=("REDACTION-EVIDENCE",),
        enforcement_point="source_resolution",
        valid_from="2026-08-31T09:00:00+02:00",
        valid_until="2026-08-31T11:00:00+02:00",
        failure_action="deny",
        state="satisfied",
    )
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(
        evaluation, _configuration(subjects, conditions=(condition,))
    )
    assert decision.result == "permit" and decision.conditions

    _assert_private_denial(_resolve(adapter, captured, address, evaluation, decision))


def test_duplicate_public_and_restricted_passages_keep_separate_authorization(tmp_path):
    adapter = LocalHtmlAdapter()
    captured = _capture(
        tmp_path,
        "<p>Repeated passage.</p><aside class='internal-note'>"
        "<p>Repeated passage.</p></aside>",
    )
    with pytest.raises(ValueError, match="ambiguous"):
        adapter.evidence_address(captured, ["Repeated passage."])
    addresses = adapter.passage_evidence_addresses(captured)
    assert len(addresses) == 2
    public = next(address for address in addresses if not address.restricted)
    restricted = next(address for address in addresses if address.restricted)
    assert public.text == restricted.text
    assert public.selector != restricted.selector
    assert public.evidence_address_ref != restricted.evidence_address_ref
    subjects = _subjects(public)
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(evaluation, _configuration(subjects))

    public_result = _resolve(adapter, captured, public, evaluation, decision)
    assert public_result.content == public.text
    _assert_private_denial(
        _resolve(adapter, captured, restricted, evaluation, decision)
    )


def test_ancestor_inherits_restricted_descendant_before_content_resolution(tmp_path):
    adapter = LocalHtmlAdapter()
    captured = _capture(
        tmp_path,
        "<article><p>Public context.</p><aside class='internal-note'>"
        "<p>Confidential detail.</p></aside></article>",
    )
    address = adapter.evidence_address(captured, ["Public context.", "Confidential"])
    assert address.restricted
    assert set(address.policy_refs) > set(captured.snapshot.policy_refs)
    subjects = _subjects(address)
    insufficient = _evaluation(subjects)
    insufficient_decision = PolicyEvaluator().evaluate(
        insufficient, _configuration(subjects)
    )
    assert insufficient_decision.result == "permit"
    _assert_private_denial(
        _resolve(adapter, captured, address, insufficient, insufficient_decision)
    )

    complete = _evaluation(subjects, anchors=address.policy_refs)
    complete_decision = PolicyEvaluator().evaluate(
        complete, _configuration(subjects, anchors=address.policy_refs)
    )
    result = _resolve(adapter, captured, address, complete, complete_decision)
    assert result.status == "resolved"
    assert result.content == "Public context. Confidential detail."


@pytest.mark.parametrize(
    "selector_change",
    [
        {"selector_type": "unknown"},
        {"selector_version": "999"},
        {"target_type": "claim"},
        {"selector_type": "html_dom_path", "selector_value": ("/missing",)},
    ],
)
def test_valid_policy_does_not_reinterpret_unknown_or_missing_selectors(
    source, selector_change
):
    adapter, captured, address = source
    subjects = _subjects(address)
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(evaluation, _configuration(subjects))
    invalid = replace(address, selector=replace(address.selector, **selector_change))

    result = _resolve(adapter, captured, invalid, evaluation, decision)

    assert result.status == "not_resolvable"
    assert result.content is None
    assert "Public fixture" not in json.dumps(asdict(result))


@pytest.mark.parametrize(
    "json_value",
    ['"passage"', '["passage"]', '[["nested"]]', '{"fragment":"passage"}', "7"],
)
def test_selector_constructor_rejects_untyped_or_mutable_json_values(json_value):
    with pytest.raises((ValueError, TypeError)):
        Selector("text_fragments", "1", json.loads(json_value))


def test_selector_export_cannot_mutate_the_evidence_used_for_resolution(source):
    adapter, captured, address = source
    exported = json.loads(json.dumps(address.to_dict()))
    exported["selector"]["selector_value"].append("invented fragment")
    exported["text"] = "invented content"
    assert adapter.resolve(captured, address)
    with pytest.raises(FrozenInstanceError):
        address.selector.selector_value = ("invented fragment",)
    with pytest.raises((ValueError, TypeError)):
        replace(address, selector=exported["selector"])


def test_valid_policy_does_not_override_corrupt_snapshot_integrity(source):
    adapter, captured, address = source
    subjects = _subjects(address)
    evaluation = _evaluation(subjects)
    decision = PolicyEvaluator().evaluate(evaluation, _configuration(subjects))

    result = _resolve(
        adapter,
        replace(captured, raw_content=b"tampered content"),
        address,
        evaluation,
        decision,
    )

    assert result.status == "not_resolvable"
    assert result.content is None
