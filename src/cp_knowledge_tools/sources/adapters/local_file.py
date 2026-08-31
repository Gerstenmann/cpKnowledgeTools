"""Shared local capture and independent consumer Policy gate.

Format adapters implement only the trusted integrity check; neither capture nor
an evidence address grants consumer access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from cp_knowledge_tools.platform.hashing import (
    canonical_json_hash,
    sha256_bytes,
    stable_token,
)
from cp_knowledge_tools.policy import (
    PolicyDecision,
    PolicyDecisionValidator,
    PolicyEvaluationInput,
)
from cp_knowledge_tools.sources.models import (
    CapturedSource,
    Coverage,
    EvidenceAddress,
    Fingerprint,
    RawContentReference,
    ResolutionResult,
    SourceRecord,
    SourceSnapshot,
)


class LocalFileAdapter(ABC):
    media_type: str

    @abstractmethod
    def resolve(self, captured: CapturedSource, address: EvidenceAddress) -> bool:
        """Verify integrity after the shared consumer gate; never grant access."""

    def capture(
        self,
        source_key: str,
        path: Path,
        *,
        captured_at: str | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
        policy_refs: tuple[str, ...] = (),
    ) -> CapturedSource:
        # Adapter input uses a caller's stable registration key, never the locator.
        if not source_key.strip() or Path(source_key).is_absolute():
            raise ValueError("stable source key required; locator is not identity")
        raw = path.read_bytes()
        captured_at = captured_at or datetime.now().astimezone().isoformat()
        if datetime.fromisoformat(captured_at).tzinfo is None:
            raise ValueError("capture time requires timezone")
        metadata = tuple(sorted(metadata))
        policy_refs = tuple(sorted(set(policy_refs)))
        raw_fp = Fingerprint(
            "raw_content",
            sha256_bytes(raw),
            canonicalization_profile="cpkt.raw-bytes@1",
        )
        source_ref = stable_token("SRC", source_key)
        coverage = Coverage(
            "capture", "complete", ("local_file_bytes",), ("local_file_bytes",)
        )
        snapshot_ref = stable_token(
            "SNAP",
            source_ref,
            raw_fp.value,
            canonical_json_hash(metadata),
            captured_at,
            canonical_json_hash(policy_refs),
            self.media_type,
            canonical_json_hash(asdict(coverage)),
        )
        capture_ref = stable_token("CAP", snapshot_ref, "cpkt.local-file.capture@1")
        record_ref = stable_token("REC", snapshot_ref, "document")
        raw_ref = RawContentReference(
            stable_token("RAW", snapshot_ref, raw_fp.value),
            source_ref,
            snapshot_ref,
            record_ref,
            str(path.absolute()),
            self.media_type,
            raw_fp,
            policy_refs,
            capture_ref,
        )
        snapshot = SourceSnapshot(
            snapshot_ref,
            source_ref,
            captured_at,
            capture_ref,
            coverage,
            policy_refs,
            metadata,
        )
        record = SourceRecord(
            source_key,
            source_ref,
            snapshot_ref,
            record_ref,
            self.media_type,
            (raw_ref.raw_content_ref,),
        )
        captured = CapturedSource(snapshot, record, raw_ref, raw)
        captured.validate()
        return captured

    def capture_many(
        self, bindings: Iterable[tuple[str, Path]]
    ) -> list[CapturedSource]:
        return [self.capture(source_key, path) for source_key, path in bindings]

    def resolve_content(
        self,
        captured: CapturedSource,
        address: EvidenceAddress,
        *,
        consumer_ref: str,
        purpose: str,
        mode: str = "content",
        evaluation: PolicyEvaluationInput | None = None,
        decision: PolicyDecision | None = None,
    ) -> ResolutionResult:
        """Policy inputs must come from the trusted host, independently of this adapter.

        Denials do not disclose existence, selector details, metadata or content.
        Conditions/redaction are not implemented and therefore cannot grant access.
        """
        operation = {"content": "read_content", "metadata_only": "read_metadata"}.get(
            mode
        )
        if not (
            consumer_ref
            and purpose
            and operation
            and evaluation
            and decision
            and decision.result == "permit"
            and not decision.conditions
            and decision.decision_authority_ref
            and decision.policy_rule_refs
            and evaluation.actor_or_consumer_ref == consumer_ref
            and evaluation.purpose == purpose
            and evaluation.requested_action == "resolve_evidence"
            and {"resolve_evidence", operation}
            <= set(evaluation.requested_data_operations)
            and PolicyDecisionValidator().validate(decision, evaluation).disposition
            == "valid"
            and any(
                s.subject_type == "evidence_address"
                and s.stable_id == address.evidence_address_ref
                and s.version == "1"
                and s.authority_context == "Source and Evidence"
                for s in evaluation.subject_refs
            )
            and any(
                s.subject_type == "source_snapshot"
                and s.stable_id == address.snapshot_ref
                and s.version == "1"
                and s.authority_context == "Source and Evidence"
                for s in evaluation.subject_refs
            )
            and set((*captured.snapshot.policy_refs, *address.policy_refs))
            <= set(evaluation.policy_anchor_ids)
        ):
            return ResolutionResult("not_authorized")
        if not self.resolve(captured, address):
            return ResolutionResult(
                "not_resolvable", diagnostic_code="source_evidence_integrity"
            )
        return ResolutionResult("resolved", address.text if mode == "content" else None)
