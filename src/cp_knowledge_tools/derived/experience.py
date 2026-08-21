from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from cp_knowledge_tools.lifecycle import (
    HashRuleBinding,
    PublicationRecord,
    publication_unit_knowledge_content_hash,
)
from cp_knowledge_tools.platform.hashing import canonical_json_hash

ExperienceSubjectType = Literal["claim", "event", "event_participation"]
ExperiencePhaseStatus = Literal["supported", "partial", "unresolved"]
ExperienceGapStatus = Literal[
    "unresolved",
    "resolved",
    "informed_unresolved",
]


class ExperienceProjectionError(ValueError):
    """Raised when a projection plan cannot be applied without ambiguity."""


@dataclass(frozen=True, slots=True)
class ExperienceSemanticSelector:
    """Source-neutral requirement over semantic state in a Publication Unit."""

    subject_type: ExperienceSubjectType
    stable_id: str | None = None
    claim_predicate_ref: str | None = None
    claim_object_value: str | int | float | bool | None = None
    event_type_ref: str | None = None
    participation_role: str | None = None
    time_modality: str | None = None
    requires_evidence: bool = True


@dataclass(frozen=True, slots=True)
class ExperiencePhasePlan:
    phase_ref: str
    requirements: tuple[ExperienceSemanticSelector, ...]
    required_for_lesson_learned: bool = False
    status_when_supported: Literal["supported", "partial"] = "supported"


@dataclass(frozen=True, slots=True)
class ExperienceThreadPlan:
    thread_ref: str
    semantic_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperienceGapPlan:
    gap_ref: str
    question: str
    phase_ref: str
    semantic_basis_refs: tuple[str, ...] = ()
    progression_requirements: tuple[ExperienceSemanticSelector, ...] = ()
    status_when_progressed: Literal[
        "resolved",
        "informed_unresolved",
    ] | None = None


@dataclass(frozen=True, slots=True)
class ExperienceReuseContext:
    domain_terms: tuple[str, ...] = ()
    topic_terms: tuple[str, ...] = ()
    purpose_terms: tuple[str, ...] = ()

    def normalized(self) -> ExperienceReuseContext:
        return ExperienceReuseContext(
            domain_terms=tuple(dict.fromkeys(self.domain_terms)),
            topic_terms=tuple(dict.fromkeys(self.topic_terms)),
            purpose_terms=tuple(dict.fromkeys(self.purpose_terms)),
        )

    @property
    def all_terms(self) -> frozenset[str]:
        return frozenset(
            (*self.domain_terms, *self.topic_terms, *self.purpose_terms)
        )


@dataclass(frozen=True, slots=True)
class ExperienceContinuationPlan:
    continuation_ref: str
    critical_gap_refs: tuple[str, ...]
    search_after: str
    trigger_purposes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperienceProjectionPlan:
    experience_ref: str
    focus_knowledge_object_ref: str
    as_of: str
    phases: tuple[ExperiencePhasePlan, ...]
    threads: tuple[ExperienceThreadPlan, ...]
    gaps: tuple[ExperienceGapPlan, ...]
    reuse_context: ExperienceReuseContext
    continuation: ExperienceContinuationPlan | None = None


@dataclass(frozen=True, slots=True)
class ExperiencePhase:
    phase_ref: str
    status: ExperiencePhaseStatus
    semantic_basis_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    required_for_lesson_learned: bool


@dataclass(frozen=True, slots=True)
class ExperienceThread:
    thread_ref: str
    semantic_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperienceGap:
    gap_ref: str
    question: str
    status: ExperienceGapStatus
    phase_ref: str
    semantic_basis_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperienceContinuationRequirement:
    continuation_ref: str
    experience_ref: str
    status: Literal["required_for_reusable_experience"]
    critical_gap_refs: tuple[str, ...]
    search_after: str
    trigger_purposes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperienceProjection:
    experience_projection_ref: str
    semantic_hash: str
    projection_schema_version: str
    builder_version: str
    experience_ref: str
    focus_knowledge_object_ref: str
    publication_unit_ref: dict[str, str]
    as_of: str
    experience_completeness: Literal["complete", "partial", "unresolved"]
    phases: tuple[ExperiencePhase, ...]
    threads: tuple[ExperienceThread, ...]
    gaps: tuple[ExperienceGap, ...]
    reuse_context: ExperienceReuseContext
    continuation_requirements: tuple[ExperienceContinuationRequirement, ...]
    lesson_learned_eligibility: Literal["eligible", "insufficient_evidence"]
    lesson_learned_candidates: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def semantic_signature(self) -> str:
        return self.semantic_hash


