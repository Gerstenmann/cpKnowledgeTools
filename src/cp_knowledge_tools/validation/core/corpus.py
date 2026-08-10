from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cp_knowledge_tools.platform.hashing import canonical_json_hash

from .models import CoreValidationInputError, PreparedCoreInputs
from .validator import VALIDATOR_REF, VALIDATOR_VERSION, CoreKnowledgeValidator


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _diagnostic_expectation(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": value.get("severity"),
        "code": value.get("code"),
        "path": value.get("path"),
    }


def _compare_expected(
    actual: dict[str, Any], expected: dict[str, Any]
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    if actual["conformance_status"] != expected.get("conformance_status"):
        mismatches.append(
            {
                "field": "conformance_status",
                "expected": expected.get("conformance_status"),
                "actual": actual["conformance_status"],
            }
        )
    actual_diagnostics = [
        _diagnostic_expectation(item) for item in actual["diagnostics"]
    ]
    expected_diagnostics = expected.get("diagnostics", [])
    if actual_diagnostics != expected_diagnostics:
        mismatches.append(
            {
                "field": "diagnostics",
                "expected": expected_diagnostics,
                "actual": actual_diagnostics,
            }
        )
    for key, expected_value in expected.items():
        if key in {"conformance_status", "diagnostics"}:
            continue
        actual_value = actual["artifacts"].get(key)
        if actual_value != expected_value:
            mismatches.append(
                {"field": key, "expected": expected_value, "actual": actual_value}
            )
    return mismatches


def run_core_knowledge_corpus(
    inputs: PreparedCoreInputs,
    *,
    validator: CoreKnowledgeValidator | None = None,
) -> dict[str, Any]:
    """Execute every Golden case without mutating Profile, Corpus, or case input."""
    started_at = _timestamp()
    validator = validator or CoreKnowledgeValidator(inputs)
    case_results: list[dict[str, Any]] = []
    cases = sorted(inputs.corpus_payload["cases"], key=lambda item: item["case_id"])
    for case in cases:
        case_copy = deepcopy(case)
        input_fingerprint = canonical_json_hash(case_copy["input"])
        whole_case_before = canonical_json_hash(case_copy)
        actual = validator.validate_input(case_copy["input"], case_copy["rule_refs"])
        whole_case_after = canonical_json_hash(case_copy)
        mutation_detected = whole_case_before != whole_case_after
        mismatches = _compare_expected(actual, case_copy["expected"])
        if mutation_detected:
            mismatches.append(
                {
                    "field": "input_mutation",
                    "expected": False,
                    "actual": True,
                }
            )
        result = {
            "case_id": case_copy["case_id"],
            "profile_ref": inputs.profile_manifest["profile_ref"],
            "profile_version": inputs.profile_manifest["profile_version"],
            "input_fingerprint": input_fingerprint,
            "conformance_status": actual["conformance_status"],
            "diagnostics": actual["diagnostics"],
            "artifacts": actual["artifacts"],
            "rule_outcomes": actual["rule_outcomes"],
            "input_mutation_detected": mutation_detected,
            "expected_outcome_match": not mismatches,
            "mismatches": mismatches,
        }
        fingerprint_value = deepcopy(result)
        result["output_fingerprint"] = canonical_json_hash(fingerprint_value)
        case_results.append(result)

    exact_count = sum(item["expected_outcome_match"] for item in case_results)
    completed_at = _timestamp()
    required_profiles = [
        {
            "profile_ref": manifest["profile_ref"],
            "profile_version": manifest["profile_version"],
            "status": manifest["status"],
            "manifest_hash": inputs.required_profile_hashes[
                f"{manifest['profile_ref']}@{manifest['profile_version']}"
            ],
        }
        for manifest in sorted(
            inputs.required_profile_manifests,
            key=lambda item: (item["profile_ref"], item["profile_version"]),
        )
    ]
    rule_sources = sorted(
        {
            source
            for rule in inputs.profile_payload["validator_rules"]
            for source in rule.get("rule_sources", [])
        }
    )
    report = {
        "report_type": "core_knowledge_conformance",
        "validator_ref": VALIDATOR_REF,
        "validator_version": VALIDATOR_VERSION,
        "validator": {
            "validator_ref": VALIDATOR_REF,
            "version": VALIDATOR_VERSION,
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "profile_ref": inputs.profile_manifest["profile_ref"],
        "profile_version": inputs.profile_manifest["profile_version"],
        "profile_manifest_hash": inputs.profile_hash,
        "profile_hash": inputs.profile_hash,
        "corpus_ref": inputs.corpus_manifest["corpus_ref"],
        "corpus_version": inputs.corpus_manifest["corpus_version"],
        "corpus_hash": inputs.corpus_hash,
        "required_profile_hashes": dict(sorted(inputs.required_profile_hashes.items())),
        "required_profile_resolution": "resolved",
        "required_profiles": required_profiles,
        "canonicalization_profile_ref": (
            "cpks.profile.canonicalization.canonical-json-value@1.0"
        ),
        "contract_conformance_corpus_execution": (
            "not_in_scope_for_this_slice"
        ),
        "rule_sources": rule_sources,
        "input_mode": "golden_corpus",
        "case_count": len(case_results),
        "cases_passed_exactly": exact_count,
        "cases_failed": len(case_results) - exact_count,
        "exact_outcome_count": exact_count,
        "overall_status": "pass" if exact_count == len(case_results) else "fail",
        "case_results": case_results,
    }
    fingerprint_value = {
        key: value
        for key, value in report.items()
        if key not in {"started_at", "completed_at"}
    }
    report["report_fingerprint"] = canonical_json_hash(fingerprint_value)
    return report


def integrity_failure_report(error: CoreValidationInputError) -> dict[str, Any]:
    now = _timestamp()
    report = {
        "report_type": "core_knowledge_conformance",
        "validator_ref": VALIDATOR_REF,
        "validator_version": VALIDATOR_VERSION,
        "validator": {
            "validator_ref": VALIDATOR_REF,
            "version": VALIDATOR_VERSION,
        },
        "started_at": now,
        "completed_at": now,
        "overall_status": "fail",
        "input_mode": "golden_corpus",
        "case_count": 0,
        "cases_passed_exactly": 0,
        "cases_failed": 0,
        "exact_outcome_count": 0,
        "diagnostics": [
            {
                "severity": "fatal",
                "code": error.code,
                "path": error.path,
                "message": error.message,
                "validator_rule_ref": "CK-CORP-001",
                "rule_sources": [],
            }
        ],
        "case_results": [],
    }
    report["report_fingerprint"] = canonical_json_hash(
        {
            key: value
            for key, value in report.items()
            if key not in {"started_at", "completed_at"}
        }
    )
    return report


def write_json_report(report: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
