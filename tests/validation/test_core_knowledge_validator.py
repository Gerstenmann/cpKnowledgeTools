from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from cp_knowledge_tools.platform.hashing import canonical_json_hash
from cp_knowledge_tools.publication import (
    PublicationUnitDocument,
    parse_publication_unit,
    render_publication_unit,
)
from cp_knowledge_tools.validation.core import (
    CANONICALIZATION_PROFILE,
    CONTRACT_PROFILE,
    CORE_CORPUS,
    CORE_PROFILE,
    CoreKnowledgeValidator,
    CoreValidationInputError,
    load_json_object,
    prepare_core_inputs,
    run_core_knowledge_corpus,
    write_json_report,
)
from scripts.cp_tools.validator import run_core_knowledge_conformance

RULES = {
    "CK-CLAIM-ID-001": ("error", "claim_identity_reused_for_material_change"),
    "CK-CONFLICT-001": ("error", "core_conflict_preservation_failed"),
    "CK-CORP-001": ("fatal", "core_knowledge_golden_corpus_integrity_failed"),
    "CK-EPI-001": ("error", "core_epistemic_evidence_conformance_failed"),
    "CK-EVT-001": ("error", "event_participation_role_missing"),
    "CK-POL-001": ("fatal", "claim_access_used_as_evidence_permission"),
    "CK-PROFILE-001": ("fatal", "core_vocabulary_namespace_collision"),
    "CK-RB-001": ("fatal", "core_publication_unit_rebuild_failed"),
    "CK-RT-001": ("fatal", "core_publication_unit_round_trip_failed"),
    "CK-SCH-001": ("error", "core_knowledge_schema_conformance_failed"),
    "CK-TIME-001": ("error", "core_time_semantics_changed"),
    "CK-XVIEW-001": ("error", "material_narrative_statement_unmapped"),
}

ROUND_TRIP_FIELDS = [
    "identity",
    "schema_ref",
    "semantic_model_ref",
    "vocabulary_set_ref",
    "primary_kind",
    "knowledge_functions",
    "applicability",
    "profile_refs",
    "claims",
    "events",
    "event_participations",
    "evidence_links",
    "structural_relationships",
    "conflict_sets",
    "policy_anchors",
    "cross_view_mappings",
    "body_sha256",
]


def _ref(subject_type: str, stable_id: str) -> dict[str, str]:
    return {
        "subject_type": subject_type,
        "stable_id": stable_id,
        "version": "7.3",
        "authority_context": "Synthetic",
    }


