from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITY_RANK = {"fatal": 0, "error": 1, "warning": 2, "info": 3}


@dataclass(frozen=True)
class CoreDiagnostic:
    severity: str
    code: str
    path: str
    message: str
    validator_rule_ref: str
    rule_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_RANK:
            raise ValueError(f"unsupported diagnostic severity: {self.severity}")

    def sort_key(self) -> tuple[int, str, str, str]:
        return (SEVERITY_RANK[self.severity], self.code, self.path, self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "rule_ref": self.validator_rule_ref,
            "message": self.message,
            "validator_rule_ref": self.validator_rule_ref,
            "rule_sources": list(self.rule_sources),
        }


@dataclass
class RuleOutcome:
    diagnostics: list[CoreDiagnostic] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)


class CoreValidationInputError(ValueError):
    """Fail-closed error for invalid active Profile or Corpus inputs."""

    def __init__(self, code: str, message: str, path: str = "/") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path


@dataclass(frozen=True)
class PreparedCoreInputs:
    profile_manifest: dict[str, Any]
    corpus_manifest: dict[str, Any]
    corpus_payload: dict[str, Any]
    required_profile_manifests: tuple[dict[str, Any], ...]
    applicable_profile_manifests: tuple[dict[str, Any], ...]
    profile_hash: str
    corpus_hash: str
    required_profile_hashes: dict[str, str]
    applicable_profile_hashes: dict[str, str]

    @property
    def profile_payload(self) -> dict[str, Any]:
        return self.profile_manifest["payload"]
