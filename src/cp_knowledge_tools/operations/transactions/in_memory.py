"""Test-isolated in-memory transaction target with fault injection."""

from __future__ import annotations

import uuid
from collections.abc import Callable, MutableMapping

from cp_knowledge_tools.platform.hashing import sha256_bytes

from ..contracts import (
    MutationAction,
    MutationKind,
    MutationPlan,
    OperationResult,
    PostconditionReport,
    RecoveryRecord,
    ResultDisposition,
    utc_now,
)


class InMemoryTransactionTarget:
    def __init__(
        self,
        files: dict[str, bytes] | None = None,
        *,
        fail_action_index: int | None = None,
        fail_compensation: bool = False,
        postcommit_hook: Callable[[MutableMapping[str, bytes]], None] | None = None,
    ) -> None:
        self._files = dict(files or {})
        self._idempotency: dict[str, str] = {}
        self.fail_action_index = fail_action_index
        self.fail_compensation = fail_compensation
        self.postcommit_hook = postcommit_hook

    def fingerprint(self, path: str) -> str | None:
        content = self._files.get(path)
        return sha256_bytes(content) if content is not None else None

    def reread(self, path: str) -> bytes | None:
        return self._files.get(path)

    @staticmethod
    def _content(action: MutationAction) -> bytes:
        if action.content is None:
            raise ValueError(f"{action.kind} requires content")
        return (
            action.content.encode("utf-8")
            if isinstance(action.content, str)
            else action.content
        )

    @classmethod
    def _execute(cls, files: dict[str, bytes], action: MutationAction) -> None:
        if action.kind is MutationKind.CREATE:
            if action.path in files:
                raise FileExistsError(action.path)
            files[action.path] = cls._content(action)
        elif action.kind is MutationKind.REPLACE:
            if action.path not in files:
                raise FileNotFoundError(action.path)
            files[action.path] = cls._content(action)
        elif action.kind is MutationKind.DELETE:
            if action.path not in files:
                raise FileNotFoundError(action.path)
            del files[action.path]
        elif action.kind is MutationKind.MOVE:
            if action.destination is None:
                raise ValueError("MOVE requires destination")
            if action.path not in files:
                raise FileNotFoundError(action.path)
            if action.destination in files:
                raise FileExistsError(action.destination)
            files[action.destination] = files.pop(action.path)
        else:  # pragma: no cover - enum closes this branch
            raise ValueError(f"unsupported action: {action.kind}")

    def _result(
        self,
        disposition: ResultDisposition,
        message: str,
        *,
        changed_paths: tuple[str, ...] = (),
        recovery: RecoveryRecord | None = None,
        compensation_status: str = "none",
    ) -> OperationResult:
        return OperationResult(
            operation_name="transaction.in_memory",
            operation_version="0.1",
            disposition=disposition,
            run_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
            message=message,
            actual_mutations=changed_paths,
            postcondition_report=PostconditionReport(
                passed=disposition is ResultDisposition.SUCCEEDED,
                results=(),
            ),
            compensation_status=compensation_status,
            recovery_record=recovery,
        )

    def apply(self, plan: MutationPlan, *, idempotency_key: str) -> OperationResult:
        existing = self._idempotency.get(idempotency_key)
        if existing is not None:
            if existing == plan.request_fingerprint:
                return self._result(
                    ResultDisposition.IDEMPOTENT_REPLAY, "idempotent replay"
                )
            return self._result(ResultDisposition.CONFLICT, "idempotency key conflict")

        for path, expected in plan.expected_source_fingerprints.items():
            if self.fingerprint(path) != expected:
                return self._result(
                    ResultDisposition.CONFLICT, "source fingerprint conflict"
                )
        for action in plan.actions:
            if (
                action.expected_fingerprint is not None
                and self.fingerprint(action.path) != action.expected_fingerprint
            ):
                return self._result(
                    ResultDisposition.CONFLICT, "source fingerprint conflict"
                )

        before = dict(self._files)
        expected = dict(before)
        try:
            for action in plan.actions:
                self._execute(expected, action)
        except (FileExistsError, FileNotFoundError, ValueError) as exc:
            return self._result(
                ResultDisposition.VALIDATION_FAILED_BEFORE_COMMIT,
                f"staging validation failed: {exc}",
            )

        changed: set[str] = set()
        try:
            for index, action in enumerate(plan.actions):
                if self.fail_action_index == index:
                    raise OSError(f"injected failure at action {index}")
                self._execute(self._files, action)
                changed.add(action.path)
                if action.destination:
                    changed.add(action.destination)
            if self.postcommit_hook is not None:
                self.postcommit_hook(self._files)
            if self._files != expected:
                raise RuntimeError("postcommit reread detected unplanned mutation")
        except (
            Exception
        ) as exc:  # fault target intentionally captures injected failures
            if not changed:
                self._files = before
                return self._result(
                    ResultDisposition.FAILED_BEFORE_MUTATION,
                    str(exc),
                )
            if not self.fail_compensation:
                self._files = before
                return self._result(
                    ResultDisposition.COMPENSATED_FAILURE,
                    str(exc),
                    changed_paths=tuple(sorted(changed)),
                    compensation_status="compensated",
                )
            recovery = RecoveryRecord(
                recovery_id=f"REC-{uuid.uuid4().hex[:12]}",
                run_id=f"run-{uuid.uuid4().hex[:12]}",
                mutation_state="partial",
                changed_paths=tuple(sorted(changed)),
                required_actions=("manual reread and recovery",),
                created_at=utc_now(),
                compensation_error="injected compensation failure",
            )
            return self._result(
                ResultDisposition.RECOVERY_REQUIRED,
                str(exc),
                changed_paths=tuple(sorted(changed)),
                compensation_status="failed",
                recovery=recovery,
            )

        self._idempotency[idempotency_key] = plan.request_fingerprint
        return self._result(
            ResultDisposition.SUCCEEDED,
            "transaction committed and verified",
            changed_paths=tuple(sorted(changed)),
        )
