"""Fail-closed runtime-authority resolution for K1 mutation operations."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from cp_knowledge_tools.mcp.cp_wiki.governance import (
    ActiveArtifactNotFoundError,
    ArtifactIntegrityError,
    GovernanceResolutionError,
    inspect_artifact_line,
    read_active_artifact,
)
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault
from cp_knowledge_tools.platform.hashing import sha256_text
from cp_knowledge_tools.validation.temporal import (
    parse_lifecycle_temporal,
    parse_technical_timestamp,
)

from ..contracts import (
    AuthorityClass,
    AuthorityDecision,
    AuthorityDisposition,
    EnvironmentKind,
    RuntimeAuthorityContract,
    RuntimeAuthorityTarget,
    TargetKind,
)

_DOCUMENT_TYPE_TO_AUTHORITY_CLASS = {
    "work_package": AuthorityClass.WORK_PACKAGE,
    "decision_record": AuthorityClass.DECISION_RECORD,
    "process": AuthorityClass.PROCESS,
}


class AuthoritySourceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AuthoritySourceRecord:
    authority_ref: str
    version: str
    authority_class: AuthorityClass
    issuer: str
    source_path: str
    source_fingerprint: str
    effective_from: Any
    grants: tuple[RuntimeAuthorityContract, ...]
    approval_verified: bool = False


class AuthorityEvidenceSource(Protocol):
    """Trusted adapter that resolves authority independently of caller claims."""

    def resolve(self, authority_ref: str) -> AuthoritySourceRecord: ...


def _split_authority_ref(value: str) -> tuple[str, str | None]:
    if "@" not in value:
        return value, None
    stable_id, version = value.rsplit("@", 1)
    return stable_id, version


def _contract_values(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        return tuple(value)
    return ()


class CanonicalManagedAuthoritySource:
    """Resolve managed authority bases through the existing active resolver."""

    def __init__(self, vault_root: Path) -> None:
        self.vault = Vault(vault_root)

    def resolve(self, authority_ref: str) -> AuthoritySourceRecord:
        stable_id, bound_version = _split_authority_ref(authority_ref)
        try:
            resolution, document = read_active_artifact(self.vault, stable_id)
        except ActiveArtifactNotFoundError as exc:
            records = inspect_artifact_line(self.vault, stable_id)
            code = "authority_not_active" if records else "authority_not_found"
            raise AuthoritySourceError(code, str(exc)) from exc
        except ArtifactIntegrityError as exc:
            raise AuthoritySourceError("authority_integrity_invalid", str(exc)) from exc
        except GovernanceResolutionError as exc:
            raise AuthoritySourceError(
                "authority_resolution_conflict", str(exc)
            ) from exc

        authority_class = _DOCUMENT_TYPE_TO_AUTHORITY_CLASS.get(
            resolution.document_type
        )
        if authority_class is None:
            raise AuthoritySourceError(
                "authority_class_not_permitted",
                f"{resolution.document_type} is a constraint source, "
                "not mutation authority",
            )
        if bound_version is not None and bound_version != resolution.version:
            raise AuthoritySourceError(
                "authority_version_mismatch",
                f"authority requires {bound_version}, active version is "
                f"{resolution.version}",
            )

        frontmatter = document.frontmatter
        issuer = frontmatter.get("owner")
        if not isinstance(issuer, str) or not issuer.strip():
            raise AuthoritySourceError(
                "authority_issuer_unresolved", "authority issuer is not resolvable"
            )
        effective_from = parse_lifecycle_temporal(frontmatter.get("effective_from"))
        if effective_from is None:
            raise AuthoritySourceError(
                "authority_effectivity_invalid",
                "authority effective_from is missing or invalid",
            )

        raw_grants = frontmatter.get(
            "runtime_authority_contracts", frontmatter.get("runtime_authority")
        )
        try:
            grants = tuple(
                RuntimeAuthorityContract.from_mapping(item)
                for item in _contract_values(raw_grants)
            )
        except (TypeError, ValueError) as exc:
            raise AuthoritySourceError(
                "authority_contract_invalid",
                f"canonical authority contract invalid: {exc}",
            ) from exc
        if not grants:
            raise AuthoritySourceError(
                "authority_scope_unavailable",
                "canonical authority does not expose structured runtime scope",
            )

        expected_authority = (
            resolution.stable_id,
            resolution.version,
            authority_class,
            issuer.strip(),
        )
        if any(
            (
                grant.authority.ref,
                grant.authority.version,
                grant.authority.authority_class,
                grant.authority.issuer,
            )
            != expected_authority
            for grant in grants
        ):
            raise AuthoritySourceError(
                "authority_contract_source_mismatch",
                "canonical runtime contract does not match its authority source",
            )

        raw = self.vault.read_markdown(resolution.relative_path)
        approval_verified = all(
            not grant.approval.required
            or (
                grant.approval.approved_by == frontmatter.get("approved_by")
                and grant.approval.approved_at == frontmatter.get("approved_at")
                and grant.approval.evidence_ref
                in {
                    f"{resolution.stable_id}@{resolution.version}",
                    resolution.relative_path,
                }
            )
            for grant in grants
        )
        return AuthoritySourceRecord(
            authority_ref=resolution.stable_id,
            version=resolution.version,
            authority_class=authority_class,
            issuer=issuer.strip(),
            source_path=resolution.relative_path,
            source_fingerprint=sha256_text(raw),
            effective_from=effective_from,
            grants=grants,
            approval_verified=approval_verified,
        )


@dataclass(frozen=True, slots=True)
class AuthorityRequirement:
    operation_id: str
    target_stable_id: str
    target_version: str | None
    artifact_class: str
    target_kind: TargetKind
    document_type: str
    mutation_scope: tuple[str, ...]
    environment_kind: EnvironmentKind
    environment_identity: str
    activate: bool
    remote_effects: bool = False


def _target_within(
    requested: RuntimeAuthorityTarget, granted: RuntimeAuthorityTarget
) -> bool:
    return (
        requested.stable_id == granted.stable_id
        and requested.artifact_class == granted.artifact_class
        and requested.target_kind is granted.target_kind
        and (
            requested.version == granted.version
            or (granted.version is None and requested.version is not None)
        )
    )


def _instant(value: str | None) -> dt.datetime | None:
    return parse_technical_timestamp(value) if value is not None else None


def _contract_within(
    requested: RuntimeAuthorityContract, granted: RuntimeAuthorityContract
) -> bool:
    requested_effective = _instant(requested.validity.effective_from)
    granted_effective = _instant(granted.validity.effective_from)
    requested_expires = _instant(requested.validity.expires_at)
    granted_expires = _instant(granted.validity.expires_at)
    if requested_effective is None or granted_effective is None:
        return False
    return (
        requested.authority == granted.authority
        and set(requested.operations) <= set(granted.operations)
        and all(
            any(
                _target_within(target, grant_target) for grant_target in granted.targets
            )
            for target in requested.targets
        )
        and set(requested.scope.document_types) <= set(granted.scope.document_types)
        and set(requested.scope.mutation_scope) <= set(granted.scope.mutation_scope)
        and requested.environment == granted.environment
        and (not requested.effects.mutate or granted.effects.mutate)
        and (not requested.effects.activate or granted.effects.activate)
        and (not requested.effects.remote_effects or granted.effects.remote_effects)
        and requested_effective >= granted_effective
        and (
            granted_expires is None
            or (requested_expires is not None and requested_expires <= granted_expires)
        )
        and (not granted.approval.required or requested.approval == granted.approval)
    )


class RuntimeAuthorityResolver:
    def __init__(
        self,
        source: AuthorityEvidenceSource,
        *,
        owner_approval_source: AuthorityEvidenceSource | None = None,
        known_operations: Sequence[str] = (),
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.source = source
        self.owner_approval_source = owner_approval_source
        self.known_operations = frozenset(known_operations)
        self.clock = clock or (lambda: dt.datetime.now(dt.UTC))

    @staticmethod
    def _blocked(
        authority_ref: str | None,
        targets: tuple[str, ...],
        code: str,
        message: str,
        checks: list[dict[str, Any]] | None = None,
    ) -> AuthorityDecision:
        return AuthorityDecision(
            disposition=AuthorityDisposition.BLOCKED,
            authority_ref=authority_ref,
            targets=targets,
            checks=tuple(checks or ())
            + ({"code": code, "passed": False, "message": message},),
            reasons=(message,),
        )

    def resolve(
        self,
        *,
        authority_ref: str | None,
        contract_value: Mapping[str, Any] | None,
        requirement: AuthorityRequirement,
    ) -> AuthorityDecision:
        targets = (requirement.target_stable_id,)
        if not authority_ref:
            return self._blocked(
                authority_ref,
                targets,
                "authority_ref_missing",
                "authority_ref is required for mutation",
            )
        try:
            requested = (
                RuntimeAuthorityContract.from_mapping(contract_value)
                if contract_value is not None
                else None
            )
        except (TypeError, ValueError) as exc:
            return self._blocked(
                authority_ref, targets, "authority_contract_invalid", str(exc)
            )

        ref_stable_id, ref_version = _split_authority_ref(authority_ref)
        requested_class = (
            requested.authority.authority_class if requested is not None else None
        )
        selected_source = self.source
        if requested_class is AuthorityClass.OWNER_APPROVAL:
            if self.owner_approval_source is None:
                return self._blocked(
                    authority_ref,
                    targets,
                    "owner_approval_unverifiable",
                    "no trusted owner-approval evidence source is configured",
                )
            selected_source = self.owner_approval_source
        try:
            source = selected_source.resolve(authority_ref)
        except AuthoritySourceError as exc:
            return self._blocked(authority_ref, targets, exc.code, str(exc))

        checks: list[dict[str, Any]] = []

        def check(code: str, passed: bool, message: str) -> bool:
            checks.append({"code": code, "passed": passed, "message": message})
            return passed

        if not check(
            "authority_reference_resolved",
            source.authority_ref == ref_stable_id,
            "authority reference resolved from trusted source",
        ):
            return self._blocked(
                authority_ref,
                targets,
                "authority_ref_mismatch",
                "authority reference mismatch",
                checks,
            )
        if not check(
            "authority_version_matches",
            ref_version is None or ref_version == source.version,
            "authority version matches the resolved source",
        ):
            return self._blocked(
                authority_ref,
                targets,
                "authority_version_mismatch",
                "authority version mismatch",
                checks,
            )
        if requested is not None and (
            requested.authority.ref != source.authority_ref
            or requested.authority.version != source.version
        ):
            return self._blocked(
                authority_ref,
                targets,
                "contract_authority_mismatch",
                "contract authority does not match the resolved source",
                checks,
            )
        if (
            requested is not None
            and requested.authority.authority_class is not source.authority_class
        ):
            return self._blocked(
                authority_ref,
                targets,
                "authority_class_mismatch",
                "contract authority class does not match source",
                checks,
            )
        if requested is not None and requested.authority.issuer != source.issuer:
            return self._blocked(
                authority_ref,
                targets,
                "authority_issuer_mismatch",
                "contract issuer does not match source",
                checks,
            )

        candidates = (
            tuple(
                grant for grant in source.grants if _contract_within(requested, grant)
            )
            if requested is not None
            else source.grants
        )
        if len(candidates) != 1:
            return self._blocked(
                authority_ref,
                targets,
                "authority_contract_not_uniquely_verified",
                "runtime contract is not uniquely covered by canonical authority",
                checks,
            )
        contract = requested or candidates[0]
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            return self._blocked(
                authority_ref,
                targets,
                "runtime_clock_invalid",
                "runtime clock must be timezone-aware",
                checks,
            )
        effective = _instant(contract.validity.effective_from)
        expires = _instant(contract.validity.expires_at)
        if effective is None or (contract.validity.expires_at and expires is None):
            return self._blocked(
                authority_ref,
                targets,
                "authority_validity_invalid",
                "authority validity timestamps are invalid",
                checks,
            )
        source_is_effective = (
            now >= source.effective_from.instant
            if source.effective_from.instant is not None
            else now.date() >= source.effective_from.calendar_date
        )

        expected_target = RuntimeAuthorityTarget(
            stable_id=requirement.target_stable_id,
            version=requirement.target_version,
            artifact_class=requirement.artifact_class,
            target_kind=requirement.target_kind,
        )
        requirements = (
            (
                "operation_registered",
                not self.known_operations
                or requirement.operation_id in self.known_operations,
                "operation is registered",
            ),
            (
                "operation_exact",
                set(contract.operations) == {requirement.operation_id},
                "exact operation ID is authorized",
            ),
            (
                "target_exact",
                contract.targets == (expected_target,),
                "exact target and target version are authorized",
            ),
            (
                "document_type_scope",
                set(contract.scope.document_types) == {requirement.document_type},
                "document type is authorized",
            ),
            (
                "mutation_scope",
                set(requirement.mutation_scope)
                == set(contract.scope.mutation_scope),
                "mutation scope is authorized",
            ),
            (
                "environment_kind",
                requirement.environment_kind is contract.environment.kind,
                "environment kind matches",
            ),
            (
                "environment_identity",
                requirement.environment_identity == contract.environment.identity,
                "environment identity matches",
            ),
            ("effect_mutate", contract.effects.mutate, "mutation effect is authorized"),
            (
                "effect_activate",
                requirement.activate == contract.effects.activate,
                "activation effect is explicitly authorized",
            ),
            (
                "remote_effects",
                requirement.remote_effects == contract.effects.remote_effects,
                "remote-effect boundary matches",
            ),
            (
                "authority_source_effective",
                source_is_effective,
                "canonical authority source is effective",
            ),
            (
                "validity_effective",
                effective is not None and now >= effective,
                "runtime authority is effective",
            ),
            (
                "validity_not_expired",
                expires is None or now <= expires,
                "runtime authority is not expired",
            ),
            (
                "approval_evidence",
                not contract.approval.required or source.approval_verified,
                "required approval evidence is verified",
            ),
        )
        for code, passed, message in requirements:
            if not check(code, passed, message):
                return self._blocked(authority_ref, targets, code, message, checks)

        return AuthorityDecision(
            disposition=AuthorityDisposition.AUTHORIZED,
            authority_ref=source.authority_ref,
            authority_version=source.version,
            authority_class=source.authority_class,
            issuer=source.issuer,
            runtime_contract=contract,
            source_path=source.source_path,
            source_fingerprint=source.source_fingerprint,
            targets=targets,
            checks=tuple(checks),
        )
