from __future__ import annotations

from dataclasses import replace

from cp_knowledge_tools.lifecycle import (
    G6PublicationReadinessGate,
    G6PublicationReadinessRequest,
    PublicationExecutor,
    PublicationRequestFactory,
    TestIsolatedPublicationTarget,
)

from .test_gates import _authority, _g5


def _ready_context():
    candidate, resolution, package, review, _, policy_decision, g5 = _g5()
    g6 = G6PublicationReadinessGate().evaluate(
        G6PublicationReadinessRequest(
            package=package,
            candidate_revision=candidate,
            resolution_decision=resolution,
            candidate_reviews_satisfied=True,
            publication_review=review,
            g5_result=g5,
            publication_authority=_authority(package),
            observed_prior_states=package.expected_prior_states,
            recovery_consequences_determined=True,
        )
    )
    assert g6.disposition == "ready"
    return candidate, package, review, policy_decision, g6


def _request(*, requested_at: str = "2026-08-15T10:05:00+02:00"):
    candidate, package, review, policy_decision, g6 = _ready_context()
    request = PublicationRequestFactory().create(
        package=package,
        g6_result=g6,
        policy_decision_ref=policy_decision.policy_decision_ref,
        publication_review_record_ref=review.review_record_ref or "",
        idempotency_key="D7-TEST-PUBLICATION",
        requested_at=requested_at,
    )
    return candidate, package, g6, request


def test_g7_exact_plan_execution_creates_record_only_after_verified_reread() -> None:
    candidate, package, g6, request = _request()
    target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states
    )

    result = PublicationExecutor().execute(
        request=request,
        package=package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:06:00+02:00",
    )

    assert result.disposition == "published"
    assert result.reason_code == "test_isolated_publication_finalized"
    assert result.change_set_applied is True
    assert result.candidate_closed_after_publication is True
    assert result.final_state_verified is True
    assert result.record is not None
    assert result.record.outcome == "success"
    assert result.record.publication_record_ref == (
        package.publication_finalization_plan.planned_publication_record_ref
    )
    assert result.record.publication_request_ref == request.publication_request_ref
    assert result.record.publication_finalization_plan_refs == (
        package.publication_finalization_plan.publication_finalization_plan_ref,
    )
    assert result.record.knowledge_content_hashes == (
        package.publication_unit_binding.content_hash,
    )
    assert result.record.final_representation_hashes[0].hash_scope == (
        "publication_unit_final_representation"
    )
    final = target.read(package.publication_finalization_plan.canonical_path)
    assert final is not None
    assert final.manifest["canonical_path"] == (
        package.publication_finalization_plan.canonical_path
    )
    assert final.manifest["publication"]["publication_state"] == "published"
    assert final.manifest["publication"]["publication_record_ref"] == (
        result.record.publication_record_ref
    )
    assert final.manifest["knowledge_object_id"] == "KO-TEST"
    assert final.manifest["knowledge_object_version"] == "0.2"
    assert result.changed_fields == (
        "canonical_path",
        "publication.publication_state",
        "publication.publication_record_ref",
        "publication.published_at",
        "publication.publisher_ref",
        "publication.predecessor_publication_ref",
        "markdown_section:publication",
    )


def test_g7_same_key_and_fingerprint_returns_same_record_without_second_commit(
) -> None:
    _, package, g6, request = _request()
    target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states
    )
    executor = PublicationExecutor()

    first = executor.execute(
        request=request,
        package=package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:06:00+02:00",
    )
    repeated = executor.execute(
        request=request,
        package=package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:07:00+02:00",
    )

    assert repeated.disposition == "idempotent_replay"
    assert repeated.record == first.record
    assert target.commit_count == 1


def test_g7_same_key_with_different_fingerprint_is_conflict() -> None:
    _, package, g6, request = _request()
    _, _, _, changed_request = _request(
        requested_at="2026-08-15T10:05:01+02:00"
    )
    target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states
    )
    executor = PublicationExecutor()
    first = executor.execute(
        request=request,
        package=package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:06:00+02:00",
    )
    conflict = executor.execute(
        request=changed_request,
        package=package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:07:00+02:00",
    )

    assert first.disposition == "published"
    assert conflict.disposition == "blocked"
    assert conflict.reason_code == "idempotency_conflict"
    assert conflict.record is None
    assert target.commit_count == 1


def test_g7_blocks_changed_prepublication_representation_before_mutation() -> None:
    _, package, g6, request = _request()
    changed_unit = replace(
        package.publication_unit_binding,
        markdown_body=(
            package.publication_unit_binding.markdown_body.replace(
                "Synthetic knowledge.", "Changed knowledge."
            )
        ),
    )
    changed_package = replace(package, publication_unit_binding=changed_unit)
    target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states
    )

    result = PublicationExecutor().execute(
        request=request,
        package=changed_package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:06:00+02:00",
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "prepublication_representation_hash_mismatch"
    assert result.record is None
    assert target.commit_count == 0


def test_g7_rejects_mutated_finalization_plan_before_mutation() -> None:
    _, package, g6, request = _request()
    changed_plan = replace(
        package.publication_finalization_plan,
        allowed_finalization_fields=(
            *package.publication_finalization_plan.allowed_finalization_fields,
            "claims",
        ),
    )
    changed_package = replace(package, publication_finalization_plan=changed_plan)
    target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states
    )

    result = PublicationExecutor().execute(
        request=request,
        package=changed_package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:06:00+02:00",
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "publication_finalization_plan_integrity_invalid"
    assert result.record is None
    assert target.commit_count == 0


def test_g7_postcommit_verification_failure_is_fully_compensated() -> None:
    _, package, g6, request = _request()
    target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states,
        fault_mode="tamper_postcommit_reread",
    )

    result = PublicationExecutor().execute(
        request=request,
        package=package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:06:00+02:00",
    )

    assert result.disposition == "compensated_failure"
    assert result.reason_code == "final_state_verification_failed_compensated"
    assert result.record is None
    assert result.change_set_applied is False
    assert target.read(package.publication_finalization_plan.canonical_path) is None
    assert target.compensation_count == 1


def test_g7_uncompensated_partial_state_is_fatal_and_never_success() -> None:
    _, package, g6, request = _request()
    target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states,
        fault_mode="tamper_postcommit_reread_and_fail_compensation",
    )

    result = PublicationExecutor().execute(
        request=request,
        package=package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:06:00+02:00",
    )

    assert result.disposition == "fatal"
    assert result.reason_code == "publication_partial_uncompensated"
    assert result.record is None
    assert result.change_set_applied is False