def _document() -> PublicationUnitDocument:
    object_ref = _ref("knowledge_object", "KO-ARBITRARY-ZETA")
    claim_ref = _ref("claim", "CLM-ARBITRARY-OMEGA")
    manifest = {
        "document_type": "knowledge_object_publication_unit",
        "template_ref": "CPKS-TPL-KM-PU@0.1",
        "knowledge_object_id": object_ref["stable_id"],
        "knowledge_object_version": object_ref["version"],
        "schema_ref": "CPKS-SPEC-KM-PU@0.1",
        "semantic_model_ref": "CPKS-SPEC-KM@0.20",
        "vocabulary_set_ref": "CPKS-SPEC-KM-VOC@0.1",
        "title": "Arbitrary semantic unit",
        "language": "en",
        "canonical_path": None,
        "primary_kind": "evidence_synthesis",
        "knowledge_functions": ["descriptive"],
        "applicability": {
            "domain_refs": [],
            "entity_refs": [],
            "organization_refs": [],
            "product_refs": [],
            "purposes": ["synthetic_validation"],
            "valid_time": [],
        },
        "profile_refs": [],
        "claims": [
            {
                "claim_ref": claim_ref,
                "statement": {
                    "subject_ref": _ref("entity", "ENT-ARBITRARY-SIGMA"),
                    "predicate_ref": "synthetic.predicate.state",
                    "object": {"kind": "literal", "value": "alpha"},
                },
                "epistemic_status": "reported",
                "time": [],
                "evidence_link_ids": ["EL-ARBITRARY-TAU"],
                "authority_basis_refs": [],
                "policy_anchor_ids": ["PA-ARBITRARY"],
                "conflict_set_ids": [],
                "narrative_anchor": "claim-arbitrary",
            }
        ],
        "events": [],
        "event_participations": [],
        "evidence_links": [
            {
                "evidence_link_id": "EL-ARBITRARY-TAU",
                "subject_ref": claim_ref,
                "evidence_address_ref": _ref(
                    "evidence_address", "EVA-ARBITRARY-PHI"
                ),
                "role": "reports_statement",
                "narrative_anchor": "evidence-arbitrary",
                "policy_anchor_ids": ["PA-ARBITRARY"],
                "time_relevance": [],
            }
        ],
        "structural_relationships": [],
        "conflict_sets": [],
        "policy_anchors": [
            {
                "policy_anchor_id": "PA-ARBITRARY",
                "narrative_anchor": "policy-arbitrary",
                "dimensions": ["read_access", "evidence_resolution"],
                "subject_refs": [object_ref],
                "policy_refs": [],
                "policy_decision_refs": [],
            }
        ],
        "human_readable": {
            "summary_anchor": "summary-arbitrary",
            "applicability_anchor": "applicability-arbitrary",
        },
        "cross_view_mappings": [
            {
                "mapping_id": "MAP-CLAIM-ARBITRARY",
                "material": True,
                "narrative_anchor": "claim-arbitrary",
                "representation_role": "primary_statement",
                "semantic_ref": claim_ref,
            }
        ],
        "review_record_refs": [],
        "policy_decision_refs": [],
        "publication": {
            "publication_state": "unpublished",
            "publication_record_ref": None,
            "published_at": None,
            "publisher_ref": None,
            "predecessor_publication_ref": None,
        },
        "integrity": {
            "content_hash": None,
            "cross_view_validation": {"status": "pending", "report_ref": None},
        },
    }
    body = (
        '<a id="summary-arbitrary"></a>\n'
        '<a id="applicability-arbitrary"></a>\n'
        '<a id="claim-arbitrary"></a>\n'
        '<a id="evidence-arbitrary"></a>\n'
        '<a id="policy-arbitrary"></a>\n'
        "Arbitrary semantic statement."
    )
    return PublicationUnitDocument(manifest, body)


def _hash_block(payload: dict[str, object], scope: str) -> dict[str, object]:
    return {
        "algorithm": "sha-256",
        "canonicalization_profile": {
            "profile_ref": CANONICALIZATION_PROFILE[0],
            "profile_version": CANONICALIZATION_PROFILE[1],
        },
        "hash_scope": scope,
        "value": canonical_json_hash(payload),
    }


def _profile_manifest(
    identity: tuple[str, str], payload: dict[str, object]
) -> dict[str, object]:
    return {
        "document_type": "profile_manifest",
        "profile_ref": identity[0],
        "profile_version": identity[1],
        "status": "active",
        "payload": payload,
        "manifest_hash": _hash_block(payload, "profile_manifest_payload"),
        "content_hash": _hash_block(payload, "profile_manifest_payload"),
    }


