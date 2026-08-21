from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from ._common import content_hash, local_ref, ordered_unique
from .gates import G6PublicationReadinessResult
from .publication import (
    INITIAL_PUBLICATION_FINALIZATION_FIELDS,
    ExpectedPriorState,
    HashRuleBinding,
    IntegrityHash,
    PublicationPackage,
    publication_unit_knowledge_content_hash,
    publication_unit_representation_hash,
)


@dataclass(frozen=True, slots=True)
class PublicationRequest:
    publication_request_ref: str
    publication_package_version_ref: str
    publication_package_hash: str
    publication_change_set_ref: str
    publication_change_set_version_ref: str
    publication_change_set_hash: str
    publication_finalization_plan_ref: str
    publication_finalization_plan_hash: str
    publication_unit_ref: str
    knowledge_content_hash: IntegrityHash
    prepublication_representation_hash: IntegrityHash
    target_refs: tuple[str, ...]
    executor_ref: str
    publication_authority_ref: str
    policy_decision_ref: str
    review_record_refs: tuple[str, ...]
    conformance_report_refs: tuple[str, ...]
    g6_binding_refs: tuple[str, ...]
    idempotency_key: str
    requested_at: str
    request_fingerprint: str
    state: str = "ready_for_execution"
    contract_version: str = "0.1"

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "contract_name": "Publication Request Contract",
            "contract_version": self.contract_version,
            "publication_package_version_ref": self.publication_package_version_ref,
            "publication_package_hash": self.publication_package_hash,
            "publication_change_set_ref": self.publication_change_set_ref,
            "publication_change_set_version_ref": (
                self.publication_change_set_version_ref
            ),
            "publication_change_set_hash": self.publication_change_set_hash,
            "publication_finalization_plan_ref": (
                self.publication_finalization_plan_ref
            ),
            "publication_finalization_plan_hash": (
                self.publication_finalization_plan_hash
            ),
            "publication_unit_ref": self.publication_unit_ref,
            "knowledge_content_hash": self.knowledge_content_hash.to_dict(),
            "prepublication_representation_hash": (
                self.prepublication_representation_hash.to_dict()
            ),
            "target_refs": list(self.target_refs),
            "executor_ref": self.executor_ref,
            "publication_authority_ref": self.publication_authority_ref,
            "policy_decision_ref": self.policy_decision_ref,
            "review_record_refs": list(self.review_record_refs),
            "conformance_report_refs": list(self.conformance_report_refs),
            "g6_binding_refs": list(self.g6_binding_refs),
            "idempotency_key": self.idempotency_key,
            "requested_at": self.requested_at,
            "state": self.state,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "publication_request_ref": self.publication_request_ref,
            **self.fingerprint_payload(),
            "request_fingerprint": self.request_fingerprint,
        }


class PublicationRequestFactory:
    def create(
        self,
        *,
        package: PublicationPackage,
        g6_result: G6PublicationReadinessResult,
        policy_decision_ref: str,
        publication_review_record_ref: str,
        idempotency_key: str,
        requested_at: str,
    ) -> PublicationRequest:
        if (
            g6_result.disposition != "ready"
            or not g6_result.synthetic_test_only
            or g6_result.execution_performed
            or g6_result.publication_performed
            or g6_result.publication_record_created
        ):
            raise ValueError("g6_test_isolated_finalization_readiness_required")
        if not policy_decision_ref or not publication_review_record_ref:
            raise ValueError("publication_request_decision_context_missing")
        if not idempotency_key or not requested_at:
            raise ValueError("publication_request_provenance_missing")

        plan = package.publication_finalization_plan
        unit = package.publication_unit_binding
        review_refs = ordered_unique(
            (*package.candidate_review_record_refs, publication_review_record_ref)
        )
        values: dict[str, Any] = {
            "publication_package_version_ref": package.package_version_ref,
            "publication_package_hash": package.package_hash.value,
            "publication_change_set_ref": (
                package.change_set.publication_change_set_ref
            ),
            "publication_change_set_version_ref": (
                package.change_set.change_set_version_ref
            ),
            "publication_change_set_hash": package.change_set.change_set_hash.value,
            "publication_finalization_plan_ref": (
                plan.publication_finalization_plan_ref
            ),
            "publication_finalization_plan_hash": plan.plan_hash.value,
            "publication_unit_ref": unit.publication_unit_ref,
            "knowledge_content_hash": unit.content_hash,
            "prepublication_representation_hash": (
                unit.prepublication_representation_hash
            ),
            "target_refs": (plan.canonical_path, plan.maintenance_context_ref),
            "executor_ref": plan.executor_ref,
            "publication_authority_ref": plan.publication_authority_ref,
            "policy_decision_ref": policy_decision_ref,
            "review_record_refs": review_refs,
            "conformance_report_refs": package.conformance_report_refs,
            "g6_binding_refs": g6_result.binding_refs,
            "idempotency_key": idempotency_key,
            "requested_at": requested_at,
            "state": "ready_for_execution",
            "contract_version": "0.1",
        }
        temporary = PublicationRequest(
            publication_request_ref="pending",
            request_fingerprint="pending",
            **values,
        )
        fingerprint = content_hash(temporary.fingerprint_payload())
        return PublicationRequest(
            publication_request_ref=local_ref(
                "PRQ",
                {
                    "idempotency_key": idempotency_key,
                    "request_fingerprint": fingerprint,
                },
            ),
            request_fingerprint=fingerprint,
            **values,
        )


