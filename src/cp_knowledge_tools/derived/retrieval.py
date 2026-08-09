from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cp_knowledge_tools.platform.hashing import canonical_json_hash


class DerivedRetrievalBuilder:
    """Builds a minimal rebuildable projection from a Publication Unit manifest."""

    def build(self, manifest: dict[str, Any]) -> dict[str, Any]:
        claims = sorted(
            manifest["claims"],
            key=lambda item: (
                item["claim_ref"]["stable_id"],
                item["claim_ref"]["version"],
            ),
        )
        events = sorted(
            manifest["events"],
            key=lambda item: (
                item["event_ref"]["stable_id"],
                item["event_ref"]["version"],
            ),
        )
        evidence = sorted(
            [
                {
                    "evidence_link_id": item["evidence_link_id"],
                    "subject_ref": item["subject_ref"],
                    "evidence_address_ref": item["evidence_address_ref"],
                    "role": item["role"],
                    "policy_anchor_ids": item["policy_anchor_ids"],
                }
                for item in manifest["evidence_links"]
            ],
            key=lambda item: item["evidence_link_id"],
        )
        conflicts = sorted(
            manifest["conflict_sets"], key=lambda item: item["conflict_set_id"]
        )
        projection = {
            "projection_schema_version": "0.1",
            "knowledge_object_ref": {
                "subject_type": "knowledge_object",
                "stable_id": manifest["knowledge_object_id"],
                "version": manifest["knowledge_object_version"],
                "authority_context": "Semantic Core",
            },
            "claim_index": claims,
            "event_index": events,
            "participation_index": sorted(
                manifest["event_participations"],
                key=lambda item: item["participation_ref"]["stable_id"],
            ),
            "evidence_index": evidence,
            "conflict_index": conflicts,
            "policy_index": manifest["policy_anchors"],
        }
        semantic_hash = canonical_json_hash(projection)
        projection["projection_ref"] = f"DRP-{semantic_hash[:24].upper()}"
        projection["semantic_hash"] = semantic_hash
        return projection

    def write(self, projection: dict[str, Any], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
