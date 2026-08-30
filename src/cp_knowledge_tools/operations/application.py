"""Single application boundary used by all executable operation surfaces."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cp_knowledge_tools.derived.governance_state import GovernanceStateError
from cp_knowledge_tools.mcp.cp_wiki.governance import (
    ActiveArtifactNotFoundError,
    GovernanceResolutionError,
    MultipleActiveArtifactsError,
    read_active_artifact,
)
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault

from .context import build_operation_context, verify_execution_target
from .contracts import (
    AuthorityDecision,
    EnvironmentKind,
    OperationContext,
    OperationRequest,
    OperationResult,
    ResultDisposition,
    RunState,
    TargetKind,
    TechnicalRunEvidence,
    utc_now,
)
from .controller import InProcessRunController
from .evidence import TechnicalRunEvidenceWriter
from .governance.authority import (
    AuthorityEvidenceSource,
    AuthorityRequirement,
    CanonicalManagedAuthoritySource,
    RuntimeAuthorityResolver,
)
from .governance.lifecycle_profiles import (
    UnsupportedLifecycleProfileError,
    active_path_allowed,
    development_path_allowed,
    get_lifecycle_profile,
    history_path_allowed,
)
from .governance.managed_artifacts import (
    inspect_prepared_frontmatter,
    inspect_prepared_target,
)
from .governance.preflight import preflight_governance
from .governance.resolution import resolve_governance
from .registry import OperationRegistry, build_standard_registry
from .results import to_primitive
from .transactions.filesystem import FileTransactionEngine

_MANAGED_ARTIFACT_MUTATIONS = frozenset(
    {"artifact.revise", "artifact.activate", "artifact.transition"}
)
_MUTATION_SCOPE = {
    "artifact.revise": ("lifecycle_transition",),
    "artifact.activate": ("lifecycle_activation",),
    "artifact.transition": ("lifecycle_transition",),
}


class OperationApplication:
    def __init__(
        self,
        registry: OperationRegistry | None = None,
        *,
        authority_source_factory: Callable[[Path], AuthorityEvidenceSource]
        | None = None,
        owner_approval_source: AuthorityEvidenceSource | None = None,
        transaction_engine_factory: Callable[[Path, Path], FileTransactionEngine]
        | None = None,
        event_clock: Callable[[], str] = utc_now,
        authority_clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.registry = registry or build_standard_registry()
        self.authority_source_factory = (
            authority_source_factory or CanonicalManagedAuthoritySource
        )
        self.owner_approval_source = owner_approval_source
        self.transaction_engine_factory = (
            transaction_engine_factory or FileTransactionEngine
        )
        self.event_clock = event_clock
        self.authority_clock = authority_clock or (lambda: dt.datetime.now(dt.UTC))

    @staticmethod
    def _blocked(
        request: OperationRequest,
        message: str,
        *,
        disposition: ResultDisposition = ResultDisposition.BLOCKED,
        run_id: str | None = None,
    ) -> OperationResult:
        return OperationResult(
            operation_name=request.operation_name,
            operation_version=request.operation_version,
            disposition=disposition,
            run_id=run_id or f"run-{uuid.uuid4().hex}",
            correlation_id=request.correlation_id,
            message=message,
        )

    @staticmethod
    def _authority_evidence(
        decision: AuthorityDecision | None, operation_id: str
    ) -> dict[str, Any]:
        if decision is None:
            return {"disposition": "not_applicable"}
        contract = decision.runtime_contract
        return {
            "contract_id": contract.contract_id if contract else None,
            "contract_fingerprint": contract.fingerprint if contract else None,
            "authority_ref": decision.authority_ref,
            "authority_version": decision.authority_version,
            "authority_class": (
                decision.authority_class.value if decision.authority_class else None
            ),
            "issuer": decision.issuer,
            "operation_id": operation_id,
            "targets": list(decision.targets),
            "environment": (
                {
                    "kind": contract.environment.kind.value,
                    "identity": contract.environment.identity,
                }
                if contract
                else None
            ),
            "disposition": decision.disposition.value,
            "checks": list(decision.checks),
            "reasons": list(decision.reasons),
        }

    @staticmethod
    def _target_version(
        request: OperationRequest, parameters: Mapping[str, Any], vault: Vault
    ) -> tuple[str, str, dict[str, Any]]:
        if request.operation_name == "artifact.activate":
            prepared_path = vault.resolve_path(str(parameters["draft_path"]))
        elif (
            request.operation_name == "artifact.transition"
            and parameters.get("completion_evidence_file")
        ):
            resolution, document = read_active_artifact(vault, request.targets[0])
            return (
                resolution.version,
                resolution.document_type,
                dict(document.frontmatter),
            )
        else:
            prepared_path = Path(str(parameters["prepared_file"]))
        stable_id, version, document_type = inspect_prepared_target(prepared_path)
        if stable_id != request.targets[0]:
            raise ValueError("prepared target stable ID does not match request target")
        return version, document_type, inspect_prepared_frontmatter(prepared_path)

    @staticmethod
    def _resolve_rule_homes(
        vault: Vault, document_type: str
    ) -> tuple[dict[str, str], dict[str, bool]]:
        versions: dict[str, str] = {}
        integrity: dict[str, bool] = {}
        for stable_id in get_lifecycle_profile(document_type).rule_homes:
            resolution, _ = read_active_artifact(vault, stable_id)
            versions[stable_id] = resolution.version
            integrity[stable_id] = resolution.integrity_ok
        return versions, integrity

    def _execute_managed_artifact_mutation(
        self,
        request: OperationRequest,
        registered: Any,
        parameters: dict[str, Any],
        controller: InProcessRunController,
    ) -> tuple[OperationResult, OperationContext | None, AuthorityDecision | None]:
        try:
            vault_root = Path(str(parameters["vault_root"]))
            run_root = Path(str(parameters["run_root"]))
            execution_target = verify_execution_target(
                vault_root,
                target_kind=TargetKind.CP_WIKI,
                environment_kind=EnvironmentKind.LOCAL_VAULT,
                classification=str(parameters.get("target_classification", "other")),
            )
            engine = self.transaction_engine_factory(execution_target.root, run_root)
            key = request.idempotency_key or request.fingerprint
            replay = engine.idempotency_disposition(key, request.fingerprint)
            if replay is not None:
                return (
                    self._blocked(
                        request,
                        "idempotent replay"
                        if replay is ResultDisposition.IDEMPOTENT_REPLAY
                        else "idempotency key conflict",
                        disposition=replay,
                    ),
                    None,
                    None,
                )
            vault = Vault(execution_target.root)
            target_version, document_type, prepared_frontmatter = self._target_version(
                request, parameters, vault
            )
            try:
                current_state = resolve_governance(vault, request.targets[0])
            except ActiveArtifactNotFoundError:
                if request.operation_name != "artifact.activate":
                    raise
                current_state = {
                    "stable_id": request.targets[0],
                    "version": None,
                    "status": "absent",
                    "document_type": document_type,
                    "relative_path": None,
                    "current_state_fingerprint": None,
                }
            rule_versions, rule_integrity = self._resolve_rule_homes(
                vault, document_type
            )
        except UnsupportedLifecycleProfileError as exc:
            return (
                self._blocked(
                    request,
                    str(exc),
                    disposition=ResultDisposition.UNSUPPORTED,
                ),
                None,
                None,
            )
        except MultipleActiveArtifactsError as exc:
            return (
                self._blocked(
                    request, str(exc), disposition=ResultDisposition.CONFLICT
                ),
                None,
                None,
            )
        except (KeyError, OSError, ValueError, GovernanceResolutionError) as exc:
            return self._blocked(request, str(exc)), None, None

        raw_contract = parameters.get("runtime_authority")
        contract_value = raw_contract if isinstance(raw_contract, Mapping) else None
        resolver = RuntimeAuthorityResolver(
            self.authority_source_factory(execution_target.root),
            owner_approval_source=self.owner_approval_source,
            known_operations=self.registry.operation_ids(),
            clock=self.authority_clock,
        )
        authority = resolver.resolve(
            authority_ref=request.authority_ref,
            contract_value=contract_value,
            requirement=AuthorityRequirement(
                operation_id=request.operation_name,
                target_stable_id=request.targets[0],
                target_version=target_version,
                artifact_class=document_type,
                target_kind=execution_target.target_kind,
                document_type=document_type,
                mutation_scope=_MUTATION_SCOPE[request.operation_name],
                environment_kind=execution_target.environment_kind,
                environment_identity=execution_target.environment_identity,
                activate=request.operation_name == "artifact.activate",
            ),
        )
        context = build_operation_context(
            request,
            target_system="cp-wiki",
            vault_root=execution_target.root,
            repo_root=(
                Path(str(parameters["repo_root"]))
                if parameters.get("repo_root")
                else None
            ),
            run_root=run_root,
            actual_current_state=current_state,
            active_rule_homes=rule_versions,
            rule_home_integrity=rule_integrity,
            authority_decision=authority,
            execution_target=execution_target,
            expected_source_fingerprints={
                **(
                    {
                        current_state["relative_path"]: current_state[
                            "current_state_fingerprint"
                        ]
                    }
                    if current_state.get("relative_path")
                    else {}
                )
            },
            mutation_class=_MUTATION_SCOPE[request.operation_name][0],
            document_type=document_type,
            identity_field=get_lifecycle_profile(document_type).identity_field,
            lifecycle_profile=document_type,
            stable_id=request.targets[0],
            target_version=target_version,
        )
        controller.transition(RunState.CONTEXT_RESOLVED)
        profile = get_lifecycle_profile(document_type)
        if request.operation_name == "artifact.revise":
            preflight_path_allowed = development_path_allowed(
                profile,
                str(parameters["target_path"]),
                prepared_frontmatter,
            )
        elif request.operation_name == "artifact.activate":
            preflight_path_allowed = development_path_allowed(
                profile,
                str(parameters["draft_path"]),
                prepared_frontmatter,
            ) and (
                not parameters.get("active_path")
                or active_path_allowed(
                    profile,
                    str(parameters["active_path"]),
                    prepared_frontmatter,
                )
            )
        else:
            preflight_path_allowed = history_path_allowed(
                profile,
                str(parameters["archive_path"]),
                prepared_frontmatter,
                active_path=current_state.get("relative_path"),
            )
        try:
            preflight = preflight_governance(
                vault_root=execution_target.root,
                stable_id=request.targets[0],
                target_version=target_version,
                authority=authority,
                operation_id=request.operation_name,
                document_type=document_type,
                path_allowed=preflight_path_allowed,
            )
        except GovernanceStateError as exc:
            return (
                self._blocked(
                    request,
                    str(exc),
                    disposition=ResultDisposition.CONFLICT,
                    run_id=context.run_id,
                ),
                context,
                authority,
            )
        except (OSError, ValueError, GovernanceResolutionError) as exc:
            return (
                self._blocked(request, str(exc), run_id=context.run_id),
                context,
                authority,
            )
        if preflight.unsupported_reasons or not preflight.lifecycle_allowed:
            return (
                self._blocked(
                    request,
                    "; ".join(preflight.unsupported_reasons)
                    or "preflight did not permit the lifecycle transition",
                    disposition=preflight.disposition,
                    run_id=context.run_id,
                ),
                context,
                authority,
            )
        controller.transition(RunState.PREFLIGHT_PASSED)
        handler_parameters = {
            **parameters,
            "_operation_context": context,
            "_authority_decision": authority,
            "_run_controller": controller,
            "_transaction_engine": engine,
        }
        result = registered.handler(request, **handler_parameters)
        if not isinstance(result, OperationResult):
            raise TypeError("operation handler returned an invalid result")
        result.outputs.update(
            {
                "operation_context": to_primitive(context),
                "preflight": to_primitive(preflight),
                "run_state_history": [state.value for state in controller.history],
                "run_state_events": list(controller.events),
            }
        )
        return result, context, authority

    def execute(self, request: OperationRequest, **kwargs: Any) -> OperationResult:
        started_at = self.event_clock()
        controller = InProcessRunController(clock=self.event_clock)
        registered = self.registry.resolve(
            request.operation_name, request.operation_version
        )
        if request.requested_mode not in registered.spec.supported_modes:
            raise ValueError(
                f"mode {request.requested_mode!r} is not supported by "
                f"{request.operation_name}"
            )
        parameters = {**request.parameters, **kwargs}
        context: OperationContext | None = None
        authority: AuthorityDecision | None = None
        if request.operation_name in _MANAGED_ARTIFACT_MUTATIONS:
            result, context, authority = self._execute_managed_artifact_mutation(
                request, registered, parameters, controller
            )
        else:
            result = registered.handler(request, **parameters)
            if not isinstance(result, OperationResult):
                raise TypeError("operation handler returned an invalid result")

        completed_at = self.event_clock()
        run_root_value = parameters.get("run_root")
        if request.requested_mode == "apply" and run_root_value:
            versions = {
                "contract": "0.1",
                "schema": "0.1",
                "profile": context.lifecycle_profile if context else "not_applicable",
                "tool": "0.1.0",
                "code": "working-tree",
            }
            if context is not None:
                versions.update(
                    {
                        f"rule:{key}": value
                        for key, value in context.active_rule_homes.items()
                    }
                )
            evidence = TechnicalRunEvidence.create(
                started_at=started_at,
                completed_at=completed_at,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                operation_name=result.operation_name,
                operation_version=result.operation_version,
                scope=registered.spec.supported_scope,
                authority_context=self._authority_evidence(
                    authority, request.operation_name
                ),
                versions=versions,
                inputs={"parameters": request.parameters},
                fingerprints={
                    "request": request.fingerprint,
                    **(
                        context.expected_source_fingerprints
                        if context is not None
                        else {}
                    ),
                },
                plan_ref=result.outputs.get("plan_id"),
                preview_ref=result.outputs.get("preview_ref"),
                actual_mutations=result.actual_mutations,
                validation_results=result.validation_results,
                postconditions=(
                    result.postcondition_report.results
                    if result.postcondition_report is not None
                    else ()
                ),
                outputs={
                    **result.outputs,
                    "recovery_record": (
                        to_primitive(result.recovery_record)
                        if result.recovery_record is not None
                        else None
                    ),
                },
                disposition=result.disposition,
                compensation_status=result.compensation_status,
                recovery_status=(
                    "recovery_required"
                    if result.recovery_record is not None
                    else "none"
                ),
            )
            try:
                path = TechnicalRunEvidenceWriter(Path(str(run_root_value))).write(
                    evidence
                )
            except (OSError, TypeError, ValueError) as exc:
                result.outputs.update(
                    {
                        "technical_run_evidence": None,
                        "technical_run_evidence_status": (
                            "persistence_failed_after_operation"
                        ),
                        "technical_run_evidence_error": {
                            "type": type(exc).__name__,
                            "message": (
                                "technical run evidence could not be persisted "
                                "after the operation result"
                            ),
                        },
                        "operation_result_preserved": True,
                        "retry_operation_required": False,
                    }
                )
            else:
                result.outputs["technical_run_evidence"] = str(path)
                result.outputs["technical_run_evidence_status"] = "persisted"
        return result
