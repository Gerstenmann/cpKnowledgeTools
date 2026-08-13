from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = (
    REPO_ROOT
    / "tests/golden/source_to_knowledge/minecraft_esports/expected/scenario.v1.json"
)
RUNNER_PATH = (
    REPO_ROOT / "scripts/cp_tools/run_minecraft_esports_mvp.py"
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _index(items: list[dict], key: str = "gt_id") -> dict[str, dict]:
    return {item[key]: item for item in items}


def _assert_subset(
    expected: dict,
    actual: dict,
    ignored: set[str] | None = None,
) -> None:
    ignored = ignored or set()
    for key, value in expected.items():
        if key in ignored:
            continue
        assert key in actual, f"Missing key {key!r}"
        assert actual[key] == value, (
            f"{key!r}: expected {value!r}, got {actual[key]!r}"
        )


def test_fixture_bindings_are_frozen() -> None:
    scenario = _load_json(SCENARIO_PATH)

    assert scenario["scenario_ref"] == "GT-S2K-MINI-DOSSIER-01"
    assert scenario["scenario_version"] == "1.2"
    assert scenario["sensitivity"] == "synthetic_non_sensitive"

    for fixture in scenario["fixture_bindings"]:
        path = REPO_ROOT / fixture["path"]
        assert path.is_file(), f"Missing fixture: {fixture['path']}"
        assert path.stat().st_size > 0, f"Empty fixture: {fixture['path']}"
        assert _sha256(path) == fixture["sha256"], (
            f"Fixture hash changed: {fixture['path']}. "
            "Review Golden Truth and version the scenario if material."
        )

    # Bind all source-level text locators now, before implementation.
    fixture_text = {
        item["source_key"]: (REPO_ROOT / item["path"]).read_text(encoding="utf-8")
        for item in scenario["fixture_bindings"]
    }
    for evidence in scenario["evidence_addresses"]:
        text = fixture_text[evidence["source_key"]]
        for fragment in evidence["fixture_locator"]["required_fragments"]:
            assert fragment in text, (
                f"{evidence['gt_id']} cannot bind fragment {fragment!r} "
                f"in {evidence['source_key']}"
            )

    for rule in scenario["pattern_rules"]:
        assert rule["fixture_text"] in fixture_text[rule["source_key"]]


def test_source_to_knowledge_minecraft_esports_golden_case(tmp_path: Path) -> None:
    """Run the production pipeline and verify its isolated result.

    Production modules are deliberately not imported. The eventual MVP runner
    may be implemented or refactored freely as long as it emits the test-harness
    result JSON consumed here.
    """
    scenario = _load_json(SCENARIO_PATH)
    runner = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--output-root",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert runner.returncode == 0, (
        "Source-to-Knowledge runner failed.\n"
        f"stdout:\n{runner.stdout}\n"
        f"stderr:\n{runner.stderr}"
    )

    result_path = tmp_path / "result.json"
    assert result_path.is_file(), f"Runner did not produce {result_path}"

    result = _load_json(result_path)
    assert result["result_format_version"] == scenario["test_harness_contract"][
        "result_format_version"
    ]
    assert result["scenario_ref"] == scenario["scenario_ref"]
    assert result["scenario_version"] == scenario["scenario_version"]
    assert result["golden_as_of"] == scenario["golden_as_of"]
    assert result["outcome"] == "pass"

    counts = scenario["expected_counts"]

    # Source / Evidence
    source = result["source"]
    assert source["source_count"] == 3
    assert source["snapshot_count"] >= 3
    assert source["record_count"] >= 3
    assert source["all_source_identities_preserved"] is True

    evidence_index = _index(source["evidence_addresses"])
    assert len(evidence_index) >= counts["fixed_evidence_addresses_min"]
    for expected in scenario["evidence_addresses"]:
        actual = evidence_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Evidence Address {expected['gt_id']}"
        assert actual["source_key"] == expected["source_key"]
        assert actual["resolvable"] is True

    # Semantic
    semantic = result["semantic"]

    candidate_boundary = semantic["candidate_boundary"]
    assert candidate_boundary["candidate_count"] > 0
    assert candidate_boundary["known_gaps"] == []
    candidate_artifact = tmp_path / candidate_boundary["artifact_path"]
    assert candidate_artifact.is_file()
    assert _load_json(candidate_artifact)["candidate_payloads"] == (
        candidate_boundary["candidate_payloads"]
    )
    candidates_by_rule = {
        item["interpretation_rule_ref"]: item
        for item in candidate_boundary["candidate_payloads"]
    }
    assert candidates_by_rule["training_initial_date"]["proposed_claim"]["value"] == (
        "2024-09-19"
    )
    assert candidates_by_rule["training_current_date"]["proposed_claim"]["value"] == (
        "2024-09-26"
    )
    assert candidates_by_rule["capacity_initial_estimate"]["proposed_claim"][
        "value"
    ] == 20
    assert candidates_by_rule["capacity_confirmed_maximum"]["proposed_claim"][
        "value"
    ] == 16
    training_provenance = candidates_by_rule["training_current_date"][
        "producer_provenance"
    ]
    assert training_provenance["extraction"]["extracted_text"] == (
        "26 September 2024"
    )
    assert "predicate_ref" in training_provenance["semantic_mapping"][
        "configured_fields"
    ]
    forbidden_candidate_fields = {
        "candidate_id",
        "candidate_revision",
        "candidate_processing_state",
        "review_state",
        "publication_state",
        "policy_decision",
    }
    for candidate in candidate_boundary["candidate_payloads"]:
        assert forbidden_candidate_fields.isdisjoint(candidate)

    entity_index = _index(semantic["entities"])
    assert len(entity_index) == counts["entities_exact"]
    for expected in scenario["entities"]:
        actual = entity_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Entity {expected['gt_id']}"
        assert actual["label"] == expected["label"]

    claim_index = _index(semantic["claims"])
    assert len(claim_index) >= counts["fixed_claims_min"]
    assert sum(item["relationship"] for item in semantic["claims"]) >= counts[
        "relational_claims_min"
    ]
    for expected in scenario["claims"]:
        actual = claim_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Claim {expected['gt_id']}"
        assert actual["epistemic_status"] == expected["final_epistemic_status"]
        assert set(expected["source_keys"]).issubset(set(actual["source_keys"]))
        if "value" in expected:
            assert actual["value"] == expected["value"]
        if "predicate_ref" in expected:
            assert actual["predicate_ref"] == expected["predicate_ref"]
        if "time_modality" in expected:
            assert actual["time_modality"] == expected["time_modality"]
        if expected.get("historical_state_must_survive"):
            assert actual["preserved"] is True
        if expected.get("must_not_be_confirmed_without_independent_evidence"):
            assert actual["epistemic_status"] != "confirmed"
        if expected.get("relationship"):
            assert actual["relationship"] is True
            assert actual["subject_gt_id"] == expected["subject_gt_id"]
            assert actual["predicate_ref"] == expected["predicate_ref"]
            assert actual["object_gt_id"] == expected["object_gt_id"]

    # Pattern-based benefit statement must remain reported.
    pattern = scenario["pattern_rules"][0]
    pattern_results = [
        c for c in semantic.get("pattern_claims", [])
        if c.get("rule_key") == pattern["rule_key"]
    ]
    assert pattern_results, "Missing pattern result for DOC-01 general benefit claim"
    for actual in pattern_results:
        assert actual["epistemic_status"] == pattern["expected_epistemic_status"]
        assert pattern["expected_evidence_role"] in actual["evidence_roles"]
        assert actual["epistemic_status"] != pattern[
            "forbidden_epistemic_status_from_this_evidence_alone"
        ]

    link_index = _index(semantic["evidence_links"])
    assert len(link_index) >= counts["fixed_evidence_links_min"]
    for expected in scenario["evidence_links"]:
        actual = link_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Evidence Link {expected['gt_id']}"
        _assert_subset(expected, actual)

    event_index = _index(semantic["events"])
    assert len(event_index) >= counts["events_min"]
    action_event_types = {
        item["event_type_ref"]
        for item in semantic["events"]
        if item["event_type_ref"].startswith(
            "cpks.vocab.profile.organizational-context.event_type."
        )
    }
    assert len(action_event_types) >= counts["organizational_action_events_min"]
    for expected in scenario["events"]:
        actual = event_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Event {expected['gt_id']}"
        for key in ("event_time", "time_precision", "time_modality"):
            assert actual[key] == expected[key]
        if "event_type_ref" in expected:
            assert actual["event_type_ref"] == expected["event_type_ref"]
        if expected.get("must_not_be_actual_without_occurrence_evidence"):
            assert actual["time_modality"] != "actual"

    participation_index = _index(semantic["participations"])
    assert len(participation_index) >= counts["event_participations_min"]
    for expected in scenario["event_participations"]:
        actual = participation_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Participation {expected['gt_id']}"
        assert actual["event_gt_id"] == expected["event_gt_id"]
        assert actual["entity_gt_id"] == expected["entity_gt_id"]
        assert actual["role"] == expected["role"]

    conflict_index = _index(semantic["conflict_sets"])
    assert len(conflict_index) >= counts["conflict_sets_min"]
    for expected in scenario["conflict_sets"]:
        actual = conflict_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Conflict Set {expected['gt_id']}"
        assert set(actual["claim_gt_ids"]) == set(expected["claim_gt_ids"])
        assert set(actual["conflict_dimensions"]) == set(
            expected["conflict_dimensions"]
        )
        assert actual["preferred_claim_gt_id"] == expected["preferred_claim_gt_id"]

    # Policy
    policy_expected = scenario["policy_case"]
    policy = result["policy"]
    assert policy["consumer"] == policy_expected["consumer"]
    assert policy["claim_read"] == policy_expected["claim_read"]["expected"]
    assert (
        policy["restricted_evidence_resolution"]
        == policy_expected["restricted_evidence_resolution"]["expected"]
    )
    assert policy["claim_read_decision"]["authorized_actions"] == ["claim_read"]
    assert policy["claim_read_evaluation"]["profile_refs"] == scenario[
        "profile_refs"
    ]
    assert (
        policy["claim_read_evaluation"]["profile_applicability_status"]
        == "resolved"
    )
    assert policy["claim_read_evaluation"]["policy_anchor_ids"] == ["PA-KO"]
    assert policy["evidence_resolution_decision"]["authorized_actions"] == []
    assert policy["evidence_resolution_evaluation"]["profile_refs"] == scenario[
        "profile_refs"
    ]
    assert (
        policy["evidence_resolution_evaluation"][
            "profile_applicability_status"
        ]
        == "resolved"
    )
    assert policy["evidence_resolution_evaluation"]["policy_anchor_ids"] == [
        "PA-RESTRICTED-EVIDENCE"
    ]
    assert policy["restricted_evidence_loader_called"] is False
    assert policy["consumer_visible_output"]["evidence_content"] is None
    consumer_view = json.dumps(policy["consumer_visible_output"], ensure_ascii=False)
    for literal in policy_expected["forbidden_leak_literals"]:
        assert literal not in consumer_view

    # Publication Unit
    publication_expected = scenario["publication_unit"]
    publication = result["publication_unit"]
    for key in (
        "knowledge_object_id",
        "knowledge_object_version",
        "primary_kind",
        "knowledge_functions",
        "publication_state",
        "canonical_path",
        "publication_record_ref",
        "published_at",
        "publisher_ref",
        "schema_ref",
        "semantic_model_ref",
        "vocabulary_set_ref",
        "cross_view_validation",
    ):
        assert publication[key] == publication_expected[key]
    assert publication["profile_refs"] == publication_expected["profile_refs"]

    # Retrieval
    retrieval_index = _index(result["retrieval"], key="query_key")
    for expected in scenario["retrieval_cases"]:
        actual = retrieval_index.get(expected["query_key"])
        assert actual is not None, f"Missing retrieval case {expected['query_key']}"
        rendered = actual["rendered_answer"]
        expected_outcome = expected.get("expected_outcome", "results")
        expected_claims = set(
            expected.get("required_current_claim_gt_ids", ())
        ) | set(expected.get("required_claim_gt_ids", ()))
        assert set(actual["claim_keys"]) == expected_claims
        assert set(expected.get("required_event_gt_ids", ())).issubset(
            actual["event_keys"]
        )
        assert set(expected.get("required_participation_gt_ids", ())).issubset(
            actual["participation_keys"]
        )
        if expected_claims:
            assert actual["actual_claim_refs"]
        assert actual["publication_unit_ref"] == {
            "subject_type": "knowledge_object",
            "stable_id": publication_expected["knowledge_object_id"],
            "version": publication_expected["knowledge_object_version"],
            "authority_context": "Semantic Core",
        }
        assert actual["projection_ref"].startswith("DRP-")
        structured = actual["structured_result"]
        assert structured["outcome"] == expected_outcome
        assert structured["profile_refs"] == scenario["profile_refs"]
        assert structured["knowledge_valid_time"] == [
            {
                "role": "valid_time",
                "value_kind": "instant",
                "precision": "minute",
                "modality": "actual",
                "start": scenario["golden_as_of"],
                "end": None,
                "timezone": "+02:00",
                "approximate": False,
                "uncertainty": None,
                "source_ref": None,
            }
        ]
        assert structured["policy_decision_ref"] == policy[
            "claim_read_decision"
        ]["policy_decision_ref"]
        assert structured["evidence_content_resolved"] is False
        for item in structured["claim_items"]:
            assert item["subject_ref"]["stable_id"] in actual[
                "actual_claim_refs"
            ]
            assert item["evidence_content_resolved"] is False
        for item in (
            *structured["event_items"],
            *structured["participation_items"],
        ):
            assert item["evidence_content_resolved"] is False

        for text in expected.get("must_contain", []):
            assert text in rendered
        for text in expected.get("must_not_contain", []):
            assert text not in rendered
        for text in expected.get("must_not_present_as_current", []):
            assert text not in actual.get("current_state_text", "")
        if expected.get("must_preserve_reported_status"):
            assert actual["epistemic_status"] == "reported"
        if "evidence_resolution" in expected:
            assert actual["evidence_resolution"] == expected["evidence_resolution"]
        if expected.get("must_not_claim_actual_occurrence"):
            assert actual.get("claims_actual_occurrence", False) is False

    relationship_claims = [
        item for item in semantic["claims"] if item["relationship"]
    ]
    assert {item["gt_id"] for item in relationship_claims} == {
        item["gt_id"]
        for item in scenario["claims"]
        if item.get("relationship")
    }
    assert all(
        item["predicate_ref"].startswith(
            "cpks.vocab.profile.organizational-context.relationship_predicate."
        )
        for item in relationship_claims
    )
    predicates = {item["predicate_ref"] for item in semantic["claims"]}
    assert not any(predicate.endswith(".employed_by") for predicate in predicates)
    assert not any(predicate.endswith(".represents") for predicate in predicates)
    assert not any(
        predicate.endswith((".legal_liability", ".financial_liability"))
        for predicate in predicates
    )
    decision_makers = [
        item
        for item in semantic["participations"]
        if item["role"].endswith(".decision_maker")
    ]
    assert [item["entity_gt_id"] for item in decision_makers] == ["ENT-RMIS"]
    action_events = {
        item["gt_id"]: item for item in semantic["events"]
    }
    assert action_events["EVT-PILOT-DECISION"]["actual_event_ref"] != (
        action_events["EVT-PILOT-STATUS-CONFIRMATION"]["actual_event_ref"]
    )
    assert action_events["EVT-PILOT-STATUS-CONFIRMATION"][
        "actual_event_ref"
    ] != action_events["EVT-PILOT-STATUS-COMMUNICATION"]["actual_event_ref"]
    assert not any(
        item["event_type_ref"].endswith(".coordination")
        and item["time_modality"] == "actual"
        for item in semantic["events"]
    )
    relationship_refs = {
        item["actual_claim_ref"] for item in relationship_claims
    }
    authorized_subjects = {
        item["stable_id"]
        for item in policy["claim_read_decision"]["authorized_subject_refs"]
    }
    assert relationship_refs.isdisjoint(authorized_subjects)
    assert policy["evidence_resolution_decision"]["authorized_subject_refs"] == []

    # HR-003 Experience (#46-60)
    experience_expected = scenario["experience"]
    experience = result["experience"]
    assert experience["experience_ref"] == experience_expected["experience_ref"]
    assert experience["projection_count"] == counts[
        "experience_projections_exact"
    ]
    assert experience["focus_knowledge_object_ref"] == experience_expected[
        "focus_knowledge_object_ref"
    ]
    assert experience["as_of"] == experience_expected["as_of"]
    assert experience["completeness"] == experience_expected[
        "experience_completeness"
    ]
    assert experience["projection_ref"].startswith("EXPP-")
    assert experience["semantic_hash"]
    assert experience["artifact_path"] == "derived/experience_projection.json"
    experience_artifact = tmp_path / experience["artifact_path"]
    assert experience_artifact.is_file()
    assert "experience" not in _load_json(
        tmp_path / "derived/retrieval_projection.json"
    )
    publication_text = (tmp_path / publication["artifact_path"]).read_text(
        encoding="utf-8"
    )
    publication_frontmatter = publication_text.split("\n---\n", 1)[0]
    assert "\nexperience:" not in publication_frontmatter

    phase_index = _index(experience["phases"], key="phase_ref")
    assert {
        phase_ref: phase["status"] for phase_ref, phase in phase_index.items()
    } == {
        phase["phase_ref"]: phase["status"]
        for phase in experience_expected["phases"]
    }
    assert all(
        phase_index[phase_ref]["semantic_basis_refs"]
        and phase_index[phase_ref]["evidence_refs"]
        for phase_ref in ("context", "intent", "proposal", "decision", "scope")
    )
    assert phase_index["execution"]["status"] == "unresolved"
    internal_pilot = event_index["EVT-INTERNAL-PILOT"]
    assert internal_pilot["time_modality"] == "planned"
    assert not any(
        item["event_type_ref"] == "cpkt.test.event_type.pilot_evaluation"
        and item["time_modality"] == "actual"
        for item in semantic["events"]
    )

    experience_threads = _index(experience["threads"], key="thread_ref")
    for expected in experience_expected["threads"]:
        assert experience_threads[expected["thread_ref"]][
            "semantic_gt_refs"
        ] == expected["semantic_gt_refs"]
    scope_thread = experience_threads["scope_evaluation"]["semantic_gt_refs"]
    assert scope_thread == [
        "CLM-SCOPE-OPEN",
        "CLM-SCOPE-AFTERSCHOOL",
        "CLM-ACADEMIC-DEFERRED",
        "CLM-CLASSROOM-INTEGRATION-DEPENDS-ON-PILOT-EVALUATION",
    ]

    gap_index = _index(experience["gaps"], key="gap_ref")
    assert len(gap_index) >= counts["experience_gaps_min"]
    for expected in experience_expected["gaps"]:
        actual = gap_index[expected["gap_ref"]]
        assert actual["status"] == expected["status"] == "unresolved"
        assert actual["phase_ref"] == expected["phase_ref"]
        assert actual["semantic_basis_refs"]
        assert actual["semantic_basis_gt_refs"]
    assert not any(
        "success" in item["question"].lower()
        and item["status"] != "unresolved"
        for item in experience["gaps"]
    )

    assert experience["reuse_context"] == experience_expected["reuse_context"]
    assert len(experience["continuation_requirements"]) >= counts[
        "continuation_retrieval_requirements_min"
    ]
    continuation = experience["continuation_requirements"][0]
    continuation_expected = experience_expected["continuation_requirement"]
    assert continuation["continuation_ref"] == continuation_expected[
        "continuation_ref"
    ]
    assert continuation["status"] == continuation_expected["status"]
    assert continuation["critical_gap_refs"] == continuation_expected[
        "critical_gap_refs"
    ]
    assert continuation["search_after"] == continuation_expected["search_after"]
    assert set(continuation["trigger_purposes"]) == set(
        continuation_expected["trigger_purposes"]
    )
    assert experience["lesson_learned_eligibility"] == (
        experience_expected["lesson_learned_eligibility"]
    )
    assert len(experience["lesson_learned_candidates"]) == counts[
        "lesson_learned_candidates_exact"
    ]
    assert publication["primary_kind"] == "event_summary"

    experience_retrieval = _index(
        result["experience_retrieval"], key="query_key"
    )
    assert set(experience_retrieval) == set(
        experience_expected["retrieval_cases"]
    )
    assert all(
        item["outcome"] == "results"
        and item["policy_decision_ref"]
        == policy["claim_read_decision"]["policy_decision_ref"]
        and item["evidence_content_resolved"] is False
        for item in experience_retrieval.values()
    )
    assert experience_retrieval["pilot_evaluation"]["items"] == [
        phase_index["evaluation"]
    ]
    assert experience_retrieval["pilot_outcome"]["items"] == [
        phase_index["outcome"]
    ]
    assert experience_retrieval["classroom_integration_followup"]["items"] == [
        gap_index["EXP-GAP-CLASSROOM-INTEGRATION-FOLLOWUP"]
    ]
    lesson_result = experience_retrieval["lesson_learned"]["items"][0]
    assert lesson_result["lesson_learned_eligibility"] == (
        "insufficient_evidence"
    )
    assert lesson_result["lesson_learned_candidates"] == []
    similar = experience_retrieval["similar_experience"]["items"][0]
    assert similar["experience_ref"] == experience["experience_ref"]
    assert similar["experience_completeness"] == "partial"
    assert any(
        phase["phase_ref"] == "outcome" and phase["status"] == "unresolved"
        for phase in similar["phases"]
    )

    # Rebuild
    rebuild_expected = scenario["rebuild"]
    rebuild = result["rebuild"]
    assert rebuild["derived_state_deleted"] is True
    assert rebuild["rebuild_success"] is True
    assert rebuild["semantic_equivalent"] is True
    assert (
        rebuild["retrieval_result_signatures_before"]
        == rebuild["retrieval_result_signatures_after"]
    )
    assert rebuild["experience_projection_hash_before"] == rebuild[
        "experience_projection_hash_after"
    ]
    assert (
        rebuild["experience_retrieval_result_signatures_before"]
        == rebuild["experience_retrieval_result_signatures_after"]
    )
    for key in rebuild_expected["must_preserve"]:
        assert rebuild["preserved"][key] is True
