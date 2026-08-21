from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from cp_knowledge_tools.platform.hashing import canonical_json_hash


@dataclass(frozen=True, slots=True)
class HumanSourceContext:
    source_role_context: str
    directness_context: str
    authority_context: str
    temporal_context: str
    perspective_context: str
    retrospective_recollection: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> HumanSourceContext:
        return cls(
            source_role_context=value.get("source_role_context", "unknown"),
            directness_context=value.get("directness_context", "unknown"),
            authority_context=value.get("authority_context", "unknown"),
            temporal_context=value.get("temporal_context", "unknown"),
            perspective_context=value.get("perspective_context", "unknown"),
            retrospective_recollection=(
                value.get("retrospective_recollection") is True
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HumanInteractionSourceRecord:
    human_interaction_source_record_ref: str
    human_source_ref: str
    interaction_ref: str
    human_enrichment_request_ref: str | None
    related_candidate_ref: str | None
    related_candidate_revision_ref: str | None
    related_experience_refs: tuple[str, ...]
    related_knowledge_refs: tuple[str, ...]
    knowledge_frontier_ref: str | None
    captured_during: str
    question_or_prompt_context: str
    response_content: str
    source_context: HumanSourceContext
    provided_at: str
    captured_at: str
    capture_provenance: tuple[str, ...]
    access_policy_refs: tuple[str, ...]
    processing_policy_refs: tuple[str, ...]
    content_hash: str
    evidence_address_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "human_interaction_source_record_ref": (
                self.human_interaction_source_record_ref
            ),
            "human_source_ref": self.human_source_ref,
            "interaction_ref": self.interaction_ref,
            "human_enrichment_request_ref": self.human_enrichment_request_ref,
            "related_candidate_ref": self.related_candidate_ref,
            "related_candidate_revision_ref": self.related_candidate_revision_ref,
            "related_experience_refs": list(self.related_experience_refs),
            "related_knowledge_refs": list(self.related_knowledge_refs),
            "knowledge_frontier_ref": self.knowledge_frontier_ref,
            "captured_during": self.captured_during,
            "question_or_prompt_context": self.question_or_prompt_context,
            "response_content": self.response_content,
            "source_context": self.source_context.to_dict(),
            "provided_at": self.provided_at,
            "captured_at": self.captured_at,
            "capture_provenance": list(self.capture_provenance),
            "access_policy_refs": list(self.access_policy_refs),
            "processing_policy_refs": list(self.processing_policy_refs),
            "content_hash": self.content_hash,
            "evidence_address_ref": self.evidence_address_ref,
        }


def capture_human_interaction_source(
    *,
    human_source_ref: str,
    interaction_ref: str,
    human_enrichment_request_ref: str | None,
    related_candidate_ref: str | None,
    related_candidate_revision_ref: str | None,
    related_experience_refs: Sequence[str],
    related_knowledge_refs: Sequence[str],
    knowledge_frontier_ref: str | None,
    captured_during: str,
    question_or_prompt_context: str,
    response_content: str,
    source_context: HumanSourceContext,
    provided_at: str,
    captured_at: str,
    capture_provenance: Sequence[str],
    access_policy_refs: Sequence[str],
    processing_policy_refs: Sequence[str],
) -> HumanInteractionSourceRecord:
    required = {
        "human_source_ref": human_source_ref,
        "interaction_ref": interaction_ref,
        "captured_during": captured_during,
        "question_or_prompt_context": question_or_prompt_context,
        "response_content": response_content,
        "provided_at": provided_at,
        "captured_at": captured_at,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f"Human Interaction Source missing fields: {missing}")
    if not access_policy_refs or not processing_policy_refs:
        raise ValueError("Human Interaction Source requires explicit Policy references")
    if not capture_provenance:
        raise ValueError("Human Interaction Source requires Capture Provenance")

    payload = {
        **required,
        "human_enrichment_request_ref": human_enrichment_request_ref,
        "related_candidate_ref": related_candidate_ref,
        "related_candidate_revision_ref": related_candidate_revision_ref,
        "related_experience_refs": list(related_experience_refs),
        "related_knowledge_refs": list(related_knowledge_refs),
        "knowledge_frontier_ref": knowledge_frontier_ref,
        "source_context": source_context.to_dict(),
        "capture_provenance": list(capture_provenance),
        "access_policy_refs": list(access_policy_refs),
        "processing_policy_refs": list(processing_policy_refs),
    }
    digest = canonical_json_hash(payload)
    return HumanInteractionSourceRecord(
        human_interaction_source_record_ref=f"HISR-{digest[:24].upper()}",
        human_source_ref=human_source_ref,
        interaction_ref=interaction_ref,
        human_enrichment_request_ref=human_enrichment_request_ref,
        related_candidate_ref=related_candidate_ref,
        related_candidate_revision_ref=related_candidate_revision_ref,
        related_experience_refs=tuple(related_experience_refs),
        related_knowledge_refs=tuple(related_knowledge_refs),
        knowledge_frontier_ref=knowledge_frontier_ref,
        captured_during=captured_during,
        question_or_prompt_context=question_or_prompt_context,
        response_content=response_content,
        source_context=source_context,
        provided_at=provided_at,
        captured_at=captured_at,
        capture_provenance=tuple(capture_provenance),
        access_policy_refs=tuple(access_policy_refs),
        processing_policy_refs=tuple(processing_policy_refs),
        content_hash=digest,
        evidence_address_ref=f"EA-HUM-{digest[:24].upper()}",
    )
