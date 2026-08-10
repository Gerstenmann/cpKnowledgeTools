from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from cp_knowledge_tools.platform.hashing import canonical_json_hash
from cp_knowledge_tools.publication.codec import PublicationUnitDocument

from .models import CoreValidationInputError, PreparedCoreInputs, RuleOutcome
from .rules import RULE_REGISTRY, RuleContext

VALIDATOR_REF = "cpkt.validator.core-knowledge"
VALIDATOR_VERSION = "0.1.0"


class CoreKnowledgeValidator:
    """Deterministic, read-only executor for the active Core rule registry."""

    def __init__(self, inputs: PreparedCoreInputs) -> None:
        self.inputs = inputs
        definitions = inputs.profile_payload.get("validator_rules", [])
        self.rule_definitions = {
            item["validator_rule_ref"]: item for item in definitions
        }
        unresolved = sorted(set(self.rule_definitions) - set(RULE_REGISTRY))
        if unresolved:
            raise CoreValidationInputError(
                "core_knowledge_rule_resolution_failed",
                (
                    "active Core rules have no executable handler: "
                    f"{', '.join(unresolved)}"
                ),
                "/payload/validator_rules",
            )

    def validate_input(
        self,
        input_value: dict[str, Any],
        rule_refs: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        diagnostics = []
        artifacts: dict[str, Any] = {}
        rule_outcomes: list[dict[str, Any]] = []
        for rule_ref in sorted(set(rule_refs)):
            definition = self.rule_definitions.get(rule_ref)
            handler = RULE_REGISTRY.get(rule_ref)
            if definition is None or handler is None:
                raise CoreValidationInputError(
                    "core_knowledge_rule_resolution_failed",
                    f"rule {rule_ref!r} cannot be resolved",
                    "/rule_refs",
                )
            context = RuleContext(
                input_value=input_value,
                rule_definition=definition,
                profile_payload=self.inputs.profile_payload,
            )
            try:
                outcome = handler(context)
            except (KeyError, TypeError, ValueError) as exc:
                outcome = RuleOutcome(
                    diagnostics=[
                        context.diagnostic(
                            path="/",
                            message=f"rule could not evaluate malformed input: {exc}",
                        )
                    ]
                )
            diagnostics.extend(outcome.diagnostics)
            for key, value in outcome.artifacts.items():
                if key in artifacts and artifacts[key] != value:
                    raise CoreValidationInputError(
                        "core_knowledge_rule_artifact_collision",
                        f"rules produced conflicting artifact {key!r}",
                    )
                artifacts[key] = value
            rule_outcomes.append(
                {
                    "validator_rule_ref": rule_ref,
                    "diagnostic_count": len(outcome.diagnostics),
                    "artifact_keys": sorted(outcome.artifacts),
                }
            )
        diagnostics.sort(key=lambda item: item.sort_key())
        conformance_status = (
            "fail"
            if any(item.severity in {"fatal", "error"} for item in diagnostics)
            else "pass"
        )
        return {
            "conformance_status": conformance_status,
            "diagnostics": [item.to_dict() for item in diagnostics],
            "artifacts": artifacts,
            "rule_outcomes": rule_outcomes,
        }

    def applicable_publication_rules(
        self, execution_context: dict[str, Any] | None = None
    ) -> tuple[list[str], list[str]]:
        applicable = {
            "CK-CONFLICT-001",
            "CK-EPI-001",
            "CK-EVT-001",
            "CK-RB-001",
            "CK-RT-001",
            "CK-SCH-001",
            "CK-TIME-001",
            "CK-XVIEW-001",
        }
        if execution_context and (
            "policy_decisions" in execution_context
            or "expected_access" in execution_context
        ):
            applicable.add("CK-POL-001")
        declared = set(self.rule_definitions)
        return sorted(applicable & declared), sorted(declared - applicable)

    def validate_publication_unit(
        self,
        document: PublicationUnitDocument,
        *,
        source_ref: str | None = None,
        execution_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC).isoformat()
        applicable, not_applicable = self.applicable_publication_rules(
            execution_context
        )
        input_value: dict[str, Any] = {
            "manifest": deepcopy(document.manifest),
            "markdown_body": document.markdown_body,
        }
        if execution_context is not None:
            input_value["execution_context"] = deepcopy(execution_context)
        before = canonical_json_hash(input_value)
        validation = self.validate_input(input_value, applicable)
        after = canonical_json_hash(input_value)
        mutation_detected = before != after
        if mutation_detected:
            validation["conformance_status"] = "fail"
        required_profiles = [
            {
                "profile_ref": manifest["profile_ref"],
                "profile_version": manifest["profile_version"],
                "status": manifest["status"],
                "manifest_hash": self.inputs.required_profile_hashes[
                    f"{manifest['profile_ref']}@{manifest['profile_version']}"
                ],
            }
            for manifest in sorted(
                self.inputs.required_profile_manifests,
                key=lambda item: (item["profile_ref"], item["profile_version"]),
            )
        ]
        rule_sources = sorted(
            {
                source
                for rule_ref in applicable
                for source in self.rule_definitions[rule_ref].get("rule_sources", [])
            }
        )
        payload = {
            "report_type": "core_knowledge_publication_unit_conformance",
            "validator_ref": VALIDATOR_REF,
            "validator_version": VALIDATOR_VERSION,
            "validator": {
                "validator_ref": VALIDATOR_REF,
                "version": VALIDATOR_VERSION,
            },
            "profile_ref": self.inputs.profile_manifest["profile_ref"],
            "profile_version": self.inputs.profile_manifest["profile_version"],
            "profile_manifest_hash": self.inputs.profile_hash,
            "profile_hash": self.inputs.profile_hash,
            "canonicalization_profile_ref": (
                "cpks.profile.canonicalization.canonical-json-value@1.0"
            ),
            "required_profile_resolution": "resolved",
            "required_profiles": required_profiles,
            "contract_conformance_corpus_execution": (
                "not_in_scope_for_this_slice"
            ),
            "input_mode": "standalone_publication_unit",
            "rule_sources": rule_sources,
            "started_at": started_at,
            "completed_at": datetime.now(UTC).isoformat(),
            "publication_unit_ref": {
                "stable_id": document.manifest.get("knowledge_object_id"),
                "version": document.manifest.get("knowledge_object_version"),
                "source_ref": source_ref,
            },
            "input_fingerprint": before,
            "conformance_status": validation["conformance_status"],
            "applicable_rule_refs": applicable,
            "not_applicable_rule_refs": not_applicable,
            "diagnostics": validation["diagnostics"],
            "rule_outcomes": validation["rule_outcomes"],
            "artifacts": validation["artifacts"],
            "input_mutation_detected": mutation_detected,
        }
        payload["output_fingerprint"] = canonical_json_hash(
            {
                key: value
                for key, value in payload.items()
                if key not in {"started_at", "completed_at"}
            }
        )
        return payload
