from __future__ import annotations

import pytest

from cp_knowledge_tools.operations.contracts import (
    MutationAction,
    MutationKind,
    MutationPlan,
    ResultDisposition,
    RunState,
)
from cp_knowledge_tools.operations.controller import InProcessRunController
from cp_knowledge_tools.operations.transactions.in_memory import (
    InMemoryTransactionTarget,
)


def _plan(*actions: MutationAction, fingerprint: str = "request-a") -> MutationPlan:
    return MutationPlan(
        plan_id="plan-1",
        request_fingerprint=fingerprint,
        actions=actions,
        expected_source_fingerprints={},
    )


def test_run_controller_accepts_success_and_failure_paths() -> None:
    controller = InProcessRunController()
    for state in (
        RunState.CONTEXT_RESOLVED,
        RunState.PREFLIGHT_PASSED,
        RunState.PLANNED,
        RunState.PREVIEWED,
        RunState.AWAITING_AUTHORITY,
        RunState.AUTHORIZED,
        RunState.STAGING,
        RunState.APPLYING,
        RunState.VERIFYING,
        RunState.SUCCEEDED,
    ):
        controller.transition(state)
    assert controller.state is RunState.SUCCEEDED

    failure = InProcessRunController(state=RunState.APPLYING)
    failure.transition(RunState.PARTIAL_STATE_DETECTED)
    failure.transition(RunState.COMPENSATING)
    failure.transition(RunState.FATAL_PARTIAL_STATE)
    failure.transition(RunState.RECOVERY_REQUIRED)
    assert failure.state is RunState.RECOVERY_REQUIRED


def test_run_controller_rejects_artifact_lifecycle_state() -> None:
    controller = InProcessRunController()
    with pytest.raises(ValueError):
        controller.transition(RunState.SUCCEEDED)


def test_in_memory_commit_reread_and_idempotency() -> None:
    target = InMemoryTransactionTarget({"a.txt": b"old"})
    plan = _plan(
        MutationAction(
            kind=MutationKind.REPLACE,
            path="a.txt",
            content="new",
            expected_fingerprint=target.fingerprint("a.txt"),
        )
    )

    first = target.apply(plan, idempotency_key="idem")
    replay = target.apply(plan, idempotency_key="idem")
    conflict = target.apply(
        _plan(*plan.actions, fingerprint="request-b"),
        idempotency_key="idem",
    )

    assert first.disposition is ResultDisposition.SUCCEEDED
    assert target.reread("a.txt") == b"new"
    assert replay.disposition is ResultDisposition.IDEMPOTENT_REPLAY
    assert conflict.disposition is ResultDisposition.CONFLICT


def test_in_memory_postcommit_manipulation_is_detected_and_compensated() -> None:
    target = InMemoryTransactionTarget(
        {"a.txt": b"old"},
        postcommit_hook=lambda files: files.__setitem__("a.txt", b"tampered"),
    )
    plan = _plan(
        MutationAction(
            kind=MutationKind.REPLACE,
            path="a.txt",
            content="new",
            expected_fingerprint=target.fingerprint("a.txt"),
        )
    )

    result = target.apply(plan, idempotency_key="tamper")

    assert result.disposition is ResultDisposition.COMPENSATED_FAILURE
    assert target.reread("a.txt") == b"old"


def test_in_memory_partial_failure_compensates_or_requires_recovery() -> None:
    actions = (
        MutationAction(MutationKind.REPLACE, "a.txt", content="new-a"),
        MutationAction(MutationKind.REPLACE, "b.txt", content="new-b"),
    )
    successful_rollback = InMemoryTransactionTarget(
        {"a.txt": b"old-a", "b.txt": b"old-b"},
        fail_action_index=1,
    )
    failed_rollback = InMemoryTransactionTarget(
        {"a.txt": b"old-a", "b.txt": b"old-b"},
        fail_action_index=1,
        fail_compensation=True,
    )

    compensated = successful_rollback.apply(_plan(*actions), idempotency_key="one")
    fatal = failed_rollback.apply(_plan(*actions), idempotency_key="two")

    assert compensated.disposition is ResultDisposition.COMPENSATED_FAILURE
    assert successful_rollback.reread("a.txt") == b"old-a"
    assert fatal.disposition is ResultDisposition.RECOVERY_REQUIRED
    assert fatal.recovery_record is not None