def _raw_inputs() -> tuple[dict[str, object], ...]:
    document = _document()
    cases = [
        {
            "case_id": f"CASE-ARBITRARY-{index:02d}",
            "rule_refs": ["CK-SCH-001"],
            "input": {
                "manifest": deepcopy(document.manifest),
                "markdown_body": document.markdown_body,
            },
            "expected": {"conformance_status": "pass", "diagnostics": []},
        }
        for index in range(16)
    ]
    corpus_payload = {
        "corpus_ref": CORE_CORPUS[0],
        "corpus_version": CORE_CORPUS[1],
        "profile_ref": CORE_PROFILE[0],
        "profile_version": CORE_PROFILE[1],
        "case_count": 16,
        "cases": cases,
    }
    corpus_hash = canonical_json_hash(corpus_payload)
    core_payload = {
        "profile_ref": CORE_PROFILE[0],
        "profile_version": CORE_PROFILE[1],
        "required_profiles": [
            {
                "profile_ref": CONTRACT_PROFILE[0],
                "compatible_versions": [CONTRACT_PROFILE[1]],
            },
            {
                "profile_ref": CANONICALIZATION_PROFILE[0],
                "compatible_versions": [CANONICALIZATION_PROFILE[1]],
            },
        ],
        "validator_rules": [
            {
                "validator_rule_ref": rule_ref,
                "severity": severity,
                "diagnostic_code": code,
                "rule_sources": ["SYNTHETIC-RULE-SOURCE@1.0"],
            }
            for rule_ref, (severity, code) in RULES.items()
        ],
        "semantic_projection_contract": {
            "round_trip_projection": ROUND_TRIP_FIELDS,
            "rebuild_projection": [
                "knowledge_object_ref",
                "claim_index",
                "event_index",
                "participation_index",
                "evidence_index",
                "conflict_index",
                "policy_index",
            ],
        },
        "fixture_refs": [
            {
                "corpus_ref": CORE_CORPUS[0],
                "corpus_version": CORE_CORPUS[1],
                "content_hash": {
                    "algorithm": "sha-256",
                    "canonicalization_profile": {
                        "profile_ref": CANONICALIZATION_PROFILE[0],
                        "profile_version": CANONICALIZATION_PROFILE[1],
                    },
                    "hash_scope": "golden_corpus_payload",
                    "value": corpus_hash,
                },
            }
        ],
    }
    core_manifest = _profile_manifest(CORE_PROFILE, core_payload)
    corpus_manifest = {
        "document_type": "golden_corpus_manifest",
        "corpus_ref": CORE_CORPUS[0],
        "corpus_version": CORE_CORPUS[1],
        "profile_ref": CORE_PROFILE[0],
        "profile_version": CORE_PROFILE[1],
        "status": "active",
        "case_count": 16,
        "content_hash": _hash_block(corpus_payload, "golden_corpus_payload"),
    }
    contract_payload = {
        "profile_ref": CONTRACT_PROFILE[0],
        "profile_version": CONTRACT_PROFILE[1],
    }
    canonical_payload = {
        "profile_ref": CANONICALIZATION_PROFILE[0],
        "profile_version": CANONICALIZATION_PROFILE[1],
    }
    return (
        core_manifest,
        corpus_manifest,
        corpus_payload,
        _profile_manifest(CONTRACT_PROFILE, contract_payload),
        _profile_manifest(CANONICALIZATION_PROFILE, canonical_payload),
    )


def _prepared():
    core, corpus, payload, contract, canonical = _raw_inputs()
    return prepare_core_inputs(
        profile_manifest=core,
        corpus_manifest=corpus,
        corpus_payload=payload,
        required_profile_manifests=[contract, canonical],
    )


def _codes(result: dict[str, object]) -> set[str]:
    return {item["code"] for item in result["diagnostics"]}


def test_publication_unit_codec_preserves_manifest_and_exact_body() -> None:
    document = _document()

    reparsed = parse_publication_unit(render_publication_unit(document))

    assert reparsed == document


