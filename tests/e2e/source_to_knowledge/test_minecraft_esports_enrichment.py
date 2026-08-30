from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = REPO_ROOT / (
    "tests/golden/source_to_knowledge/minecraft_esports/enrichment/"
    "expected/scenario.v0.8.json"
)
SCENARIO_SHA256 = "eda713688cc7a4b301538a7cde431bc57619049f36e5ff8ff26fb814090148b2"
D2_MANIFEST_PATH = REPO_ROOT / (
    "tests/fixtures/source_to_knowledge/minecraft_esports/enrichment/manifest.v0.1.json"
)
D2_MANIFEST_SHA256 = "6612b10d8ded2db62eea67f7504c3fd39c6b1d65bcf9001703728a3007305ab3"
RUNNER_PATH = REPO_ROOT / "scripts/cp_tools/run_minecraft_esports_enrichment.py"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(item[key]): item for item in items}


def test_d1_d2_bindings_are_fixed_and_synthetic() -> None:
    scenario = _load_json(SCENARIO_PATH)
    manifest = _load_json(D2_MANIFEST_PATH)

    assert _sha256(SCENARIO_PATH) == SCENARIO_SHA256
    assert _sha256(D2_MANIFEST_PATH) == D2_MANIFEST_SHA256
    assert scenario["scenario_ref"] == "GT-S2K-ENRICHMENT-01"
    assert scenario["scenario_version"] == "0.8"
    assert scenario["work_package_ref"] == "CPKS-WP-003@0.2"
    assert scenario["sensitivity"] == "synthetic_non_sensitive"
    assert "CPKS-SPEC-KM-PU@0.2" in scenario["rule_basis"]
    assert "CPKS-SPEC-KPR@0.3" in scenario["rule_basis"]
    assert "CPKS-SPEC-KM-PU@0.1" not in scenario["rule_basis"]
    assert "CPKS-SPEC-KPR@0.2" not in scenario["rule_basis"]
    assert manifest["scenario_ref"] == "GT-S2K-ENRICHMENT-01@0.8"
    assert manifest["work_package_ref"] == "CPKS-WP-003@0.2"
    assert manifest["sensitivity"] == "synthetic_non_sensitive"
    assert manifest["d1_expected_sha256"] == SCENARIO_SHA256

    for item in manifest["source_fixtures"] + manifest["reused_existing_inputs"]:
        path = REPO_ROOT / item["path"]
        assert path.is_file(), f"Missing D2 fixture: {item['path']}"
        assert _sha256(path) == item["sha256"], f"Fixture hash changed: {item['path']}"


def test_d2_cases_keep_material_delta_boundaries_separate() -> None:
    manifest = _load_json(D2_MANIFEST_PATH)
    cases = manifest["cases"]

    evidence = cases["same_proposition_new_evidence"]
    assert evidence["incoming_source_ref"] == "DOC-07"
    assert evidence["expected"]["material_evidence_coverage_delta"] is True
    assert evidence["expected"]["semantic_change_operation"] == "update_evidence_basis"
    assert evidence["expected"]["resolution_type"] == "revise_existing_identity"

    conflict = cases["conflict_uncertainty"]
    assert conflict["incoming_source_ref"] == "DOC-08"
    assert conflict["expected"]["semantic_change_operation"] == "register_conflict"
    assert conflict["expected"]["automatic_winner_or_resolution"] is False

    replay = cases["no_material_change_same_evidence_replay"]
    assert replay["incoming_source_ref"] == "DOC-05"
    assert replay["expected"]["material_delta"] is False
    assert replay["expected"]["knowledge_finding"] is False
    assert replay["expected"]["change_candidate"] is False
    assert replay["expected"]["new_knowledge_object_version"] is False

    correction = cases["correct_same_object_boundary"]
    assert correction["incoming_source_ref"] == "DOC-09"
    assert correction["expected"]["semantic_change_operation"] == "correct"
    assert correction["expected"]["resolution_type"] == "create_new_identity"
    assert correction["expected"]["claim_value_overwrite_in_place"] is False


