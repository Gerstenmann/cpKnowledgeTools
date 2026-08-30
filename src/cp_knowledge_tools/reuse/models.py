"""Runtime-neutral technical records, not policy or authorization sources."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from cp_knowledge_tools.operations.results import to_primitive


class ReuseError(ValueError):
    """A precondition failed before target mutation."""


class ReuseDisposition(StrEnum):
    USE = "USE"
    WRAP = "WRAP"
    ADAPT = "ADAPT"
    LEARN = "LEARN"
    BUILD = "BUILD"
    REJECT = "REJECT"


class DependencyAcceptanceState(StrEnum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_CONDITIONS = "accepted_with_conditions"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class LicenseState(StrEnum):
    UNKNOWN = "unknown"
    DECLARED = "declared"
    CONFLICTING = "conflicting"


class Phase(StrEnum):
    RESEARCH = "RESEARCH"
    EVALUATE = "EVALUATE"
    DECIDE = "DECIDE"
    DESIGN = "DESIGN"
    IMPLEMENT = "IMPLEMENT"


class VulnerabilityState(StrEnum):
    NOT_CHECKED = "not_checked"
    UNKNOWN = "unknown"
    CHECKED = "checked"
    FINDINGS_PRESENT = "findings_present"


@dataclass(frozen=True)
class CapabilityNeed:
    description: str
    search_terms: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.description.strip():
            raise ReuseError("capability need must be explicit")
        if len(self.search_terms) > 20 or any(
            not t.strip() or len(t) > 120 for t in self.search_terms
        ):
            raise ReuseError("search terms must be bounded nonempty literals")


@dataclass(frozen=True)
class ResearchQuestion:
    question: str
    exclusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchGateResult:
    status: str
    rationale: str
    internal_inspection_fingerprint: str


@dataclass(frozen=True)
class CandidateSource:
    kind: str
    location: str
    expected_commit: str | None = None

    def __post_init__(self):
        if self.kind == "https":
            try:
                parsed = urlsplit(self.location)
                valid = (
                    parsed.scheme == "https"
                    and parsed.hostname
                    and parsed.path not in {"", "/"}
                    and parsed.username is None
                    and parsed.password is None
                    and not parsed.query
                    and not parsed.fragment
                    and parsed.port in {None, 443}
                )
            except ValueError:
                valid = False
            if not valid or re.search(r"[\s\\%]", self.location):
                raise ReuseError("only credential-free HTTPS Git URLs are supported")
        elif self.kind == "local":
            if not Path(self.location).is_absolute():
                raise ReuseError("local repository must be an absolute path")
        else:
            raise ReuseError("unsupported candidate source")
        if self.expected_commit is not None and not re.fullmatch(
            r"[0-9a-f]{40}|[0-9a-f]{64}", self.expected_commit
        ):
            raise ReuseError("expected commit must be a complete object ID")

    @classmethod
    def local(cls, path: Path, expected_commit: str | None = None):
        return cls("local", str(path.absolute()), expected_commit)

    @classmethod
    def https(cls, url: str, expected_commit: str | None = None):
        return cls("https", url, expected_commit)


@dataclass(frozen=True)
class InspectionLimits:
    max_files: int = 3000
    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 30_000_000
    max_depth: int = 25
    max_hits: int = 20_000

    def __post_init__(self):
        if (
            min(
                self.max_files,
                self.max_file_bytes,
                self.max_total_bytes,
                self.max_depth,
                self.max_hits,
            )
            < 1
        ):
            raise ReuseError("inspection limits must be positive")


@dataclass(frozen=True)
class CandidateSnapshot:
    candidate_id: str
    source: CandidateSource
    root: Path
    commit: str
    fingerprint: str
    file_fingerprints: tuple[tuple[str, str], ...]
    dirty: bool
    diagnostics: tuple[str, ...] = ()
    limits: InspectionLimits = InspectionLimits()


@dataclass(frozen=True)
class CandidateEvidence:
    kind: str
    path: str
    value: str
    line: int | None = None
    heuristic: bool = False


@dataclass(frozen=True)
class Symbol:
    path: str
    symbol: str
    kind: str
    line: int


@dataclass(frozen=True)
class CandidateFacts:
    snapshot: CandidateSnapshot
    files: tuple[str, ...]
    source_files: tuple[str, ...]
    test_files: tuple[str, ...]
    documentation_files: tuple[str, ...]
    manifests: tuple[str, ...]
    license_files: tuple[str, ...]
    notice_files: tuple[str, ...]
    declared_licenses: tuple[str, ...]
    license_state: LicenseState
    direct_dependencies: tuple[str, ...]
    locked_dependencies: tuple[str, ...]
    build_system: tuple[str, ...]
    evidence: tuple[CandidateEvidence, ...]
    symbols: tuple[Symbol, ...]
    diagnostics: tuple[str, ...]
    vulnerability_state: VulnerabilityState = VulnerabilityState.NOT_CHECKED


@dataclass(frozen=True)
class InternalInspection:
    repository: str
    need: CapabilityNeed
    fingerprint: str
    files: tuple[str, ...]
    matches: tuple[CandidateEvidence, ...]
    symbols: tuple[Symbol, ...]
    manifests: tuple[str, ...]
    direct_dependencies: tuple[str, ...]
    tests: tuple[str, ...]
    diagnostics: tuple[str, ...]


COMPARISON_DIMENSIONS = (
    "functional_fit",
    "architectural_fit",
    "api_integration_fit",
    "complexity",
    "maturity",
    "maintenance",
    "dependencies",
    "license",
    "provenance",
    "security",
    "testability",
    "rebuildability",
    "lock_in_exit",
    "integration_cost",
    "maintenance_cost",
    "productization_impact",
)


@dataclass(frozen=True)
class CandidateComparison:
    candidate_id: str
    dimensions: tuple[tuple[str, str], ...]
    evidence_refs: tuple[str, ...] = ()
    hard_constraint_findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateAssessment:
    assessment_id: str
    candidate_id: str
    snapshot_fingerprint: str
    disposition: ReuseDisposition
    acceptance: DependencyAcceptanceState
    rationale: str
    license_expression: str = ""
    license_resolved: bool = False
    license_finding: str = ""
    license_evidence_paths: tuple[str, ...] = ()
    security_finding: str = ""
    policy_refs: tuple[str, ...] = ()
    decision_ref: str = ""
    conditions: tuple[str, ...] = ()
    unresolved_conditions: tuple[str, ...] = ()
    hard_blocks: tuple[str, ...] = ()
    architectural_fit: str = "not assessed"
    maintenance_finding: str = "not assessed"
    dependency_finding: str = "not assessed"


@dataclass(frozen=True)
class ReuseAssessment:
    assessment_id: str
    capability_need: CapabilityNeed
    research_question: ResearchQuestion
    research_gate: ResearchGateResult
    internal_inspection: InternalInspection
    candidates: tuple[CandidateFacts, ...]
    comparison: tuple[CandidateComparison, ...]
    decisions: tuple[CandidateAssessment, ...]
    overall_strategy: ReuseDisposition
    decision_rationale: str
    internal_alternative: str
    build_alternative: str
    representative_set_rationale: str
    common_patterns: tuple[str, ...] = ()
    reusable_components: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    open_questions_or_blocks: tuple[str, ...] = ()
    governance_refs: tuple[str, ...] = ()
    schema_version: str = "0.1"


@dataclass(frozen=True)
class AdoptionPlan:
    assessment_id: str
    candidate_id: str
    upstream_project: str
    upstream_repository: str
    upstream_commit_or_snapshot: str
    source_file_or_unit: str
    source_fingerprint: str
    license_expression_or_license_state: str
    notice_or_attribution_requirements: tuple[tuple[str, str], ...]
    target_repository: str
    target_repository_id: str
    target_path: str
    reuse_disposition: ReuseDisposition
    planned_modification: str
    provenance_output: str
    snapshot: CandidateSnapshot
    decision_fingerprint: str
    content_base64: str
    expected_target_fingerprint: str | None
    target_identity: tuple[int, int]
    diff: str
    plan_fingerprint: str = ""
    schema_version: str = "0.1"


@dataclass(frozen=True)
class CopiedCodeProvenance:
    assessment_id: str
    candidate_id: str
    upstream_project: str
    upstream_repository: str
    upstream_commit_or_snapshot: str
    snapshot_fingerprint: str
    source_file_or_unit: str
    source_fingerprint: str
    original_source_base64: str
    license_expression: str
    license_evidence: tuple[CandidateEvidence, ...]
    retained_notices: tuple[tuple[str, str], ...]
    target_repository: str
    target_path: str
    target_fingerprint: str
    reuse_disposition: ReuseDisposition
    local_modifications: str
    decision_ref: str
    authority_ref: str
    authority_source_fingerprint: str
    applied_at: str
    schema_version: str = "0.1"


@dataclass(frozen=True)
class ApplyResult:
    status: str
    changed_paths: tuple[str, ...]
    provenance: CopiedCodeProvenance | None
    message: str


@dataclass(frozen=True)
class IntegrationHandover:
    assessment_id: str
    candidate_id: str
    disposition: ReuseDisposition
    source: CandidateSource
    commit: str
    integration_boundary: str
    dependency_specification: str
    verification_steps: tuple[str, ...]
    environment_preflight_required: bool = True


def to_json(value: object) -> str:
    return json.dumps(
        to_primitive(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