def test_input_integrity_rejects_tampered_corpus_and_missing_profile() -> None:
    core, corpus, payload, contract, canonical = _raw_inputs()
    payload["cases"][0]["expected"]["conformance_status"] = "fail"

    with pytest.raises(CoreValidationInputError) as tampered:
        prepare_core_inputs(
            profile_manifest=core,
            corpus_manifest=corpus,
            corpus_payload=payload,
            required_profile_manifests=[contract, canonical],
        )
    assert tampered.value.code == "core_knowledge_golden_corpus_integrity_failed"

    core, corpus, payload, _contract, canonical = _raw_inputs()
    with pytest.raises(CoreValidationInputError) as missing:
        prepare_core_inputs(
            profile_manifest=core,
            corpus_manifest=corpus,
            corpus_payload=payload,
            required_profile_manifests=[canonical],
        )
    assert missing.value.code == "core_knowledge_profile_resolution_failed"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda core, _corpus, _payload, _contract: core[
                "manifest_hash"
            ].update({"value": "0" * 64}),
            "core_knowledge_profile_integrity_failed",
        ),
        (
            lambda core, _corpus, _payload, _contract: core.__setitem__(
                "status", "draft"
            ),
            "core_knowledge_profile_resolution_failed",
        ),
        (
            lambda core, _corpus, _payload, _contract: core.__setitem__(
                "profile_version", "9.9"
            ),
            "core_knowledge_profile_resolution_failed",
        ),
        (
            lambda _core, corpus, _payload, _contract: corpus.__setitem__(
                "profile_version", "9.9"
            ),
            "core_knowledge_golden_corpus_integrity_failed",
        ),
        (
            lambda _core, _corpus, _payload, contract: contract.__setitem__(
                "profile_version", "9.9"
            ),
            "core_knowledge_profile_resolution_failed",
        ),
    ],
)
def test_input_integrity_rejects_wrong_status_versions_binding_and_hash(
    mutation, expected_code: str
) -> None:
    core, corpus, payload, contract, canonical = _raw_inputs()
    mutation(core, corpus, payload, contract)

    with pytest.raises(CoreValidationInputError) as failure:
        prepare_core_inputs(
            profile_manifest=core,
            corpus_manifest=corpus,
            corpus_payload=payload,
            required_profile_manifests=[contract, canonical],
        )

    assert failure.value.code == expected_code


def test_canonical_json_loader_rejects_negative_zero(tmp_path: Path) -> None:
    payload = tmp_path / "negative-zero.json"
    payload.write_text('{"value":-0}\n', encoding="utf-8")

    with pytest.raises(CoreValidationInputError) as failure:
        load_json_object(payload)

    assert failure.value.code == "core_knowledge_golden_corpus_integrity_failed"


def test_cli_integrity_failure_is_structured_and_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, corpus, payload, contract, canonical = _raw_inputs()
    payload["case_count"] = 15
    paths: dict[str, Path] = {}
    for name, manifest in (
        ("core", core),
        ("corpus", corpus),
        ("contract", contract),
        ("canonical", canonical),
    ):
        path = tmp_path / f"{name}.md"
        path.write_text(
            render_publication_unit(PublicationUnitDocument(manifest, "")),
            encoding="utf-8",
        )
        paths[name] = path
    payload_path = tmp_path / "corpus.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_core_knowledge_conformance.py",
            "--profile-manifest",
            str(paths["core"]),
            "--corpus-manifest",
            str(paths["corpus"]),
            "--corpus-payload",
            str(payload_path),
            "--required-profile-manifest",
            str(paths["contract"]),
            "--required-profile-manifest",
            str(paths["canonical"]),
            "--report",
            str(report_path),
        ],
    )

    exit_code = run_core_knowledge_conformance.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert report["overall_status"] == "fail"
    assert report["diagnostics"][0]["severity"] == "fatal"


def test_corpus_harness_executes_all_cases_exactly_and_deterministically() -> None:
    inputs = _prepared()

    first = run_core_knowledge_corpus(inputs)
    second = run_core_knowledge_corpus(inputs)

    assert first["overall_status"] == "pass"
    assert first["case_count"] == first["exact_outcome_count"] == 16
    assert first["cases_passed_exactly"] == 16
    assert first["cases_failed"] == 0
    assert first["required_profile_resolution"] == "resolved"
    assert (
        first["contract_conformance_corpus_execution"]
        == "not_in_scope_for_this_slice"
    )
    assert [case["case_id"] for case in first["case_results"]] == sorted(
        case["case_id"] for case in first["case_results"]
    )
    assert [case["output_fingerprint"] for case in first["case_results"]] == [
        case["output_fingerprint"] for case in second["case_results"]
    ]
    assert first["report_fingerprint"] == second["report_fingerprint"]
    assert not any(
        case["input_mutation_detected"] for case in first["case_results"]
    )