@dataclass(frozen=True, slots=True)
class MaterializedPublicationState:
    _manifest_json: str
    markdown_body: str

    @classmethod
    def create(
        cls,
        manifest: dict[str, Any],
        markdown_body: str,
    ) -> MaterializedPublicationState:
        return cls(
            _manifest_json=json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            markdown_body=markdown_body,
        )

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(self._manifest_json)


@dataclass(frozen=True, slots=True)
class FinalPublicationState:
    publication_unit_ref: str
    canonical_path: str
    publication_state: str
    publication_record_ref: str
    published_at: str
    publisher_ref: str
    predecessor_publication_ref: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "publication_unit_ref": self.publication_unit_ref,
            "canonical_path": self.canonical_path,
            "publication_state": self.publication_state,
            "publication_record_ref": self.publication_record_ref,
            "published_at": self.published_at,
            "publisher_ref": self.publisher_ref,
            "predecessor_publication_ref": self.predecessor_publication_ref,
        }


@dataclass(frozen=True, slots=True)
class PublicationRecord:
    publication_record_ref: str
    publication_request_ref: str
    publication_change_set_ref: str
    publication_finalization_plan_refs: tuple[str, ...]
    published_unit_refs: tuple[str, ...]
    target_refs: tuple[str, ...]
    previous_states: tuple[ExpectedPriorState, ...]
    new_states: tuple[FinalPublicationState, ...]
    executor_ref: str
    publication_authority_ref: str
    policy_decision_ref: str
    review_record_refs: tuple[str, ...]
    conformance_report_refs: tuple[str, ...]
    executed_at: str
    transaction_or_commit_ref: str
    knowledge_content_hashes: tuple[IntegrityHash, ...]
    final_representation_hashes: tuple[IntegrityHash, ...]
    outcome: str
    diagnostics: tuple[str, ...]
    compensation_refs: tuple[str, ...]
    immutable: bool = True
    contract_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Publication Record Contract",
            "contract_version": self.contract_version,
            "publication_record_ref": self.publication_record_ref,
            "publication_request_ref": self.publication_request_ref,
            "publication_change_set_ref": self.publication_change_set_ref,
            "publication_finalization_plan_refs": list(
                self.publication_finalization_plan_refs
            ),
            "published_unit_refs": list(self.published_unit_refs),
            "target_refs": list(self.target_refs),
            "previous_states": [item.to_dict() for item in self.previous_states],
            "new_states": [item.to_dict() for item in self.new_states],
            "executor_ref": self.executor_ref,
            "publication_authority_ref": self.publication_authority_ref,
            "policy_decision_ref": self.policy_decision_ref,
            "review_record_refs": list(self.review_record_refs),
            "conformance_report_refs": list(self.conformance_report_refs),
            "executed_at": self.executed_at,
            "transaction_or_commit_ref": self.transaction_or_commit_ref,
            "knowledge_content_hashes": [
                item.to_dict() for item in self.knowledge_content_hashes
            ],
            "final_representation_hashes": [
                item.to_dict() for item in self.final_representation_hashes
            ],
            "outcome": self.outcome,
            "diagnostics": list(self.diagnostics),
            "compensation_refs": list(self.compensation_refs),
            "immutable": self.immutable,
        }


@dataclass(frozen=True, slots=True)
class PublicationExecutionResult:
    disposition: Literal[
        "published",
        "idempotent_replay",
        "blocked",
        "compensated_failure",
        "fatal",
    ]
    reason_code: str
    record: PublicationRecord | None = None
    changed_fields: tuple[str, ...] = ()
    final_state_verified: bool = False
    change_set_applied: bool = False
    candidate_closed_after_publication: bool = False
    compensation_performed: bool = False
    test_isolated: bool = True