class ExperienceProjectionBuilder:
    """Build a deterministic non-authoritative experience view from a PU."""

    projection_schema_version = "0.2"
    builder_version = "0.2"

    def build(
        self,
        manifest: Mapping[str, Any],
        plan: ExperienceProjectionPlan,
    ) -> ExperienceProjection:
        publication_ref = self._publication_ref(manifest)
        expected_focus = (
            f"{publication_ref['stable_id']}@{publication_ref['version']}"
        )
        if plan.focus_knowledge_object_ref != expected_focus:
            raise ExperienceProjectionError(
                "plan focus does not match the Publication Unit: "
                f"{plan.focus_knowledge_object_ref!r} != {expected_focus!r}"
            )

        subjects = self._subject_index(manifest)
        evidence_by_subject = self._evidence_by_subject(manifest)
        phase_refs = [item.phase_ref for item in plan.phases]
        if len(phase_refs) != len(set(phase_refs)):
            raise ExperienceProjectionError("phase references must be unique")

        phases = tuple(
            self._phase(item, subjects, evidence_by_subject)
            for item in plan.phases
        )
        phase_by_ref = {item.phase_ref: item for item in phases}
        threads = tuple(
            self._thread(item, subjects) for item in plan.threads
        )
        gaps = tuple(
            self._gap(item, phase_by_ref, subjects, evidence_by_subject)
            for item in plan.gaps
        )

        if phases and all(item.status == "supported" for item in phases):
            completeness = "complete"
        elif any(item.status != "unresolved" for item in phases):
            completeness = "partial"
        else:
            completeness = "unresolved"

        required_outcomes = tuple(
            item for item in phases if item.required_for_lesson_learned
        )
        lesson_eligibility = (
            "eligible"
            if required_outcomes
            and all(item.status == "supported" for item in required_outcomes)
            else "insufficient_evidence"
        )
        continuation_requirements = self._continuations(
            plan,
            gaps,
        )
        reuse_context = plan.reuse_context.normalized()
        payload = {
            "projection_schema_version": self.projection_schema_version,
            "builder_version": self.builder_version,
            "experience_ref": plan.experience_ref,
            "focus_knowledge_object_ref": plan.focus_knowledge_object_ref,
            "publication_unit_ref": publication_ref,
            "as_of": plan.as_of,
            "experience_completeness": completeness,
            "phases": [asdict(item) for item in phases],
            "threads": [asdict(item) for item in threads],
            "gaps": [asdict(item) for item in gaps],
            "reuse_context": asdict(reuse_context),
            "continuation_requirements": [
                asdict(item) for item in continuation_requirements
            ],
            "lesson_learned_eligibility": lesson_eligibility,
            "lesson_learned_candidates": [],
        }
        semantic_hash = canonical_json_hash(payload)
        return ExperienceProjection(
            experience_projection_ref=(
                f"EXPP-{semantic_hash[:24].upper()}"
            ),
            semantic_hash=semantic_hash,
            projection_schema_version=self.projection_schema_version,
            builder_version=self.builder_version,
            experience_ref=plan.experience_ref,
            focus_knowledge_object_ref=plan.focus_knowledge_object_ref,
            publication_unit_ref=publication_ref,
            as_of=plan.as_of,
            experience_completeness=completeness,
            phases=phases,
            threads=threads,
            gaps=gaps,
            reuse_context=reuse_context,
            continuation_requirements=continuation_requirements,
            lesson_learned_eligibility=lesson_eligibility,
        )

    def write(self, projection: ExperienceProjection, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                projection.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def _publication_ref(self, manifest: Mapping[str, Any]) -> dict[str, str]:
        return {
            "subject_type": "knowledge_object",
            "stable_id": str(manifest["knowledge_object_id"]),
            "version": str(manifest["knowledge_object_version"]),
            "authority_context": "Semantic Core",
        }

    def _subject_index(
        self,
        manifest: Mapping[str, Any],
    ) -> dict[str, tuple[dict[str, Any], ...]]:
        collections = {
            "claim": ("claims", "claim_ref"),
            "event": ("events", "event_ref"),
            "event_participation": (
                "event_participations",
                "participation_ref",
            ),
        }
        return {
            subject_type: tuple(
                sorted(
                    (deepcopy(item) for item in manifest.get(key, ())),
                    key=lambda item: item[ref_key]["stable_id"],
                )
            )
            for subject_type, (key, ref_key) in collections.items()
        }

    def _evidence_by_subject(
        self,
        manifest: Mapping[str, Any],
    ) -> dict[str, tuple[str, ...]]:
        refs: dict[str, set[str]] = {}
        for link in manifest.get("evidence_links", ()):
            subject_ref = link["subject_ref"]["stable_id"]
            evidence_ref = link["evidence_address_ref"]["stable_id"]
            refs.setdefault(subject_ref, set()).add(evidence_ref)
        return {key: tuple(sorted(value)) for key, value in refs.items()}

    def _phase(
        self,
        plan: ExperiencePhasePlan,
        subjects: Mapping[str, Sequence[dict[str, Any]]],
        evidence_by_subject: Mapping[str, tuple[str, ...]],
    ) -> ExperiencePhase:
        matches = [
            self._matches(selector, subjects)
            for selector in plan.requirements
        ]
        requirement_supported = [
            bool(items)
            and (
                not selector.requires_evidence
                or any(
                    evidence_by_subject.get(
                        self._stable_id(selector.subject_type, item), ()
                    )
                    for item in items
                )
            )
            for selector, items in zip(plan.requirements, matches, strict=True)
        ]
        supported = bool(plan.requirements) and all(requirement_supported)
        semantic_refs = tuple(
            sorted(
                {
                    self._stable_id(selector.subject_type, item)
                    for selector, items in zip(
                        plan.requirements, matches, strict=True
                    )
                    for item in items
                }
            )
        )
        evidence_refs = tuple(
            sorted(
                {
                    ref
                    for subject_ref in semantic_refs
                    for ref in evidence_by_subject.get(subject_ref, ())
                }
            )
        )
        return ExperiencePhase(
            phase_ref=plan.phase_ref,
            status=plan.status_when_supported if supported else "unresolved",
            semantic_basis_refs=semantic_refs,
            evidence_refs=evidence_refs,
            required_for_lesson_learned=plan.required_for_lesson_learned,
        )

    def _matches(
        self,
        selector: ExperienceSemanticSelector,
        subjects: Mapping[str, Sequence[dict[str, Any]]],
    ) -> tuple[dict[str, Any], ...]:
        events = {
            item["event_ref"]["stable_id"]: item
            for item in subjects["event"]
        }
        matches = []
        for item in subjects[selector.subject_type]:
            stable_id = self._stable_id(selector.subject_type, item)
            if selector.stable_id is not None and stable_id != selector.stable_id:
                continue
            if selector.subject_type == "claim":
                statement = item["statement"]
                if (
                    selector.claim_predicate_ref is not None
                    and statement["predicate_ref"]
                    != selector.claim_predicate_ref
                ):
                    continue
                if (
                    selector.claim_object_value is not None
                    and self._claim_object_value(statement["object"])
                    != selector.claim_object_value
                ):
                    continue
            event = item
            if selector.subject_type == "event_participation":
                if (
                    selector.participation_role is not None
                    and item["role"] != selector.participation_role
                ):
                    continue
                event = events.get(item["event_ref"]["stable_id"], {})
            if selector.event_type_ref is not None and (
                event.get("event_type_ref") != selector.event_type_ref
            ):
                continue
            if selector.time_modality is not None and not any(
                value.get("modality") == selector.time_modality
                for value in event.get("time", item.get("time", ()))
            ):
                continue
            matches.append(item)
        return tuple(matches)

    def _thread(
        self,
        plan: ExperienceThreadPlan,
        subjects: Mapping[str, Sequence[dict[str, Any]]],
    ) -> ExperienceThread:
        known_refs = {
            self._stable_id(subject_type, item)
            for subject_type, items in subjects.items()
            for item in items
        }
        unknown_refs = set(plan.semantic_refs) - known_refs
        if unknown_refs:
            raise ExperienceProjectionError(
                f"thread {plan.thread_ref!r} has unknown semantic refs: "
                f"{sorted(unknown_refs)}"
            )
        return ExperienceThread(plan.thread_ref, plan.semantic_refs)

    def _gap(
        self,
        plan: ExperienceGapPlan,
        phases: Mapping[str, ExperiencePhase],
        subjects: Mapping[str, Sequence[dict[str, Any]]],
        evidence_by_subject: Mapping[str, tuple[str, ...]],
    ) -> ExperienceGap:
        if plan.phase_ref not in phases:
            raise ExperienceProjectionError(
                f"gap {plan.gap_ref!r} references unknown phase "
                f"{plan.phase_ref!r}"
            )
        if bool(plan.progression_requirements) != bool(
            plan.status_when_progressed
        ):
            raise ExperienceProjectionError(
                f"gap {plan.gap_ref!r} must define progression requirements "
                "and progressed status together"
            )
        known_refs = {
            self._stable_id(subject_type, item)
            for subject_type, items in subjects.items()
            for item in items
        }
        unknown_refs = set(plan.semantic_basis_refs) - known_refs
        if unknown_refs:
            raise ExperienceProjectionError(
                f"gap {plan.gap_ref!r} has unknown semantic basis refs: "
                f"{sorted(unknown_refs)}"
            )
        phase = phases[plan.phase_ref]
        progression_matches = tuple(
            self._matches(selector, subjects)
            for selector in plan.progression_requirements
        )
        progression_supported = bool(plan.progression_requirements) and all(
            items
            and (
                not selector.requires_evidence
                or any(
                    evidence_by_subject.get(
                        self._stable_id(selector.subject_type, item),
                        (),
                    )
                    for item in items
                )
            )
            for selector, items in zip(
                plan.progression_requirements,
                progression_matches,
                strict=True,
            )
        )
        progression_refs = {
            self._stable_id(selector.subject_type, item)
            for selector, items in zip(
                plan.progression_requirements,
                progression_matches,
                strict=True,
            )
            for item in items
        }
        basis_refs = tuple(
            sorted(
                set(
                    (
                        *plan.semantic_basis_refs,
                        *phase.semantic_basis_refs,
                        *progression_refs,
                    )
                )
            )
        )
        return ExperienceGap(
            gap_ref=plan.gap_ref,
            question=plan.question,
            status=(
                plan.status_when_progressed
                if progression_supported
                and plan.status_when_progressed is not None
                else "unresolved"
            ),
            phase_ref=plan.phase_ref,
            semantic_basis_refs=basis_refs,
        )

    def _continuations(
        self,
        plan: ExperienceProjectionPlan,
        gaps: tuple[ExperienceGap, ...],
    ) -> tuple[ExperienceContinuationRequirement, ...]:
        if plan.continuation is None:
            return ()
        open_gap_refs = {
            item.gap_ref for item in gaps if item.status != "resolved"
        }
        critical_gap_refs = tuple(
            ref
            for ref in plan.continuation.critical_gap_refs
            if ref in open_gap_refs
        )
        if not critical_gap_refs:
            return ()
        return (
            ExperienceContinuationRequirement(
                continuation_ref=plan.continuation.continuation_ref,
                experience_ref=plan.experience_ref,
                status="required_for_reusable_experience",
                critical_gap_refs=critical_gap_refs,
                search_after=plan.continuation.search_after,
                trigger_purposes=tuple(
                    dict.fromkeys(plan.continuation.trigger_purposes)
                ),
            ),
        )

    def _stable_id(
        self,
        subject_type: str,
        item: Mapping[str, Any],
    ) -> str:
        ref_key = {
            "claim": "claim_ref",
            "event": "event_ref",
            "event_participation": "participation_ref",
        }[subject_type]
        return str(item[ref_key]["stable_id"])

    def _claim_object_value(self, value: Mapping[str, Any]) -> Any:
        if value["kind"] == "reference":
            return value["reference"]["stable_id"]
        return value["value"]


@dataclass(frozen=True, slots=True)
class ExperienceRebuildResult:
    disposition: Literal["rebuilt", "blocked"]
    reason_code: str
    projection: ExperienceProjection | None = None
    stale_projection_refs: tuple[str, ...] = ()
    publication_record_ref: str | None = None
    source_publication_unit_ref: str | None = None


class ExperienceProjectionStore:
    """Small rebuildable store; its projections are never canonical sources."""

    def __init__(
        self,
        projections: Sequence[ExperienceProjection] = (),
    ) -> None:
        self._projections = {
            item.experience_projection_ref: item for item in projections
        }
        self._statuses = {
            item.experience_projection_ref: "current" for item in projections
        }

    def projections(self) -> tuple[ExperienceProjection, ...]:
        return tuple(
            self._projections[key] for key in sorted(self._projections)
        )

    def status(self, projection_ref: str) -> str | None:
        return self._statuses.get(projection_ref)

    def delete(self, projection_ref: str) -> bool:
        if projection_ref not in self._projections:
            return False
        del self._projections[projection_ref]
        del self._statuses[projection_ref]
        return True

    def mark_prior_versions_stale(
        self,
        *,
        stable_id: str,
        current_version: str,
    ) -> tuple[str, ...]:
        stale_refs = []
        for projection_ref, projection in self._projections.items():
            publication_ref = projection.publication_unit_ref
            if (
                publication_ref["stable_id"] == stable_id
                and publication_ref["version"] != current_version
                and self._statuses[projection_ref] == "current"
            ):
                self._statuses[projection_ref] = "stale"
                stale_refs.append(projection_ref)
        return tuple(sorted(stale_refs))

    def put_current(self, projection: ExperienceProjection) -> None:
        self._projections[projection.experience_projection_ref] = projection
        self._statuses[projection.experience_projection_ref] = "current"


class PublicationBoundExperienceRebuilder:
    """Rebuild Derived Experience only from a verified published unit."""

    def rebuild(
        self,
        *,
        manifest: Mapping[str, Any],
        markdown_body: str,
        plan: ExperienceProjectionPlan,
        publication_record: PublicationRecord,
        store: ExperienceProjectionStore,
    ) -> ExperienceRebuildResult:
        if publication_record.outcome != "success" or not publication_record.immutable:
            return self._blocked("successful_publication_record_required")

        stable_id = str(manifest.get("knowledge_object_id", ""))
        version = str(manifest.get("knowledge_object_version", ""))
        publication_unit_ref = f"{stable_id}@{version}"
        publication = manifest.get("publication", {})
        if (
            not stable_id
            or not version
            or publication_unit_ref not in publication_record.published_unit_refs
        ):
            return self._blocked("publication_record_unit_binding_mismatch")
        if (
            publication.get("publication_state") != "published"
            or publication.get("publication_record_ref")
            != publication_record.publication_record_ref
        ):
            return self._blocked("published_unit_state_not_verified")
        if not publication_record.knowledge_content_hashes:
            return self._blocked("publication_record_knowledge_hash_missing")
        declared_hash = manifest.get("integrity", {}).get("content_hash")
        record_hash = publication_record.knowledge_content_hashes[0]
        hash_binding = HashRuleBinding(
            algorithm=record_hash.algorithm,
            canonicalization_profile_ref=record_hash.canonicalization_profile,
            approval_context_ref=record_hash.approval_context_ref,
            synthetic_test_fixture=record_hash.synthetic_test_fixture,
        )
        actual_hash = publication_unit_knowledge_content_hash(
            dict(manifest),
            markdown_body,
            hash_binding,
        )
        if (
            not isinstance(declared_hash, Mapping)
            or declared_hash.get("value") != record_hash.value
            or actual_hash != record_hash
        ):
            return self._blocked("publication_record_knowledge_hash_mismatch")
        if plan.focus_knowledge_object_ref != publication_unit_ref:
            return self._blocked("experience_plan_published_unit_mismatch")

        projection = ExperienceProjectionBuilder().build(manifest, plan)
        stale_refs = store.mark_prior_versions_stale(
            stable_id=stable_id,
            current_version=version,
        )
        store.put_current(projection)
        return ExperienceRebuildResult(
            disposition="rebuilt",
            reason_code="experience_rebuilt_from_published_unit",
            projection=projection,
            stale_projection_refs=stale_refs,
            publication_record_ref=publication_record.publication_record_ref,
            source_publication_unit_ref=publication_unit_ref,
        )

    @staticmethod
    def _blocked(reason_code: str) -> ExperienceRebuildResult:
        return ExperienceRebuildResult(
            disposition="blocked",
            reason_code=reason_code,
        )
