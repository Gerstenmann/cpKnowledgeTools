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
    assert scenario["scenario_version"] == "1.0"
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

    entity_index = _index(semantic["entities"])
    assert len(entity_index) == counts["entities_exact"]
    for expected in scenario["entities"]:
        actual = entity_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Entity {expected['gt_id']}"
        assert actual["label"] == expected["label"]

    claim_index = _index(semantic["claims"])
    assert len(claim_index) >= counts["fixed_claims_min"]
    for expected in scenario["claims"]:
        actual = claim_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Claim {expected['gt_id']}"
        assert actual["epistemic_status"] == expected["final_epistemic_status"]
        assert set(expected["source_keys"]).issubset(set(actual["source_keys"]))
        if "value" in expected:
            assert actual["value"] == expected["value"]
        if "time_modality" in expected:
            assert actual["time_modality"] == expected["time_modality"]
        if expected.get("historical_state_must_survive"):
            assert actual["preserved"] is True
        if expected.get("must_not_be_confirmed_without_independent_evidence"):
            assert actual["epistemic_status"] != "confirmed"

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
    for expected in scenario["events"]:
        actual = event_index.get(expected["gt_id"])
        assert actual is not None, f"Missing Event {expected['gt_id']}"
        for key in ("event_time", "time_precision", "time_modality"):
            assert actual[key] == expected[key]
        if expected.get("must_not_be_actual_without_occurrence_evidence"):
            assert actual["time_modality"] != "actual"

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

    # Retrieval
    retrieval_index = _index(result["retrieval"], key="query_key")
    for expected in scenario["retrieval_cases"]:
        actual = retrieval_index.get(expected["query_key"])
        assert actual is not None, f"Missing retrieval case {expected['query_key']}"
        rendered = actual["rendered_answer"]

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

    # Rebuild
    rebuild_expected = scenario["rebuild"]
    rebuild = result["rebuild"]
    assert rebuild["derived_state_deleted"] is True
    assert rebuild["rebuild_success"] is True
    assert rebuild["semantic_equivalent"] is True
    for key in rebuild_expected["must_preserve"]:
        assert rebuild["preserved"][key] is True