class TestIsolatedPublicationTarget:
    """In-memory staging target that cannot perform a canonical or Vault write."""

    __test__ = False

    def __init__(
        self,
        *,
        expected_prior_states: tuple[ExpectedPriorState, ...],
        target_ref: str = "synthetic-test-target",
        fault_mode: str | None = None,
    ) -> None:
        self.expected_prior_states = expected_prior_states
        self.target_ref = target_ref
        self.fault_mode = fault_mode
        self.test_isolated = True
        self.commit_count = 0
        self.compensation_count = 0
        self._states: dict[str, MaterializedPublicationState] = {}
        self._executions: dict[str, tuple[str, PublicationRecord]] = {}

    def lookup_execution(
        self,
        idempotency_key: str,
    ) -> tuple[str, PublicationRecord] | None:
        return self._executions.get(idempotency_key)

    def remember_execution(
        self,
        idempotency_key: str,
        request_fingerprint: str,
        record: PublicationRecord,
    ) -> None:
        self._executions[idempotency_key] = (request_fingerprint, record)

    def read(self, canonical_path: str) -> MaterializedPublicationState | None:
        state = self._states.get(canonical_path)
        if state is None:
            return None
        if self.fault_mode in {
            "tamper_postcommit_reread",
            "tamper_postcommit_reread_and_fail_compensation",
        }:
            manifest = state.manifest
            manifest["canonical_path"] = "tampered-after-commit"
            return MaterializedPublicationState.create(
                manifest,
                state.markdown_body,
            )
        return state

    def commit(
        self,
        canonical_path: str,
        state: MaterializedPublicationState,
        request_fingerprint: str,
    ) -> str:
        if canonical_path in self._states:
            raise ValueError("publication_target_already_materialized")
        self._states[canonical_path] = state
        self.commit_count += 1
        return local_ref(
            "TXN",
            {
                "target_ref": self.target_ref,
                "canonical_path": canonical_path,
                "request_fingerprint": request_fingerprint,
                "commit_count": self.commit_count,
            },
        )

    def compensate(
        self,
        canonical_path: str,
        previous_state: MaterializedPublicationState | None,
    ) -> bool:
        self.compensation_count += 1
        if self.fault_mode == "tamper_postcommit_reread_and_fail_compensation":
            return False
        if previous_state is None:
            self._states.pop(canonical_path, None)
        else:
            self._states[canonical_path] = previous_state
        return True