def test_hr004_inputs_are_preserved_and_kf_d09_does_not_invent_event_time() -> None:
    scenario = _load_json(SCENARIO_PATH)
    deltas = _index(scenario["golden_deltas"], "ref")

    assert deltas["KF-D09"]["evidence_source_ref"] == "DOC-04"
    assert deltas["KF-D09"]["source_time"] == "2024-12-18T16:00:00+01:00"
    assert deltas["KF-D09"]["event_time"] is None
    assert (
        "source_time_equals_exact_event_time"
        in deltas["KF-D09"]["prohibited_inferences"]
    )

    assert scenario["input_state"]["continuation_scenario_ref"] == (
        "GT-S2K-CONTINUATION-01@0.2"
    )
    assert scenario["input_state"]["content_reads"] == ["DOC-04", "DOC-05"]
    assert scenario["input_state"]["write_back"] is False


def test_hr005_enrichment_frontier(tmp_path: Path) -> None:
    scenario = _load_json(SCENARIO_PATH)
    manifest = _load_json(D2_MANIFEST_PATH)

    assert RUNNER_PATH.is_file(), (
        "HR-005 executable frontier runner missing: "
        "scripts/cp_tools/run_minecraft_esports_enrichment.py. "
        "This is the expected RED capability gap before D3-D9 implementation."
    )

    runner = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--output-root", str(tmp_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert runner.returncode == 0, (
        "HR-005 enrichment runner failed.\n"
        f"stdout:\n{runner.stdout}\n"
        f"stderr:\n{runner.stderr}"
    )

    result_path = tmp_path / "result.json"
    assert result_path.is_file(), f"Runner did not produce {result_path}"
    result = _load_json(result_path)

    assert result["result_format_version"] == "0.1"
    assert result["scenario_ref"] == scenario["scenario_ref"]
    assert result["scenario_version"] == scenario["scenario_version"]
    assert result["outcome"] == "pass"

    # D3/D4: material Findings and atomic Change Candidates.
    findings = _index(result["findings"], "golden_delta_ref")
    candidates = _index(result["change_candidates"], "golden_delta_ref")
    expected_deltas = _index(scenario["golden_deltas"], "ref")
    assert set(findings) == set(expected_deltas)
    assert candidates, (
        "HR-005 D4 Change Candidate capability missing: D3 Findings are present "
        "and valid, but no Change Candidates were produced. This is the expected "
        "RED capability gap after D3 implementation."
    )
    assert set(candidates) == set(expected_deltas)
    for ref, expected in expected_deltas.items():
        finding = findings[ref]
        candidate = candidates[ref]
        assert finding["non_canonical"] is True
        assert finding["material_delta"] is True
        assert finding["source_ref"] == expected["evidence_source_ref"]
        assert finding["evidence_refs"], f"{ref}: missing Evidence provenance"
        assert candidate["non_canonical"] is True
        assert candidate["candidate_revision_ref"]
        assert candidate["change_candidate_ref"]
        assert candidate["candidate_revision_ref"] != candidate["change_candidate_ref"]
        assert candidate["identity_scope"] == "implementation_local_non_canonical"
        assert candidate["source_finding_refs"] == [finding["finding_ref"]]
        assert set(finding["evidence_refs"]).issubset(candidate["evidence_refs"])
        assert (
            candidate["semantic_change_operation"]
            == expected["semantic_change_operation"]
        )
        assert candidate["proposed_semantic_effect"] == expected["proposed_effect"]
        assert candidate["primary_operation_count"] == 1
        assert "resolution_ref" not in candidate
        assert "resolution_type" not in candidate
        assert "review_requirement_set" not in candidate
        assert "policy_decision" not in candidate
        assert "publication_change_set" not in candidate

    assert findings["KF-D09"]["event_time"] is None
    assert candidates["KF-D09"]["time"] == {
        "event_time_values": [],
        "event_time_unknown": True,
    }
    assert (
        "preserve_together:promising_after_school+not_ready_for_classroom"
        in candidates["KF-D05"]["preservation_constraints"]
    )
    assert set(candidates["KF-D07"]["prohibited_inferences"]) == {
        "permanently_rejected",
        "later_introduced",
    }
    assert set(candidates["KF-D08"]["prohibited_inferences"]) == {
        "permanently_excluded",
        "later_approved",
        "later_participated",
    }

    # D2 executable cases: evidence-only, conflict, no-delta and Correct boundary.
    special = result["special_cases"]
    expected_special = manifest["cases"]
    evidence = special["D2-EVIDENCE-01"]
    evidence_expected = expected_special["same_proposition_new_evidence"]["expected"]
    assert evidence["finding"] is not None
    assert (
        evidence["change_candidate"]["semantic_change_operation"]
        == (evidence_expected["semantic_change_operation"])
    )
    assert set(evidence["change_candidate"]["evidence_refs"]) == set(
        evidence_expected["all_evidence_provenance_preserved"]
    )
    assert "resolution_type" not in evidence["change_candidate"]

    conflict = special["D2-CONFLICT-01"]
    conflict_expected = expected_special["conflict_uncertainty"]["expected"]
    assert (
        conflict["change_candidate"]["semantic_change_operation"]
        == (conflict_expected["semantic_change_operation"])
    )
    assert set(conflict["change_candidate"]["evidence_refs"]) == set(
        conflict_expected["all_evidence_provenance_preserved"]
    )
    assert conflict["prior_assertion_preserved"] is True
    assert conflict["conflicting_assertion_preserved"] is True
    assert conflict["automatic_winner_or_resolution"] is False
    assert "resolution_type" not in conflict["change_candidate"]

    assert special["D2-NOMAT-01"]["finding"] is None
    assert special["D2-NOMAT-01"]["change_candidate"] is None

    correction = special["D2-CORRECT-01"]
    correction_expected = expected_special["correct_same_object_boundary"]["expected"]
    assert (
        correction["change_candidate"]["semantic_change_operation"]
        == (correction_expected["semantic_change_operation"])
    )
    assert correction["change_candidate"]["proposed_semantic_payload"]["value"] == 14
    assert correction["claim_value_overwrite_in_place"] is False
    assert "resolution_type" not in correction["change_candidate"]

    # D5: explicit Core Same-Object assessments and one KPR Resolution Decision
    # per immutable positive Candidate Revision.
    lifecycle = _index(result["lifecycle_candidates"], "golden_delta_ref")
    assessments = _index(result["same_object_assessments"], "golden_delta_ref")
    resolutions = _index(result["resolutions"], "golden_delta_ref")
    requirement_sets = _index(result["review_requirement_sets"], "golden_delta_ref")
    readiness = _index(result["candidate_review_readiness"], "golden_delta_ref")
    assert set(lifecycle) == set(expected_deltas)
    assert set(assessments) == set(expected_deltas)
    assert set(resolutions) == set(expected_deltas)
    assert set(requirement_sets) == set(expected_deltas)
    assert set(readiness) == set(expected_deltas)

    expected_resolution_types = {
        "KF-D01": "revise_existing_identity",
        **{ref: "create_new_identity" for ref in expected_deltas if ref != "KF-D01"},
    }
    for ref in expected_deltas:
        registered = lifecycle[ref]
        assessment = assessments[ref]
        resolution = resolutions[ref]
        assert (
            registered["source_change_candidate_ref"]
            == (candidates[ref]["change_candidate_ref"])
        )
        assert (
            registered["source_change_candidate_revision_ref"]
            == (candidates[ref]["candidate_revision_ref"])
        )
        assert registered["candidate_ref"] != candidates[ref]["change_candidate_ref"]
        assert registered["non_canonical"] is True
        assert assessment["candidate_ref"] == registered["candidate_ref"]
        assert (
            assessment["candidate_revision_ref"]
            == (registered["candidate_revision_ref"])
        )
        assert assessment["rule_basis_refs"] == ["CPKS-SPEC-KM@0.20#9"]
        assert resolution["golden_resolution_ref"] == ref.replace("KF-", "RES-")
        assert resolution["resolution_type"] == expected_resolution_types[ref]
        assert resolution["candidate_ref"] == registered["candidate_ref"]
        assert (
            resolution["candidate_revision_ref"]
            == (registered["candidate_revision_ref"])
        )
        assert (
            resolution["same_object_assessment"]
            == (assessment["same_object_assessment_ref"])
        )
        assert resolution["decision_authority_context"] == (
            "synthetic_hr005_test_projection"
        )
        assert resolution["decision_authority_kind"] == (
            "scenario_local_owner_decision_basis"
        )
        assert resolution["publication_status"] == "not_performed"
        assert registered["candidate_ref"] not in resolution["target_canonical_refs"]
        assert (
            candidates[ref]["change_candidate_ref"]
            not in (resolution["target_canonical_refs"])
        )

    assert assessments["KF-D01"]["result"] == "same_identity"
    assert resolutions["KF-D01"]["target_canonical_refs"] == ["EVT-INTERNAL-PILOT"]
    assert "new_pilot_event_identity" in candidates["KF-D01"]["prohibited_inferences"]
    for ref in expected_deltas.keys() - {"KF-D01"}:
        assert assessments[ref]["result"] == "new_identity_required"
    assert resolutions["KF-D09"]["target_canonical_refs"] == ["TEST-EVT-HR005-D09"]
    assert "exact_event_time" in assessments["KF-D09"]["assessed_dimensions"]
    assert (
        "exact_event_time" not in assessments["KF-D09"]["changed_identity_dimensions"]
    )

    planned = result["planned_knowledge_version"]
    assert planned == {
        "stable_knowledge_object_ref": "KO-GT-ME-ESPORTS-PILOT",
        "prior_knowledge_object_version_ref": "KO-GT-ME-ESPORTS-PILOT@0.1",
        "prior_publication_state": "unpublished",
        "planned_target_knowledge_object_version_ref": ("KO-GT-ME-ESPORTS-PILOT@0.2"),
        "same_knowledge_object_identity": True,
        "projection_state": "planned_not_published",
        "prior_version_superseded": False,
        "source_resolution_decision_refs": [
            resolutions[ref]["resolution_decision_ref"]
            for ref in sorted(expected_deltas)
        ],
    }

    # Candidate-level reviews bind every Requirement, Request, and Record to the
    # concrete Lifecycle Candidate Revision. The records are synthetic fixtures,
    # never assertions of a real Human/Owner/Independent review.
    requests_by_delta: dict[str, list[dict[str, Any]]] = {}
    reviews_by_delta: dict[str, list[dict[str, Any]]] = {}
    for request in result["review_requests"]:
        requests_by_delta.setdefault(request["golden_delta_ref"], []).append(request)
    for review in result["reviews"]:
        reviews_by_delta.setdefault(review["golden_delta_ref"], []).append(review)

    baseline = {"technical_validation", "source_and_evidence_review"}
    expected_review_types = {
        ref: baseline | {"domain_review"} for ref in expected_deltas
    }
    expected_review_types["KF-D01"].add("entity_and_identity_review")
    for ref in expected_deltas:
        requirement_set = requirement_sets[ref]
        requirements = requirement_set["requirements"]
        review_types = {item["review_type"] for item in requirements}
        assert review_types == expected_review_types[ref]
        assert "publication_review" not in review_types
        assert requirement_set["candidate_level_only"] is True
        assert requirement_set["candidate_ref"] == lifecycle[ref]["candidate_ref"]
        assert (
            requirement_set["candidate_revision_ref"]
            == (lifecycle[ref]["candidate_revision_ref"])
        )
        assert all(item["blocking"] is True for item in requirements)
        assert all(
            item["subject_ref"] == lifecycle[ref]["candidate_ref"]
            and item["subject_version"] == lifecycle[ref]["candidate_revision_ref"]
            for item in requirements
        )

        requests = requests_by_delta[ref]
        reviews = reviews_by_delta[ref]
        assert {item["review_type"] for item in requests} == review_types
        assert {item["review_type"] for item in reviews} == review_types
        request_by_ref = _index(requests, "review_request_ref")
        for review in reviews:
            request = request_by_ref[review["review_request_ref"]]
            assert review["subject_ref"] == request["subject_ref"]
            assert review["subject_version"] == request["subject_version"]
            assert review["review_scope"] == request["review_scope"]
            assert review["result"] == "passed"
            assert review["synthetic_test_fixture"] is True
            assert review["asserted_effects"] == []
            assert review["selects_conflict_winner"] is False
            assert review["record_hash"]

        assert readiness[ref]["ready"] is True
        assert readiness[ref]["reason_code"] == (
            "candidate_review_requirements_satisfied"
        )
        assert readiness[ref]["readiness_scope"] == "candidate_review_readiness"
        assert readiness[ref]["publication_package_review_readiness"] is False

    assert result["review_orchestration"] == {
        "scope": "candidate_level_only",
        "real_human_review_claimed": False,
        "record_evidence_class": "synthetic_test_review_fixture",
    }

    # D5 special cases preserve the D2/D4 meaning and do not backfill a Candidate
    # for the no-material-delta case.
    evidence_d5 = evidence["d5"]
    assert evidence_d5["same_object_assessment"]["result"] == "same_identity"
    assert evidence_d5["resolution"]["resolution_type"] == ("revise_existing_identity")
    assert evidence_d5["planned_knowledge_version"]["new_version_required"] is True
    assert set(evidence_d5["lifecycle_candidate"]["evidence_refs"]) == set(
        evidence_expected["all_evidence_provenance_preserved"]
    )

    conflict_d5 = conflict["d5"]
    assert conflict_d5["same_object_assessment"]["result"] == ("new_identity_required")
    assert conflict_d5["resolution"]["resolution_type"] == "create_new_identity"
    conflict_review_types = {
        item["review_type"]
        for item in conflict_d5["review_requirement_set"]["requirements"]
    }
    assert "independent_quality_review" in conflict_review_types
    assert conflict["automatic_winner_or_resolution"] is False

    assert special["D2-NOMAT-01"]["d5"] == {
        "resolution": None,
        "planned_knowledge_version": None,
        "review_requirement_set": None,
        "reason_code": "no_d4_candidate_no_d5_resolution_required",
    }

    correction_d5 = correction["d5"]
    assert correction_d5["same_object_assessment"]["result"] == (
        "new_identity_required"
    )
    assert correction_d5["resolution"]["resolution_type"] == ("create_new_identity")
    assert correction_d5["planned_knowledge_version"]["prior_version_effect"] == (
        "unchanged"
    )

    # D6: every isolated material Candidate/Resolution pair owns one atomic,
    # immutable package containing an unpublished PU assembled by the existing
    # source-neutral PublicationUnitAssembler.
    change_sets = _index(result["publication_change_sets"], "golden_delta_ref")
    units = _index(result["publication_units"], "golden_delta_ref")
    packages = _index(result["publication_packages"], "golden_delta_ref")
    publication_reviews = _index(result["publication_reviews"], "golden_delta_ref")
    policy_evaluations = _index(result["policy_evaluations"], "golden_delta_ref")
    policy_decisions = _index(
        result["technical_test_policy_decisions"], "golden_delta_ref"
    )
    g5_results = _index(result["g5_results"], "golden_delta_ref")
    g6_results = _index(result["g6_results"], "golden_delta_ref")
    finalization_plans = _index(
        result["publication_finalization_plans"], "golden_delta_ref"
    )
    publication_requests = _index(result["publication_requests"], "golden_delta_ref")
    publication_executions = _index(
        result["publication_executions"], "golden_delta_ref"
    )
    publication_records = _index(result["publication_records"], "golden_delta_ref")
    final_units = _index(result["final_publication_units"], "golden_delta_ref")
    rebuild_conformance = _index(
        result["per_candidate_publication_bound_rebuild_conformance"],
        "golden_delta_ref",
    )
    for collection in (
        change_sets,
        units,
        packages,
        publication_reviews,
        policy_evaluations,
        policy_decisions,
        g5_results,
        g6_results,
        finalization_plans,
        publication_requests,
        publication_executions,
        publication_records,
        final_units,
        rebuild_conformance,
    ):
        assert set(collection) == set(expected_deltas)

    for ref in expected_deltas:
        change_set = change_sets[ref]
        unit = units[ref]
        package = packages[ref]
        publication_review = publication_reviews[ref]
        evaluation = policy_evaluations[ref]
        decision = policy_decisions[ref]
        assert (
            change_set["candidate_revision_ref"]
            == (lifecycle[ref]["candidate_revision_ref"])
        )
        assert (
            change_set["resolution_decision_ref"]
            == (resolutions[ref]["resolution_decision_ref"])
        )
        assert change_set["atomic"] is True
        assert change_set["state"] == "awaiting_reviews"
        assert change_set["new_publication_unit_refs"] == ["KO-GT-ME-ESPORTS-PILOT@0.2"]
        assert change_set["expected_prior_states"][0]["publication_state"] == (
            "unpublished"
        )
        assert change_set["change_set_hash"]["value"]
        operation_types = {item["operation_type"] for item in change_set["operations"]}
        assert "publish_new_version" in operation_types
        assert "supersede_version" not in operation_types
        if resolutions[ref]["resolution_type"] == "create_new_identity":
            assert "create_identity" in operation_types
        else:
            assert "create_identity" not in operation_types

        manifest = unit["manifest"]
        assert unit["assembled_by"] == "PublicationUnitAssembler"
        assert manifest["schema_ref"] == "CPKS-SPEC-KM-PU@0.2"
        assert manifest["template_ref"] == "CPKS-TPL-KM-PU@0.2"
        assert manifest["knowledge_object_id"] == "KO-GT-ME-ESPORTS-PILOT"
        assert manifest["knowledge_object_version"] == "0.2"
        assert manifest["publication"]["publication_state"] == "unpublished"
        assert manifest["publication"]["publication_record_ref"] is None
        assert manifest["canonical_path"] is None
        assert manifest["publication"]["publication_finalization_plan_ref"]
        assert manifest["integrity"]["cross_view_validation"]["status"] == "pass"
        assert manifest["evidence_links"]
        assert unit["content_hash"]["value"]
        assert unit["content_hash"]["hash_scope"] == (
            "publication_unit_knowledge_content"
        )
        assert unit["prepublication_representation_hash"]["value"]
        assert unit["cp_wiki_write_performed"] is False

        assert (
            package["candidate_revision_ref"]
            == (lifecycle[ref]["candidate_revision_ref"])
        )
        assert package["package_hash"]["value"]
        assert package["publication_performed"] is False
        assert publication_review["review_type"] == "publication_review"
        assert publication_review["subject_version"] == package["package_version_ref"]
        assert publication_review["synthetic_test_fixture"] is True
        assert publication_review["real_human_review_claimed"] is False
        assert evaluation["requested_action"] == "publish"
        assert evaluation["requested_data_operations"] == [
            "read_content",
            "transform",
            "create",
        ]
        assert (
            evaluation["publication_package_version_ref"]
            == (package["package_version_ref"])
        )
        assert decision["result"] == "permit"
        assert decision["synthetic_test_fixture"] is True
        assert decision["publication_record_created"] is False
        assert g5_results[ref]["disposition"] == "passed"
        assert g5_results[ref]["execution_authorized"] is False
        assert g6_results[ref]["disposition"] == "ready"
        assert g6_results[ref]["reason_code"] == (
            "finalization_ready_for_test_isolated_execution"
        )
        assert g6_results[ref]["execution_performed"] is False
        assert g6_results[ref]["publication_performed"] is False

        finalization_plan = finalization_plans[ref]
        publication_request = publication_requests[ref]
        execution = publication_executions[ref]
        publication_record = publication_records[ref]
        final_unit = final_units[ref]
        conformance = rebuild_conformance[ref]
        assert finalization_plan["publication_unit_ref"] == unit["publication_unit_ref"]
        assert finalization_plan["knowledge_content_hash"] == unit["content_hash"]
        assert finalization_plan["prepublication_representation_hash"] == (
            unit["prepublication_representation_hash"]
        )
        assert publication_request["publication_finalization_plan_ref"] == (
            finalization_plan["publication_finalization_plan_ref"]
        )
        assert publication_request["request_fingerprint"]
        assert execution["status"] == "published"
        assert execution["final_state_verified"] is True
        assert execution["change_set_applied"] is True
        assert execution["candidate_closed_after_publication"] is True
        assert execution["idempotency_replay_disposition"] == "idempotent_replay"
        assert execution["target_commit_count"] == 1
        assert execution["test_isolated"] is True
        assert publication_record["outcome"] == "success"
        assert publication_record["publication_request_ref"] == (
            publication_request["publication_request_ref"]
        )
        assert publication_record["publication_finalization_plan_refs"] == [
            finalization_plan["publication_finalization_plan_ref"]
        ]
        assert publication_record["knowledge_content_hashes"] == [unit["content_hash"]]
        assert publication_record["final_representation_hashes"][0]["hash_scope"] == (
            "publication_unit_final_representation"
        )
        assert final_unit["manifest"]["knowledge_object_id"] == (
            unit["knowledge_object_id"]
        )
        assert final_unit["manifest"]["knowledge_object_version"] == (
            unit["knowledge_object_version"]
        )
        assert final_unit["manifest"]["publication"]["publication_state"] == (
            "published"
        )
        assert final_unit["manifest"]["publication"]["publication_record_ref"] == (
            publication_record["publication_record_ref"]
        )
        assert conformance["status"] == (
            "publication_bound_rebuild_conformance_verified"
        )
        assert conformance["assurance_scope"] == (
            "per_candidate_technical_conformance_only"
        )
        assert conformance["publication_record_ref"] == (
            publication_record["publication_record_ref"]
        )
        assert conformance["source_publication_unit_ref"] == (
            unit["publication_unit_ref"]
        )
        assert conformance["successful_immutable_publication_record_verified"] is True
        assert conformance["exact_publication_binding_verified"] is True
        assert conformance["knowledge_content_hash_binding_verified"] is True
        assert conformance["published_state_binding_verified"] is True
        assert conformance["plan_shape"] == {
            "phase_count": 1,
            "thread_count": 1,
            "gap_count": 1,
        }
        assert conformance["first_projection_deleted"] is True
        assert conformance["deterministic_rebuild"] is True
        assert conformance["first_projection_signature"] == (
            conformance["rebuilt_projection_signature"]
        )
        assert conformance["rich_experience_acceptance_claimed"] is False
        assert conformance["derived_projection_is_canonical_source"] is False
        for forbidden_claim in (
            "projection_a",
            "projection_a_status",
            "projection_b",
            "projection_c",
            "a_differs_from_b",
            "b_semantically_equivalent_to_c",
            "experience_completeness",
            "lesson_learned_eligibility",
            "first_projection",
            "rebuilt_projection",
        ):
            assert forbidden_claim not in conformance

    conflict_unit = special["D2-CONFLICT-01"]["d6"]["publication_unit"]
    assert len(conflict_unit["manifest"]["claims"]) == 2
    assert len(conflict_unit["manifest"]["evidence_links"]) == 2
    assert conflict_unit["manifest"]["conflict_sets"][0]["preferred_claim_ref"] is None
    assert special["D2-CORRECT-01"]["d6"]["prior_version_superseded"] is False
    assert special["D2-NOMAT-01"]["d6"] == {
        "publication_change_set": None,
        "publication_unit": None,
        "publication_package": None,
        "reason_code": "no_d4_candidate_no_d6_publication_required",
    }
    assert special["D2-NOMAT-01"]["d7"] == {
        "publication_request": None,
        "publication_record": None,
        "publication": False,
        "reason_code": "no_material_candidate_no_publication_execution_required",
    }
    assert special["D2-NOMAT-01"]["d8_d9"] == {
        "publication_bound_rebuild_conformance": None,
        "reason_code": "no_success_publication_record_no_rebuild_conformance",
    }

    live = result["live_project_gate_case"]
    assert live["applicable_active_knowledge_publication_policy_proven"] is False
    assert live["publication_authority_proven"] is False
    assert live["g5"]["disposition"] == "blocked"
    assert live["g5"]["reason_code"] == (
        "applicable_knowledge_publication_policy_missing"
    )
    assert live["g6"]["disposition"] == "blocked"
    assert "publication_authority_missing" in live["g6"]["failed_requirements"]
    assert live["g7"] == "not_reached"
    assert live["publication"] is False
    assert live["publication_record"] is None
    assert live["cp_wiki_write"] is False

    pg_cases = _index(result["publication_policy_negative_cases"], "case_ref")
    assert set(pg_cases) == {f"PG-N{index:02d}" for index in range(1, 15)}
    assert all(item["status"] == "passed" for item in pg_cases.values())

    assert result["implemented_through"] == "D9"
    assert result["publication"] == {
        "status": "test_isolated_published",
        "actual_publication": True,
        "test_isolated": True,
        "canonical_write": False,
        "cp_wiki_write": False,
        "publication_record_count": len(expected_deltas),
    }
    assert result["publication_execution"] == {
        "status": "test_isolated_published",
        "all_final_states_verified": True,
        "all_replays_idempotent": True,
    }
    assert result["per_candidate_publication_bound_rebuild_conformance_summary"] == {
        "status": "publication_bound_rebuild_conformance_verified",
        "publication_bound": True,
        "all_exact_publication_bindings_verified": True,
        "all_knowledge_content_hash_bindings_verified": True,
        "all_deterministic_rebuilds": True,
        "rich_experience_acceptance_claimed": False,
    }
    assert "experience_rebuilds" not in result
    assert "experience_rebuild" not in result

    # WI-008 / TECH-EXP-01: the dedicated cumulative D8/D9 acceptance case
    # proves a semantic A→B progression while preserving the isolated D6/D7
    # Candidate and Publication paths asserted above.
    expected_experience = scenario["experience_rebuild_acceptance"]
    acceptance = result["cumulative_experience_acceptance"]
    projection_a = acceptance["projection_a"]
    projection_b = acceptance["projection_b"]
    projection_c = acceptance["projection_c"]
    phase_states_a = {
        item["phase_ref"]: item["status"] for item in projection_a["phases"]
    }
    phase_states_b = {
        item["phase_ref"]: item["status"] for item in projection_b["phases"]
    }
    gap_states_a = {
        item["gap_ref"]: item["status"] for item in projection_a["gaps"]
    }
    gap_states_b = {
        item["gap_ref"]: item["status"] for item in projection_b["gaps"]
    }

    assert acceptance["status"] == "rebuilt_and_rebuild_verified"
    assert acceptance["acceptance_scope"] == (
        "dedicated_cumulative_d8_d9_test_fixture"
    )
    assert acceptance["d6_d7_candidate_paths_modified"] is False
    assert acceptance["source_publication_record_refs"] == [
        publication_records[ref]["publication_record_ref"]
        for ref in sorted(expected_deltas)
    ]
    assert acceptance["publication_record"]["outcome"] == "success"
    assert acceptance["publication_record"]["immutable"] is True
    assert acceptance["test_isolated_publication_proof"] == {
        "test_isolated": True,
        "target_commit_count": 1,
        "final_state_verified": True,
        "transaction_or_commit_ref": acceptance["publication_record"][
            "transaction_or_commit_ref"
        ],
    }
    assert acceptance["source_publication_unit_ref"] == (
        "KO-GT-ME-ESPORTS-PILOT@0.2"
    )
    assert acceptance["projection_a_source"]["artifact_path"].endswith(
        "experience-v1-2-final-validated/derived/experience_projection.json"
    )
    assert acceptance["projection_a_status"] == "stale"
    assert acceptance["projection_b_deleted"] is True

    assert projection_a["experience_ref"] == expected_experience["experience_ref"]
    assert projection_a["focus_knowledge_object_ref"] == (
        "KO-GT-ME-ESPORTS-PILOT@0.1"
    )
    assert phase_states_a == expected_experience["baseline_phases"]
    assert gap_states_a == {
        gap_ref: "unresolved" for gap_ref in expected_experience["gap_states"]
    }
    assert projection_a["lesson_learned_eligibility"] == "insufficient_evidence"

    assert projection_b["experience_ref"] == expected_experience["experience_ref"]
    assert projection_b["focus_knowledge_object_ref"] == (
        "KO-GT-ME-ESPORTS-PILOT@0.2"
    )
    assert projection_b["as_of"] == expected_experience["golden_as_of"]
    assert projection_b["experience_completeness"] == (
        expected_experience["experience_completeness"]
    )
    assert phase_states_b == expected_experience["post_hr005_phases"]
    assert gap_states_b == expected_experience["gap_states"]
    assert projection_b["reuse_context"] == expected_experience["reuse_context_minimum"]
    assert {item["thread_ref"] for item in projection_b["threads"]} == {
        "scope_evaluation",
        "external_competition",
    }
    assert all(item["semantic_refs"] for item in projection_b["threads"])
    assert projection_b["lesson_learned_eligibility"] == "eligible"
    assert projection_b["lesson_learned_candidates"] == []
    assert projection_b["continuation_requirements"][0]["critical_gap_refs"] == [
        "EXP-GAP-CLASSROOM-INTEGRATION-FOLLOWUP",
        "EXP-GAP-EXTERNAL-COMPETITION-FOLLOWUP",
        "EXP-GAP-PILOT-REPETITION",
    ]

    assert acceptance["a_differs_from_b"] is True
    assert acceptance["a_b_delta_is_administrative_only"] is False
    assert set(acceptance["semantic_delta"]["changed_phase_refs"]) == {
        "execution",
        "evaluation",
        "outcome",
        "follow_up",
    }
    assert set(acceptance["semantic_delta"]["changed_gap_refs"]) == set(
        expected_experience["gap_states"]
    )
    assert acceptance["semantic_delta"]["lesson_learned_eligibility_changed"] is True
    assert acceptance["b_semantically_equivalent_to_c"] is True
    assert projection_b == projection_c
    assert acceptance["derived_projection_is_canonical_source"] is False

    runner_source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "prior_manifest = deepcopy(final_manifest)" not in runner_source
    assert "def _experience_plan(" not in runner_source
    assert '"all_a_differs_from_b"' not in runner_source
    assert runner_source.count('"a_differs_from_b"') == 1
    assert result["next_frontier"] == {
        "capability": "CPKS-WP-003 validation and handover evidence",
        "reason_code": "implementation_frontier_reached_through_d9",
    }
