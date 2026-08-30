from __future__ import annotations

from pathlib import Path

import pytest

from cp_knowledge_tools.operations.contracts import (
    MutationAction,
    MutationKind,
    MutationPlan,
    PostconditionReport,
    ResultDisposition,
)
from cp_knowledge_tools.operations.transactions.filesystem import (
    FileTransactionEngine,
    PathSafetyError,
)


def _plan(*actions: MutationAction, fingerprint: str = "request-a") -> MutationPlan:
    return MutationPlan(
        plan_id="plan-fs",
        request_fingerprint=fingerprint,
        actions=actions,
        expected_source_fingerprints={},
    )


def test_filesystem_commit_reread_and_persisted_idempotency(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    runs = tmp_path / "runs"
    root.mkdir()
    (root / "a.txt").write_text("old", encoding="utf-8")
    engine = FileTransactionEngine(root=root, run_root=runs)
    plan = _plan(
        MutationAction(
            MutationKind.REPLACE,
            "a.txt",
            content="new",
            expected_fingerprint=engine.fingerprint("a.txt"),
        )
    )

    first = engine.apply(plan, idempotency_key="same-key")
    replay = FileTransactionEngine(root=root, run_root=runs).apply(
        plan, idempotency_key="same-key"
    )
    conflict = engine.apply(
        _plan(*plan.actions, fingerprint="other"), idempotency_key="same-key"
    )

    assert first.disposition is ResultDisposition.SUCCEEDED
    assert (root / "a.txt").read_text(encoding="utf-8") == "new"
    assert replay.disposition is ResultDisposition.IDEMPOTENT_REPLAY
    assert conflict.disposition is ResultDisposition.CONFLICT


def test_missing_or_symlink_mutation_root_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        FileTransactionEngine(root=missing, run_root=tmp_path / "runs-missing")
    assert not missing.exists()

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(PathSafetyError, match="symlink"):
        FileTransactionEngine(root=link, run_root=tmp_path / "runs-link")


def test_source_fingerprint_conflict_has_no_mutation(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("changed", encoding="utf-8")
    engine = FileTransactionEngine(root=root, run_root=tmp_path / "runs")
    plan = _plan(
        MutationAction(
            MutationKind.REPLACE,
            "a.txt",
            content="new",
            expected_fingerprint="not-current",
        )
    )

    result = engine.apply(plan, idempotency_key="conflict")

    assert result.disposition is ResultDisposition.CONFLICT
    assert (root / "a.txt").read_text(encoding="utf-8") == "changed"


def test_plan_level_observed_source_fingerprint_is_enforced(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "observed.txt").write_text("changed", encoding="utf-8")
    engine = FileTransactionEngine(root=root, run_root=tmp_path / "runs")
    plan = MutationPlan(
        plan_id="observed-source",
        request_fingerprint="request-observed",
        actions=(MutationAction(MutationKind.CREATE, "new.txt", content="new"),),
        expected_source_fingerprints={"observed.txt": "not-current"},
    )

    result = engine.apply(plan, idempotency_key="observed")

    assert result.disposition is ResultDisposition.CONFLICT
    assert not (root / "new.txt").exists()


@pytest.mark.parametrize("path", ["../escape.txt", "/tmp/escape.txt", "a/../../x"])
def test_path_traversal_is_blocked(tmp_path: Path, path: str) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    engine = FileTransactionEngine(root=root, run_root=tmp_path / "runs")

    with pytest.raises(PathSafetyError):
        engine.preview(_plan(MutationAction(MutationKind.CREATE, path, content="bad")))


def test_symlink_scope_escape_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    engine = FileTransactionEngine(root=root, run_root=tmp_path / "runs")

    with pytest.raises(PathSafetyError):
        engine.preview(
            _plan(MutationAction(MutationKind.CREATE, "link/escape", content="bad"))
        )


def test_second_write_failure_compensates(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("old-a", encoding="utf-8")
    (root / "b.txt").write_text("old-b", encoding="utf-8")
    engine = FileTransactionEngine(
        root=root,
        run_root=tmp_path / "runs",
        fail_action_index=1,
    )
    plan = _plan(
        MutationAction(MutationKind.REPLACE, "a.txt", content="new-a"),
        MutationAction(MutationKind.REPLACE, "b.txt", content="new-b"),
    )

    result = engine.apply(plan, idempotency_key="partial")

    assert result.disposition is ResultDisposition.COMPENSATED_FAILURE
    assert (root / "a.txt").read_text(encoding="utf-8") == "old-a"
    assert (root / "b.txt").read_text(encoding="utf-8") == "old-b"


def test_staging_failure_and_first_write_failure_do_not_commit(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("old", encoding="utf-8")
    plan = _plan(MutationAction(MutationKind.REPLACE, "a.txt", content="new"))
    staging = FileTransactionEngine(
        root=root,
        run_root=tmp_path / "runs-staging",
        fail_staging=True,
    )
    first_write = FileTransactionEngine(
        root=root,
        run_root=tmp_path / "runs-write",
        fail_action_index=0,
    )

    staging_result = staging.apply(plan, idempotency_key="staging")
    first_write_result = first_write.apply(plan, idempotency_key="first")

    assert (
        staging_result.disposition is ResultDisposition.VALIDATION_FAILED_BEFORE_COMMIT
    )
    assert first_write_result.disposition is ResultDisposition.FAILED_BEFORE_MUTATION
    assert (root / "a.txt").read_text(encoding="utf-8") == "old"


def test_planned_path_postcommit_manipulation_is_compensated(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("old", encoding="utf-8")

    def tamper(transaction_root: Path) -> None:
        (transaction_root / "a.txt").write_text("tampered", encoding="utf-8")

    engine = FileTransactionEngine(
        root=root,
        run_root=tmp_path / "runs",
        postcommit_hook=tamper,
    )
    result = engine.apply(
        _plan(MutationAction(MutationKind.REPLACE, "a.txt", content="new")),
        idempotency_key="tampered",
    )

    assert result.disposition is ResultDisposition.COMPENSATED_FAILURE
    assert (root / "a.txt").read_text(encoding="utf-8") == "old"


def test_domain_postcondition_failure_is_compensated_and_reread(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("old", encoding="utf-8")
    engine = FileTransactionEngine(root=root, run_root=tmp_path / "runs")

    result = engine.apply(
        _plan(MutationAction(MutationKind.REPLACE, "a.txt", content="new")),
        idempotency_key="domain-failure",
        domain_verifier=lambda _: PostconditionReport(
            passed=False,
            results=({"code": "domain_failure", "passed": False, "actual": "invalid"},),
        ),
    )

    assert result.disposition is ResultDisposition.COMPENSATED_FAILURE
    assert result.compensation_status == "compensated"
    assert result.postcondition_report is not None
    assert result.postcondition_report.passed is False
    assert result.outputs["transaction_state"] == "compensated"
    assert (root / "a.txt").read_text(encoding="utf-8") == "old"


def test_domain_failure_with_failed_compensation_persists_recovery_record(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    runs = tmp_path / "runs"
    root.mkdir()
    (root / "a.txt").write_text("old", encoding="utf-8")
    engine = FileTransactionEngine(
        root=root,
        run_root=runs,
        fail_compensation=True,
    )

    result = engine.apply(
        _plan(MutationAction(MutationKind.REPLACE, "a.txt", content="new")),
        idempotency_key="domain-fatal",
        domain_verifier=lambda _: PostconditionReport(
            passed=False,
            results=({"code": "domain_failure", "passed": False},),
        ),
    )

    assert result.disposition is ResultDisposition.RECOVERY_REQUIRED
    assert result.recovery_record is not None
    assert result.outputs["transaction_state"] == "fatal_partial_state"
    assert (root / "a.txt").read_text(encoding="utf-8") == "new"
    recovery_path = runs / "recovery" / f"{result.recovery_record.recovery_id}.json"
    assert recovery_path.exists()


def test_failed_compensation_surfaces_recovery(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("old-a", encoding="utf-8")
    (root / "b.txt").write_text("old-b", encoding="utf-8")
    engine = FileTransactionEngine(
        root=root,
        run_root=tmp_path / "runs",
        fail_action_index=1,
        fail_compensation=True,
    )
    result = engine.apply(
        _plan(
            MutationAction(MutationKind.REPLACE, "a.txt", content="new-a"),
            MutationAction(MutationKind.REPLACE, "b.txt", content="new-b"),
        ),
        idempotency_key="fatal",
    )

    assert result.disposition is ResultDisposition.RECOVERY_REQUIRED
    assert result.recovery_record is not None
    assert result.recovery_record.changed_paths


def test_unplanned_postcommit_mutation_is_not_success(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("old", encoding="utf-8")
    (root / "unplanned.txt").write_text("safe", encoding="utf-8")

    def tamper(transaction_root: Path) -> None:
        (transaction_root / "unplanned.txt").write_text("tampered", encoding="utf-8")

    engine = FileTransactionEngine(
        root=root,
        run_root=tmp_path / "runs",
        postcommit_hook=tamper,
    )
    result = engine.apply(
        _plan(MutationAction(MutationKind.REPLACE, "a.txt", content="new")),
        idempotency_key="unplanned",
    )

    assert result.disposition is ResultDisposition.RECOVERY_REQUIRED
    assert "unplanned.txt" in result.recovery_record.changed_paths