def test_generic_claim_identity_epistemic_and_participation_defects() -> None:
    validator = CoreKnowledgeValidator(_prepared())
    document = _document()
    previous = {"manifest": deepcopy(document.manifest), "markdown_body": "before"}
    candidate = deepcopy(previous)
    candidate["manifest"]["claims"][0]["statement"]["object"]["value"] = "beta"

    identity = validator.validate_input(
        {
            "previous_publication_unit": previous,
            "candidate_publication_unit": candidate,
        },
        ["CK-CLAIM-ID-001"],
    )
    assert _codes(identity) == {"claim_identity_reused_for_material_change"}

    epistemic = deepcopy(document.manifest)
    epistemic["claims"][0]["epistemic_status"] = "confirmed"
    result = validator.validate_input(
        {"manifest": epistemic, "markdown_body": document.markdown_body},
        ["CK-EPI-001"],
    )
    assert _codes(result) == {"reported_statement_used_as_confirmation"}

    event_ref = _ref("event", "EVT-ARBITRARY-DELTA")
    participation = deepcopy(document.manifest)
    participation["events"] = [{"event_ref": event_ref}]
    participation["event_participations"] = [
        {
            "participation_ref": _ref(
                "event_participation", "PART-ARBITRARY-IOTA"
            ),
            "event_ref": event_ref,
            "entity_ref": _ref("entity", "ENT-ARBITRARY-KAPPA"),
            "role": None,
        }
    ]
    result = validator.validate_input(
        {"manifest": participation, "markdown_body": document.markdown_body},
        ["CK-EVT-001"],
    )
    assert _codes(result) == {"event_participation_role_missing"}


def test_generic_cross_view_namespace_policy_schema_and_time_defects() -> None:
    validator = CoreKnowledgeValidator(_prepared())
    document = _document()

    result = validator.validate_input(
        {
            "manifest": deepcopy(document.manifest),
            "markdown_body": (
                document.markdown_body + '\n<a id="arbitrary-unmapped"></a>'
            ),
        },
        ["CK-XVIEW-001"],
    )
    assert _codes(result) == {"material_narrative_statement_unmapped"}

    result = validator.validate_input(
        {"profile_extension": {"namespace": "cpks.vocab.core.arbitrary"}},
        ["CK-PROFILE-001"],
    )
    assert _codes(result) == {"core_vocabulary_namespace_collision"}

    result = validator.validate_input(
        {
            "manifest": deepcopy(document.manifest),
            "execution_context": {
                "expected_access": {"claim_read": "permit"},
                "policy_decisions": {"DECISION-ARBITRARY": "permit"},
            },
        },
        ["CK-POL-001"],
    )
    assert _codes(result) == {"claim_access_used_as_evidence_permission"}

    schema = deepcopy(document.manifest)
    schema["claims"][0]["evidence_link_ids"] = ["EL-DOES-NOT-RESOLVE"]
    result = validator.validate_input(
        {"manifest": schema, "markdown_body": document.markdown_body},
        ["CK-SCH-001"],
    )
    assert _codes(result) == {"core_knowledge_schema_conformance_failed"}

    temporal = deepcopy(document.manifest)
    temporal["claims"][0]["time"] = [{"role": "valid_time"}]
    result = validator.validate_input(
        {"manifest": temporal, "markdown_body": document.markdown_body},
        ["CK-TIME-001"],
    )
    assert _codes(result) == {"core_time_semantics_changed"}

    conflict = deepcopy(document.manifest)
    conflict["conflict_sets"] = [
        {
            "conflict_set_id": "CONFLICT-ARBITRARY",
            "claim_refs": [conflict["claims"][0]["claim_ref"]],
            "conflict_dimensions": ["not-a-core-dimension"],
        }
    ]
    result = validator.validate_input(
        {"manifest": conflict, "markdown_body": document.markdown_body},
        ["CK-CONFLICT-001"],
    )
    assert _codes(result) == {"core_conflict_preservation_failed"}


