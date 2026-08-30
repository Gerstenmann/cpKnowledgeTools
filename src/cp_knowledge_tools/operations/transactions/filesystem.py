"""Root-bounded transactional filesystem mutation with visible recovery."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes

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
from ..results import to_primitive


class PathSafetyError(ValueError):
    """Raised when a mutation path can escape its verified root."""


class SourceFingerprintConflict(RuntimeError):
    """Raised when the source changed after preview."""


class StagingValidationError(RuntimeError):
    """Raised when an action sequence cannot be staged safely."""


class DomainPostconditionError(RuntimeError):
    """Raised while still inside the transaction success boundary."""

    def __init__(self, report: PostconditionReport) -> None:
        super().__init__("domain postconditions failed after mutation reread")
        self.report = report


class FileTransactionEngine:
    def __init__(
        self,
        root: Path,
        run_root: Path,
        *,
        fail_action_index: int | None = None,
        fail_compensation: bool = False,
        fail_staging: bool = False,
        postcommit_hook: Callable[[Path], None] | None = None,
    ) -> None:
        if root.is_symlink():
            raise PathSafetyError("mutation root must not be a symlink")
        self.root = root.resolve()
        self.run_root = run_root.resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"mutation root does not exist: {self.root}")
        if not self.root.is_dir():
            raise PathSafetyError(f"mutation root is not a directory: {self.root}")
        if self.run_root == self.root or self.root in self.run_root.parents:
            raise PathSafetyError("run_root must remain outside the mutation root")
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.fail_action_index = fail_action_index
        self.fail_compensation = fail_compensation
        self.fail_staging = fail_staging
        self.postcommit_hook = postcommit_hook

    def _safe_path(self, relative_path: str, *, require_exists: bool = False) -> Path:
        pure = PurePosixPath(relative_path)
        if (
            pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise PathSafetyError(f"unsafe relative path: {relative_path!r}")
        candidate = self.root.joinpath(*pure.parts)
        if candidate.is_symlink():
            raise PathSafetyError(f"symlink targets are not mutable: {relative_path}")
        existing_parent = candidate.parent
        while not existing_parent.exists() and existing_parent != self.root:
            existing_parent = existing_parent.parent
        resolved_parent = existing_parent.resolve()
        if resolved_parent != self.root and self.root not in resolved_parent.parents:
            raise PathSafetyError(f"path escapes root through symlink: {relative_path}")
        if candidate.exists():
            resolved = candidate.resolve()
            if resolved != self.root and self.root not in resolved.parents:
                raise PathSafetyError(f"path escapes root: {relative_path}")
        elif require_exists:
            raise FileNotFoundError(relative_path)
        return candidate

    def fingerprint(self, relative_path: str) -> str | None:
        path = self._safe_path(relative_path)
        if not path.exists():
            return None
        if not path.is_file():
            raise PathSafetyError(f"target is not a regular file: {relative_path}")
        return sha256_bytes(path.read_bytes())

    def _snapshot(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for path in sorted(self.root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            snapshot[path.relative_to(self.root).as_posix()] = path.read_bytes()
        return snapshot

    @staticmethod
    def _content(action: MutationAction) -> bytes:
        if action.content is None:
            raise StagingValidationError(f"{action.kind} requires content")
        return (
            action.content.encode("utf-8")
            if isinstance(action.content, str)
            else action.content
        )

    @classmethod
    def _simulate_action(cls, state: dict[str, bytes], action: MutationAction) -> None:
        if action.kind is MutationKind.CREATE:
            if action.path in state:
                raise StagingValidationError(f"CREATE target exists: {action.path}")
            state[action.path] = cls._content(action)
        elif action.kind is MutationKind.REPLACE:
            if action.path not in state:
                raise StagingValidationError(f"REPLACE target missing: {action.path}")
            state[action.path] = cls._content(action)
        elif action.kind is MutationKind.DELETE:
            if action.path not in state:
                raise StagingValidationError(f"DELETE target missing: {action.path}")
            del state[action.path]
        elif action.kind is MutationKind.MOVE:
            if not action.destination:
                raise StagingValidationError("MOVE requires destination")
            if action.path not in state:
                raise StagingValidationError(f"MOVE source missing: {action.path}")
            if action.destination in state:
                raise StagingValidationError(
                    f"MOVE destination exists: {action.destination}"
                )
            state[action.destination] = state.pop(action.path)

    def preview(self, plan: MutationPlan) -> dict[str, object]:
        if self.fail_staging:
            raise StagingValidationError("injected staging validation failure")
        for path, expected in plan.expected_source_fingerprints.items():
            if self.fingerprint(path) != expected:
                raise SourceFingerprintConflict(path)
        for action in plan.actions:
            self._safe_path(
                action.path,
                require_exists=action.kind
                in {MutationKind.REPLACE, MutationKind.DELETE, MutationKind.MOVE},
            )
            if action.destination:
                self._safe_path(action.destination)
            if (
                action.expected_fingerprint is not None
                and self.fingerprint(action.path) != action.expected_fingerprint
            ):
                raise SourceFingerprintConflict(action.path)
        before = self._snapshot()
        expected = dict(before)
        for action in plan.actions:
            self._simulate_action(expected, action)
        return {
            "plan_id": plan.plan_id,
            "request_fingerprint": plan.request_fingerprint,
            "actions": tuple(action.kind.value for action in plan.actions),
            "expected_state_fingerprint": canonical_json_hash(
                {key: sha256_bytes(value) for key, value in expected.items()}
            ),
        }

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".cpks-", dir=path.parent)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _execute_action(self, action: MutationAction) -> None:
        source = self._safe_path(
            action.path,
            require_exists=action.kind
            in {MutationKind.REPLACE, MutationKind.DELETE, MutationKind.MOVE},
        )
        if action.kind in {MutationKind.CREATE, MutationKind.REPLACE}:
            self._atomic_write(source, self._content(action))
        elif action.kind is MutationKind.DELETE:
            source.unlink()
        elif action.kind is MutationKind.MOVE:
            if action.destination is None:
                raise StagingValidationError("MOVE requires destination")
            destination = self._safe_path(action.destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)

    def _idempotency_path(self, key: str) -> Path:
        token = canonical_json_hash({"idempotency_key": key})
        return self.run_root / "idempotency" / f"{token}.json"

    def _idempotency_result(
        self, plan: MutationPlan, key: str
    ) -> ResultDisposition | None:
        return self.idempotency_disposition(key, plan.request_fingerprint)

    def idempotency_disposition(
        self,
        key: str,
        request_fingerprint: str,
    ) -> ResultDisposition | None:
        """Resolve a persisted replay before mutable source paths are reread."""

        path = self._idempotency_path(key)
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        return (
            ResultDisposition.IDEMPOTENT_REPLAY
            if record.get("request_fingerprint") == request_fingerprint
            else ResultDisposition.CONFLICT
        )

    def _write_idempotency(self, plan: MutationPlan, key: str, run_id: str) -> None:
        path = self._idempotency_path(key)
        self._atomic_write(
            path,
            json.dumps(
                {
                    "contract_version": "0.1",
                    "request_fingerprint": plan.request_fingerprint,
                    "plan_id": plan.plan_id,
                    "run_id": run_id,
                    "recorded_at": utc_now(),
                },
                sort_keys=True,
            ).encode("utf-8"),
        )

    def _restore(self, before: dict[str, bytes], affected: set[str]) -> None:
        if self.fail_compensation:
            raise OSError("injected compensation failure")
        for relative in sorted(affected):
            path = self._safe_path(relative)
            if relative in before:
                self._atomic_write(path, before[relative])
            elif path.exists():
                path.unlink()

    def _write_recovery(self, record: RecoveryRecord) -> None:
        try:
            path = self.run_root / "recovery" / f"{record.recovery_id}.json"
            self._atomic_write(
                path,
                json.dumps(to_primitive(record), indent=2, sort_keys=True).encode(
                    "utf-8"
                ),
            )
        except OSError:
            pass

    @staticmethod
    def _changed(before: dict[str, bytes], after: dict[str, bytes]) -> set[str]:
        return {
            path
            for path in before.keys() | after.keys()
            if before.get(path) != after.get(path)
        }

    @staticmethod
    def _result(
        disposition: ResultDisposition,
        run_id: str,
        message: str,
        *,
        changed: set[str] | None = None,
        compensation_status: str = "none",
        recovery: RecoveryRecord | None = None,
        postconditions: PostconditionReport | None = None,
        transaction_state: str = "none",
    ) -> OperationResult:
        return OperationResult(
            operation_name="transaction.filesystem",
            operation_version="0.1",
            disposition=disposition,
            run_id=run_id,
            correlation_id=run_id,
            message=message,
            outputs={"transaction_state": transaction_state},
            actual_mutations=tuple(sorted(changed or ())),
            postcondition_report=postconditions
            or PostconditionReport(
                passed=disposition is ResultDisposition.SUCCEEDED, results=()
            ),
            compensation_status=compensation_status,
            recovery_record=recovery,
        )

    def apply(
        self,
        plan: MutationPlan,
        *,
        idempotency_key: str,
        domain_verifier: Callable[[Path], PostconditionReport] | None = None,
        verification_hook: Callable[[], None] | None = None,
        run_id: str | None = None,
    ) -> OperationResult:
        run_id = run_id or f"run-{uuid.uuid4().hex}"
        replay = self._idempotency_result(plan, idempotency_key)
        if replay is not None:
            return self._result(
                replay,
                run_id,
                "idempotent replay"
                if replay is ResultDisposition.IDEMPOTENT_REPLAY
                else "idempotency key conflict",
                transaction_state="none",
            )
        try:
            self.preview(plan)
        except SourceFingerprintConflict as exc:
            return self._result(
                ResultDisposition.CONFLICT,
                run_id,
                f"source fingerprint conflict: {exc}",
                transaction_state="none",
            )
        except (StagingValidationError, FileNotFoundError) as exc:
            return self._result(
                ResultDisposition.VALIDATION_FAILED_BEFORE_COMMIT,
                run_id,
                str(exc),
                transaction_state="staged",
            )

        before = self._snapshot()
        expected = dict(before)
        for action in plan.actions:
            self._simulate_action(expected, action)
        planned_paths = {action.path for action in plan.actions}
        planned_paths.update(
            action.destination
            for action in plan.actions
            if action.destination is not None
        )
        mutated: set[str] = set()
        postconditions: PostconditionReport | None = None
        try:
            for index, action in enumerate(plan.actions):
                if self.fail_action_index == index:
                    raise OSError(f"injected failure at action {index}")
                self._execute_action(action)
                mutated.add(action.path)
                if action.destination:
                    mutated.add(action.destination)
            if self.postcommit_hook is not None:
                self.postcommit_hook(self.root)
            if verification_hook is not None:
                verification_hook()
            actual = self._snapshot()
            if actual != expected:
                raise RuntimeError("postcommit reread detected unplanned mutation")
            if domain_verifier is not None:
                postconditions = domain_verifier(self.root)
                if not postconditions.passed:
                    raise DomainPostconditionError(postconditions)
        except Exception as exc:  # transaction boundary must classify actual mutation
            if isinstance(exc, DomainPostconditionError):
                postconditions = exc.report
            elif domain_verifier is not None and postconditions is None:
                postconditions = PostconditionReport(
                    passed=False,
                    results=(
                        {
                            "code": "domain_verifier_error",
                            "passed": False,
                            "message": str(exc),
                        },
                    ),
                )
            actual = self._snapshot()
            changed = self._changed(before, actual)
            if not changed:
                return self._result(
                    ResultDisposition.FAILED_BEFORE_MUTATION,
                    run_id,
                    str(exc),
                    postconditions=postconditions,
                    transaction_state="none",
                )
            unplanned = changed - planned_paths
            compensation_error: str | None = None
            try:
                self._restore(before, planned_paths)
            except OSError as compensation_exc:
                compensation_error = str(compensation_exc)
            after_compensation = self._snapshot()
            remaining = self._changed(before, after_compensation)
            if compensation_error is None and not remaining:
                return self._result(
                    ResultDisposition.COMPENSATED_FAILURE,
                    run_id,
                    str(exc),
                    changed=changed,
                    compensation_status="compensated",
                    postconditions=postconditions,
                    transaction_state="compensated",
                )
            recovery = RecoveryRecord(
                recovery_id=f"REC-{uuid.uuid4().hex[:16]}",
                run_id=run_id,
                mutation_state="partial",
                changed_paths=tuple(sorted(remaining or changed or unplanned)),
                required_actions=(
                    "reread changed paths",
                    "perform owner-controlled recovery",
                ),
                created_at=utc_now(),
                compensation_error=compensation_error,
            )
            self._write_recovery(recovery)
            return self._result(
                ResultDisposition.RECOVERY_REQUIRED,
                run_id,
                str(exc),
                changed=changed,
                compensation_status="failed" if compensation_error else "partial",
                recovery=recovery,
                postconditions=postconditions,
                transaction_state="fatal_partial_state",
            )

        self._write_idempotency(plan, idempotency_key, run_id)
        journal_path = self.run_root / "journals" / f"{run_id}.json"
        self._atomic_write(
            journal_path,
            json.dumps(
                {
                    "contract_version": "0.1",
                    "run_id": run_id,
                    "plan_id": plan.plan_id,
                    "request_fingerprint": plan.request_fingerprint,
                    "actual_mutations": sorted(mutated),
                    "completed_at": utc_now(),
                    "disposition": "succeeded",
                },
                indent=2,
                sort_keys=True,
            ).encode("utf-8"),
        )
        return self._result(
            ResultDisposition.SUCCEEDED,
            run_id,
            "transaction committed, reread, and verified",
            changed=mutated,
            postconditions=postconditions,
            transaction_state="applied",
        )
