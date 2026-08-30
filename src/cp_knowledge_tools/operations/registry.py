"""Typed standard-operation registry without governance authority."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass

from .contracts import OperationClass, OperationSpec
from .governance.lifecycle_profiles import supported_document_types

OperationHandler = Callable[..., object]


@dataclass(frozen=True, slots=True)
class RegisteredOperation:
    spec: OperationSpec
    handler: OperationHandler


class OperationRegistry:
    def __init__(self) -> None:
        self._operations: dict[tuple[str, str], RegisteredOperation] = {}

    @staticmethod
    def _load_handler(reference: str) -> OperationHandler:
        try:
            module_name, attribute = reference.split(":", 1)
            module = importlib.import_module(module_name)
            handler = getattr(module, attribute)
        except (ImportError, AttributeError, ValueError) as exc:
            raise ValueError(
                f"operation handler is not importable: {reference}"
            ) from exc
        if not callable(handler):
            raise ValueError(f"operation handler is not callable: {reference}")
        return handler

    def register(self, spec: OperationSpec) -> None:
        if spec.operation_class is OperationClass.EXTERNAL_EFFECT:
            raise ValueError("EXTERNAL_EFFECT is outside the K0/K1 registry")
        key = (spec.operation_id, spec.operation_version)
        if key in self._operations:
            raise ValueError(f"operation already registered: {spec.operation_id}")
        self._operations[key] = RegisteredOperation(
            spec=spec,
            handler=self._load_handler(spec.handler_ref),
        )

    def resolve(self, operation_id: str, version: str = "0.1") -> RegisteredOperation:
        try:
            return self._operations[(operation_id, version)]
        except KeyError as exc:
            raise KeyError(f"unsupported operation: {operation_id}@{version}") from exc

    def operation_ids(self) -> tuple[str, ...]:
        return tuple(sorted(operation_id for operation_id, _ in self._operations))

    def list_specs(self) -> tuple[OperationSpec, ...]:
        return tuple(self._operations[key].spec for key in sorted(self._operations))


def _spec(
    operation_id: str,
    operation_class: OperationClass,
    modes: tuple[str, ...],
    handler_ref: str,
    *,
    required_inputs: tuple[str, ...],
    surfaces: dict[str, str],
    supported_scope: dict[str, object] | None = None,
    unsupported_scope: tuple[str, ...] | None = None,
) -> OperationSpec:
    mutation = operation_id.startswith("artifact.")
    return OperationSpec(
        operation_id=operation_id,
        operation_version="0.1",
        operation_class=operation_class,
        supported_modes=modes,
        target_classes=("managed_artifact",) if mutation else ("governance",),
        required_inputs=required_inputs,
        supported_scope=dict(supported_scope or {}),
        unsupported_scope=unsupported_scope
        or (
            ("coupled multi-artifact activation", "external effects")
            if mutation
            else ("external effects",)
        ),
        surface_mappings=surfaces,
        handler_ref=handler_ref,
    )


def build_standard_registry() -> OperationRegistry:
    registry = OperationRegistry()
    specs = (
        _spec(
            "governance.resolve",
            OperationClass.QUERY,
            ("check",),
            "cp_knowledge_tools.operations.governance.resolution:resolve_operation",
            required_inputs=("vault_root", "stable_id"),
            surfaces={"cli": "cpks governance resolve"},
        ),
        _spec(
            "governance.preflight",
            OperationClass.PLAN,
            ("check",),
            "cp_knowledge_tools.operations.governance.preflight:preflight_operation",
            required_inputs=("vault_root", "stable_id"),
            surfaces={"cli": "cpks governance preflight"},
        ),
        _spec(
            "artifact.revise",
            OperationClass.MUTATE_LOCAL,
            ("check", "apply"),
            "cp_knowledge_tools.operations.governance.managed_artifacts:revise_operation",
            required_inputs=("vault_root", "prepared_file", "target_path"),
            surfaces={"cli": "cpks artifact revise"},
            supported_scope={
                "document_types": list(supported_document_types("artifact.revise"))
            },
            unsupported_scope=(
                "work_package revise",
                "baseline revise",
                "coupled process packages",
                "external effects",
            ),
        ),
        _spec(
            "artifact.transition",
            OperationClass.MUTATE_LOCAL,
            ("check", "apply"),
            "cp_knowledge_tools.operations.governance.managed_artifacts:transition_operation",
            required_inputs=(
                "transition_profile",
                "vault_root",
                "prepared_file_or_completion_evidence",
                "archive_path",
            ),
            surfaces={
                "internal": "artifact lifecycle profile core",
                "cli": "cpks work-package complete",
            },
            supported_scope={
                "document_types": list(
                    supported_document_types("artifact.transition")
                ),
                "transition_profiles": ["work_package.complete"],
            },
            unsupported_scope=(
                "work_package create/revise/activate",
                "free lifecycle transitions",
                "external effects",
            ),
        ),
        _spec(
            "artifact.activate",
            OperationClass.MUTATE_LOCAL,
            ("check", "apply"),
            "cp_knowledge_tools.operations.governance.managed_artifacts:activate_operation",
            required_inputs=(
                "vault_root",
                "stable_id",
                "draft_path",
                "approved_by",
                "approved_at",
                "effective_from",
            ),
            surfaces={"cli": "cpks artifact activate"},
            supported_scope={
                "document_types": list(
                    supported_document_types("artifact.activate")
                ),
                "activation_modes": ["initial", "follow_up"],
                "activation_body_modes": [
                    "draft_body",
                    "owner_prepared_activation_target",
                ],
            },
            unsupported_scope=(
                "work_package activation",
                "baseline activation",
                "coupled process packages",
                "external effects",
            ),
        ),
        _spec(
            "derived.governance.refresh",
            OperationClass.DERIVE,
            ("check", "apply"),
            "cp_knowledge_tools.operations.derived:refresh_operation",
            required_inputs=("vault_root", "run_root"),
            surfaces={"cli": "cpks derived governance refresh"},
        ),
        _spec(
            "incident.capture",
            OperationClass.MUTATE_LOCAL,
            ("check", "apply"),
            "cp_knowledge_tools.operations.incidents:capture_operation",
            required_inputs=("repo_root", "failure_phase", "mutation_state"),
            surfaces={"cli": "cpks incident capture"},
        ),
    )
    for spec in specs:
        registry.register(spec)
    return registry
