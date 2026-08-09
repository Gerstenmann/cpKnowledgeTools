from __future__ import annotations

from typing import Any

from cp_knowledge_tools.platform.hashing import stable_token
from cp_knowledge_tools.sources.models import EvidenceAddress, SourceRecord


class RuleBasedSemanticInterpreter:
    """Small deterministic semantic reference interpreter.

    This engine is source-neutral. Scenario-specific extraction rules are
    supplied by the caller. The engine never reads Golden Truth or Expected
    Result files.
    """

    def interpret(
        self,
        records: dict[str, SourceRecord],
        evidence: dict[str, EvidenceAddress],
        rules: dict[str, Any],
    ) -> dict[str, Any]:
        entities = self._entities(records, rules.get("entities", []))
        entity_by_key = {item["rule_key"]: item for item in entities}

        claims = self._claims(records, evidence, entity_by_key, rules.get("claims", []))
        claim_by_key = {item["rule_key"]: item for item in claims}

        evidence_links = self._evidence_links(
            evidence, claim_by_key, rules.get("evidence_links", [])
        )
        events = self._events(records, rules.get("events", []))
        event_by_key = {item["rule_key"]: item for item in events}
        participations = self._participations(
            entity_by_key, event_by_key, rules.get("participations", [])
        )
        conflict_sets = self._conflicts(claim_by_key, rules.get("conflict_sets", []))
        pattern_claims = self._pattern_claims(records, rules.get("pattern_claims", []))

        return {
            "entities": entities,
            "claims": claims,
            "evidence_links": evidence_links,
            "events": events,
            "participations": participations,
            "conflict_sets": conflict_sets,
            "pattern_claims": pattern_claims,
        }

    def _entities(
        self,
        records: dict[str, SourceRecord],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        corpus = "\n".join(record.normalized_text for record in records.values())
        result = []
        for rule in rules:
            label = rule["label"]
            if label not in corpus:
                raise ValueError(f"Entity label is not grounded in Sources: {label!r}")
            result.append(
                {
                    "rule_key": rule["rule_key"],
                    "entity_ref": stable_token("ENT", rule["class"], label),
                    "label": label,
                    "class": rule["class"],
                }
            )
        return result

    def _claims(
        self,
        records: dict[str, SourceRecord],
        evidence: dict[str, EvidenceAddress],
        entity_by_key: dict[str, dict[str, Any]],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for rule in rules:
            source_keys = list(rule["source_keys"])
            for source_key in source_keys:
                if source_key not in records:
                    raise ValueError(f"Claim source missing: {source_key}")
            evidence_keys = list(rule.get("evidence_keys", []))
            if not evidence_keys:
                raise ValueError(f"Material Claim lacks Evidence: {rule['rule_key']}")
            for evidence_key in evidence_keys:
                if evidence_key not in evidence:
                    raise ValueError(f"Claim Evidence missing: {evidence_key}")

            subject = entity_by_key[rule["subject_key"]]
            value = rule.get("value")
            object_entity_key = rule.get("object_entity_key")
            object_ref = (
                entity_by_key[object_entity_key]["entity_ref"]
                if object_entity_key
                else None
            )
            claim_ref = stable_token(
                "CLM",
                subject["entity_ref"],
                rule["predicate"],
                object_ref or value,
                rule.get("time_modality"),
            )
            result.append(
                {
                    "rule_key": rule["rule_key"],
                    "claim_ref": claim_ref,
                    "subject_ref": subject["entity_ref"],
                    "predicate_ref": rule["predicate"],
                    "value": value,
                    "object_ref": object_ref,
                    "epistemic_status": rule["epistemic_status"],
                    "source_keys": source_keys,
                    "evidence_keys": evidence_keys,
                    "time_modality": rule.get("time_modality"),
                    "current": rule.get("current", True),
                    "preserved": rule.get("preserved", True),
                    "value_qualifier": rule.get("value_qualifier"),
                }
            )
        return result

    def _evidence_links(
        self,
        evidence: dict[str, EvidenceAddress],
        claim_by_key: dict[str, dict[str, Any]],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for rule in rules:
            claim = claim_by_key[rule["claim_key"]]
            address = evidence[rule["evidence_key"]]
            result.append(
                {
                    "rule_key": rule["rule_key"],
                    "evidence_link_ref": stable_token(
                        "EL",
                        claim["claim_ref"],
                        address.evidence_address_ref,
                        rule["role"],
                    ),
                    "claim_ref": claim["claim_ref"],
                    "evidence_address_ref": address.evidence_address_ref,
                    "role": rule["role"],
                }
            )
        return result

    def _events(
        self,
        records: dict[str, SourceRecord],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for rule in rules:
            for source_key in rule["source_keys"]:
                if source_key not in records:
                    raise ValueError(f"Event source missing: {source_key}")
            event_ref = stable_token("EVT", rule["event_type"], rule["label"])
            result.append(
                {
                    "rule_key": rule["rule_key"],
                    "event_ref": event_ref,
                    "event_type_ref": rule["event_type"],
                    "label": rule["label"],
                    "event_time": rule.get("event_time"),
                    "time_precision": rule.get("time_precision", "unknown"),
                    "time_modality": rule.get("time_modality", "planned"),
                    "source_keys": list(rule["source_keys"]),
                    "evidence_keys": list(rule.get("evidence_keys", [])),
                }
            )
        return result

    def _participations(
        self,
        entity_by_key: dict[str, dict[str, Any]],
        event_by_key: dict[str, dict[str, Any]],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for rule in rules:
            entity = entity_by_key[rule["entity_key"]]
            event = event_by_key[rule["event_key"]]
            role = rule["role"]
            if not role:
                raise ValueError("Event Participation role is mandatory")
            result.append(
                {
                    "rule_key": rule["rule_key"],
                    "participation_ref": stable_token(
                        "PART", entity["entity_ref"], event["event_ref"], role
                    ),
                    "entity_ref": entity["entity_ref"],
                    "event_ref": event["event_ref"],
                    "role": role,
                    "source_keys": list(rule.get("source_keys", [])),
                }
            )
        return result

    def _conflicts(
        self,
        claim_by_key: dict[str, dict[str, Any]],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for rule in rules:
            claims = [claim_by_key[key] for key in rule["claim_keys"]]
            preferred = claim_by_key[rule["preferred_claim_key"]]
            result.append(
                {
                    "rule_key": rule["rule_key"],
                    "conflict_set_ref": stable_token(
                        "CF",
                        *sorted(claim["claim_ref"] for claim in claims),
                        *rule["conflict_dimensions"],
                    ),
                    "claim_refs": [claim["claim_ref"] for claim in claims],
                    "conflict_dimensions": list(rule["conflict_dimensions"]),
                    "preferred_claim_ref": preferred["claim_ref"],
                    "preference_context": rule["preference_context"],
                    "rationale": rule["rationale"],
                }
            )
        return result

    def _pattern_claims(
        self,
        records: dict[str, SourceRecord],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for rule in rules:
            record = records[rule["source_key"]]
            needle = rule["required_text"]
            if needle not in record.normalized_text:
                raise ValueError(f"Pattern source text not found: {needle!r}")
            result.append(
                {
                    "rule_key": rule["rule_key"],
                    "statement": needle,
                    "epistemic_status": rule["epistemic_status"],
                    "evidence_roles": list(rule["evidence_roles"]),
                    "source_keys": [rule["source_key"]],
                }
            )
        return result