def test_resolved_empty_runtime_profiles_and_separate_policy_decisions_pass() -> None:
    validator = CoreKnowledgeValidator(_prepared())
    document = _document()

    result = validator.validate_input(
        {
            "manifest": deepcopy(document.manifest),
            "execution_context": {
                "expected_access": {
                    "claim_read": "permit",
                    "evidence_resolution": "deny",
                },
                "policy_decisions": {
                    "DECISION-CLAIM-ARBITRARY": "permit",
                    "DECISION-EVIDENCE-ARBITRARY": "deny",
                },
                "profile_applicability": {
                    "resolution_status": "resolved",
                    "determination": "no_profile_applicable",
                    "applicable_profile_refs": [],
                    "profile_refs_complete": True,
                },
            },
        },
        ["CK-POL-001"],
    )

    assert result["conformance_status"] == "pass"
    assert result["artifacts"]["invariants"] == [
        "empty_profile_refs_accepted_when_no_runtime_profile_applies",
        "claim_read_and_evidence_resolution_independently_decided",
        "validator_profiles_not_used_as_runtime_authorization_profiles",
    ]


def test_diagnostics_follow_profile_sort_order() -> None:
    validator = CoreKnowledgeValidator(_prepared())
    document = _document()
    invalid = deepcopy(document.manifest)
    invalid["schema_ref"] = "WRONG"
    invalid["template_ref"] = "WRONG"

    result = validator.validate_input(
        {"manifest": invalid, "markdown_body": document.markdown_body},
        ["CK-SCH-001"],
    )
    diagnostics = result["diagnostics"]

    assert diagnostics == sorted(
        diagnostics,
        key=lambda item: (
            {"fatal": 0, "error": 1, "warning": 2, "info": 3}[
                item["severity"]
            ],
            item["code"],
            item["path"],
            item["message"],
        ),
    )


def test_round_trip_and_delete_rebuild_are_stable_and_read_only() -> None:
    validator = CoreKnowledgeValidator(_prepared())
    document = _document()
    input_value = {
        "manifest": deepcopy(document.manifest),
        "markdown_body": document.markdown_body,
    }
    before = canonical_json_hash(input_value)

    first = validator.validate_input(input_value, ["CK-RB-001", "CK-RT-001"])
    second = validator.validate_input(input_value, ["CK-RB-001", "CK-RT-001"])

    assert first["conformance_status"] == "pass"
    assert first["artifacts"] == second["artifacts"]
    assert first["artifacts"]["rebuild"]["same_hash_after_delete_and_rebuild"]
    assert first["artifacts"]["round_trip"][
        "same_semantic_projection_hash_after_reparse"
    ]
    assert canonical_json_hash(input_value) == before


def test_publication_report_marks_applicable_rules_and_uses_caller_path(
    tmp_path: Path,
) -> None:
    validator = CoreKnowledgeValidator(_prepared())

    report = validator.validate_publication_unit(_document(), source_ref="caller-input")
    repeated = validator.validate_publication_unit(
        _document(), source_ref="caller-input"
    )
    output = write_json_report(report, tmp_path / "caller" / "report.json")

    assert report["conformance_status"] == "pass"
    assert "CK-RT-001" in report["applicable_rule_refs"]
    assert "CK-POL-001" in report["not_applicable_rule_refs"]
    assert report["output_fingerprint"] == repeated["output_fingerprint"]
    assert output.is_file()


def test_production_code_has_no_golden_or_scenario_dispatch() -> None:
    source_root = Path(__file__).parents[2] / "src/cp_knowledge_tools/validation/core"
    script = (
        Path(__file__).parents[2]
        / "scripts/cp_tools/validator/run_core_knowledge_conformance.py"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(source_root.glob("*.py"))
    ) + script.read_text(encoding="utf-8")

    assert "CK-" + "POS-" not in source
    assert "CK-" + "NEG-" not in source
    assert "/Users/cp/Documents/cp-wiki" not in source
    for scenario_term in ("minecraft", "school adviser", "pilot capacity"):
        assert scenario_term not in source.lower()