class PublicationExecutor:
    def execute(
        self,
        *,
        request: PublicationRequest,
        package: PublicationPackage,
        g6_result: G6PublicationReadinessResult,
        target: TestIsolatedPublicationTarget,
        executed_at: str,
    ) -> PublicationExecutionResult:
        if not target.test_isolated:
            return self._blocked("test_isolated_publication_target_required")
        if request.request_fingerprint != content_hash(
            request.fingerprint_payload()
        ):
            return self._blocked("publication_request_fingerprint_invalid")
        existing = target.lookup_execution(request.idempotency_key)
        if existing is not None:
            existing_fingerprint, existing_record = existing
            if existing_fingerprint != request.request_fingerprint:
                return self._blocked("idempotency_conflict")
            return PublicationExecutionResult(
                disposition="idempotent_replay",
                reason_code="publication_already_finalized",
                record=existing_record,
                changed_fields=package.publication_finalization_plan.allowed_finalization_fields,
                final_state_verified=True,
                change_set_applied=True,
                candidate_closed_after_publication=True,
            )
        if not executed_at:
            return self._blocked("publication_execution_time_missing")

        binding_failure = self._binding_failure(
            request=request,
            package=package,
            g6_result=g6_result,
            target=target,
        )
        if binding_failure:
            return self._blocked(binding_failure)

        unit = package.publication_unit_binding
        plan = package.publication_finalization_plan
        binding = self._hash_rule(unit.content_hash)
        actual_prepublication_hash = publication_unit_representation_hash(
            unit.manifest,
            unit.markdown_body,
            binding,
            scope="publication_unit_prepublication_representation",
        )
        if actual_prepublication_hash != unit.prepublication_representation_hash:
            return self._blocked("prepublication_representation_hash_mismatch")
        actual_knowledge_hash = publication_unit_knowledge_content_hash(
            unit.manifest,
            unit.markdown_body,
            binding,
        )
        if actual_knowledge_hash != unit.content_hash:
            return self._blocked("knowledge_content_hash_mismatch")

        final_manifest = deepcopy(unit.manifest)
        final_manifest["canonical_path"] = plan.canonical_path
        final_manifest["publication"].update(
            {
                "publication_state": "published",
                "publication_record_ref": plan.planned_publication_record_ref,
                "published_at": executed_at,
                "publisher_ref": plan.publisher_ref,
                "predecessor_publication_ref": plan.predecessor_publication_ref,
            }
        )
        final_body = self._finalize_publication_section(
            unit.markdown_body,
            anchor=plan.publication_anchor,
            publication_record_ref=plan.planned_publication_record_ref,
            published_at=executed_at,
            publisher_ref=plan.publisher_ref,
            canonical_path=plan.canonical_path,
        )
        final_knowledge_hash = publication_unit_knowledge_content_hash(
            final_manifest,
            final_body,
            binding,
        )
        if final_knowledge_hash != unit.content_hash:
            return self._blocked("knowledge_content_changed_during_finalization")
        final_representation_hash = publication_unit_representation_hash(
            final_manifest,
            final_body,
            binding,
            scope="publication_unit_final_representation",
        )
        staged = MaterializedPublicationState.create(final_manifest, final_body)
        previous_target_state = target.read(plan.canonical_path)
        if previous_target_state is not None:
            return self._blocked("publication_target_already_materialized")
        try:
            transaction_ref = target.commit(
                plan.canonical_path,
                staged,
                request.request_fingerprint,
            )
        except ValueError as exc:
            return self._blocked(str(exc))

        reread = target.read(plan.canonical_path)
        if not self._final_state_matches(
            reread,
            package=package,
            request=request,
            executed_at=executed_at,
            final_representation_hash=final_representation_hash,
            binding=binding,
        ):
            compensated = target.compensate(
                plan.canonical_path,
                previous_target_state,
            )
            if not compensated:
                return PublicationExecutionResult(
                    disposition="fatal",
                    reason_code="publication_partial_uncompensated",
                )
            return PublicationExecutionResult(
                disposition="compensated_failure",
                reason_code="final_state_verification_failed_compensated",
                compensation_performed=True,
            )

        record = PublicationRecord(
            publication_record_ref=plan.planned_publication_record_ref,
            publication_request_ref=request.publication_request_ref,
            publication_change_set_ref=package.change_set.publication_change_set_ref,
            publication_finalization_plan_refs=(
                plan.publication_finalization_plan_ref,
            ),
            published_unit_refs=(unit.publication_unit_ref,),
            target_refs=request.target_refs,
            previous_states=package.expected_prior_states,
            new_states=(
                FinalPublicationState(
                    publication_unit_ref=unit.publication_unit_ref,
                    canonical_path=plan.canonical_path,
                    publication_state="published",
                    publication_record_ref=plan.planned_publication_record_ref,
                    published_at=executed_at,
                    publisher_ref=plan.publisher_ref,
                    predecessor_publication_ref=plan.predecessor_publication_ref,
                ),
            ),
            executor_ref=plan.executor_ref,
            publication_authority_ref=plan.publication_authority_ref,
            policy_decision_ref=request.policy_decision_ref,
            review_record_refs=request.review_record_refs,
            conformance_report_refs=request.conformance_report_refs,
            executed_at=executed_at,
            transaction_or_commit_ref=transaction_ref,
            knowledge_content_hashes=(final_knowledge_hash,),
            final_representation_hashes=(final_representation_hash,),
            outcome="success",
            diagnostics=("all_publication_postconditions_verified",),
            compensation_refs=(),
        )
        target.remember_execution(
            request.idempotency_key,
            request.request_fingerprint,
            record,
        )
        return PublicationExecutionResult(
            disposition="published",
            reason_code="test_isolated_publication_finalized",
            record=record,
            changed_fields=plan.allowed_finalization_fields,
            final_state_verified=True,
            change_set_applied=True,
            candidate_closed_after_publication=True,
        )

    @staticmethod
    def _binding_failure(
        *,
        request: PublicationRequest,
        package: PublicationPackage,
        g6_result: G6PublicationReadinessResult,
        target: TestIsolatedPublicationTarget,
    ) -> str | None:
        plan = package.publication_finalization_plan
        unit = package.publication_unit_binding
        if (
            g6_result.disposition != "ready"
            or not g6_result.synthetic_test_only
            or request.g6_binding_refs != g6_result.binding_refs
        ):
            return "g6_publication_request_binding_mismatch"
        if (
            request.publication_package_version_ref != package.package_version_ref
            or request.publication_package_hash != package.package_hash.value
            or request.publication_change_set_ref
            != package.change_set.publication_change_set_ref
            or request.publication_change_set_version_ref
            != package.change_set.change_set_version_ref
            or request.publication_change_set_hash
            != package.change_set.change_set_hash.value
            or request.publication_finalization_plan_ref
            != plan.publication_finalization_plan_ref
            or request.publication_finalization_plan_hash != plan.plan_hash.value
            or request.publication_unit_ref != unit.publication_unit_ref
            or request.knowledge_content_hash != unit.content_hash
            or request.prepublication_representation_hash
            != unit.prepublication_representation_hash
        ):
            return "publication_request_package_binding_mismatch"
        expected_allowed_fields = (
            *INITIAL_PUBLICATION_FINALIZATION_FIELDS,
            f"markdown_section:{plan.publication_anchor}",
        )
        if plan.allowed_finalization_fields != expected_allowed_fields:
            return "publication_finalization_plan_integrity_invalid"
        if not plan.integrity_ok():
            return "publication_finalization_plan_integrity_invalid"
        if request.target_refs != (
            plan.canonical_path,
            plan.maintenance_context_ref,
        ) or target.target_ref != plan.maintenance_context_ref:
            return "publication_target_binding_mismatch"
        if (
            request.executor_ref != plan.executor_ref
            or request.publication_authority_ref != plan.publication_authority_ref
            or request.policy_decision_ref not in request.g6_binding_refs
            or not set(plan.review_record_refs).issubset(request.review_record_refs)
            or not set(package.conformance_report_refs).issubset(
                request.conformance_report_refs
            )
        ):
            return "publication_execution_context_mismatch"
        if target.expected_prior_states != package.expected_prior_states:
            return "expected_prior_state_mismatch"
        return None

    @staticmethod
    def _final_state_matches(
        state: MaterializedPublicationState | None,
        *,
        package: PublicationPackage,
        request: PublicationRequest,
        executed_at: str,
        final_representation_hash: IntegrityHash,
        binding: HashRuleBinding,
    ) -> bool:
        if state is None:
            return False
        plan = package.publication_finalization_plan
        unit = package.publication_unit_binding
        manifest = state.manifest
        publication = manifest.get("publication", {})
        if (
            manifest.get("knowledge_object_id") != plan.knowledge_object_id
            or manifest.get("knowledge_object_version")
            != plan.knowledge_object_version
            or manifest.get("canonical_path") != plan.canonical_path
            or publication.get("publication_state") != "published"
            or publication.get("publication_record_ref")
            != plan.planned_publication_record_ref
            or publication.get("published_at") != executed_at
            or publication.get("publisher_ref") != plan.publisher_ref
            or publication.get("predecessor_publication_ref")
            != plan.predecessor_publication_ref
        ):
            return False
        knowledge_hash = publication_unit_knowledge_content_hash(
            manifest,
            state.markdown_body,
            binding,
        )
        representation_hash = publication_unit_representation_hash(
            manifest,
            state.markdown_body,
            binding,
            scope="publication_unit_final_representation",
        )
        return bool(
            knowledge_hash == unit.content_hash
            and knowledge_hash == request.knowledge_content_hash
            and representation_hash == final_representation_hash
        )

    @staticmethod
    def _hash_rule(value: IntegrityHash) -> HashRuleBinding:
        return HashRuleBinding(
            algorithm=value.algorithm,
            canonicalization_profile_ref=value.canonicalization_profile,
            approval_context_ref=value.approval_context_ref,
            synthetic_test_fixture=value.synthetic_test_fixture,
        )

    @staticmethod
    def _finalize_publication_section(
        markdown_body: str,
        *,
        anchor: str,
        publication_record_ref: str,
        published_at: str,
        publisher_ref: str,
        canonical_path: str,
    ) -> str:
        marker = f'<a id="{anchor}"></a>'
        start = markdown_body.find(marker)
        if start < 0:
            raise ValueError("publication_anchor_missing")
        following = re.search(
            r'<a id="[^"]+"></a>',
            markdown_body[start + len(marker) :],
        )
        end = (
            start + len(marker) + following.start()
            if following is not None
            else len(markdown_body)
        )
        section = (
            f'{marker}\n## Review and publication\n\n'
            f"Published at `{published_at}` by `{publisher_ref}`.\n\n"
            f"Publication record: `{publication_record_ref}`.\n\n"
            f"Canonical path: `{canonical_path}`.\n"
        )
        prefix = markdown_body[:start].rstrip()
        suffix = markdown_body[end:].lstrip()
        return f"{prefix}\n\n{section}" + (f"\n{suffix}" if suffix else "")

    @staticmethod
    def _blocked(reason_code: str) -> PublicationExecutionResult:
        return PublicationExecutionResult(
            disposition="blocked",
            reason_code=reason_code,
        )
