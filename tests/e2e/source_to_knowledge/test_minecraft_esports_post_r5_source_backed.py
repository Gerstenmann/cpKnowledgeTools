from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).parents[3]
FIXTURE_ROOT = ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/hardening"
MANIFEST = FIXTURE_ROOT / "source_backed_manifest.v0.1.json"
EXPECTED = ROOT / (
    "tests/golden/source_to_knowledge/minecraft_esports/hardening/"
    "expected/source_backed.v0.1.json"
)
RUNNER = ROOT / "scripts/cp_tools/run_minecraft_esports_enrichment.py"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def source_backed_result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    output_root = tmp_path_factory.mktemp("post-r5-source-backed")
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--output-root", str(output_root)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return _json(output_root / "result.json")["source_backed_post_r5"]


def test_source_backed_manifest_is_reproducible_and_annotation_free() -> None:
    manifest = _json(MANIFEST)

    assert manifest["scenario_ref"] == "GT-S2K-POSTR5-HARDENING-01@0.1"
    assert manifest["synthetic"] is True
    assert manifest["canonical"] is False
    assert manifest["runtime_semantic_annotations_used"] is False
    assert len(manifest["source_fixtures"]) == 3
    for fixture in manifest["source_fixtures"]:
        path = ROOT / fixture["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == fixture["sha256"]
        html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        assert soup.find("article") is not None
        assert soup.find("time", attrs={"datetime": fixture["source_time"]})
        assert "data-fact" not in html
        assert "rationale_for" not in html
        assert "part_of" not in html
        assert "frontier" not in html.lower()


def test_productive_interpretation_has_no_fixture_identity_or_role_hardcodes() -> None:
    production_paths = (
        ROOT / "src/cp_knowledge_tools/semantics/source_backed.py",
        ROOT / "src/cp_knowledge_tools/post_r5.py",
    )
    production_text = "\n".join(
        path.read_text(encoding="utf-8") for path in production_paths
    ).casefold()

    assert "doc-" not in production_text
    assert "minecraft" not in production_text
    assert "technical_test_role" not in production_text
    assert "tests/fixtures" not in production_text
    assert "/users/" not in production_text


def test_all_twelve_sources_enter_the_productive_processing_path(
    source_backed_result: dict[str, object],
) -> None:
    expected = _json(EXPECTED)
    accounting = source_backed_result["source_accounting"]

    assert source_backed_result["source_processing_path"] == [
        "local_html_adapter",
        "immutable_source_snapshot",
        "raw_content_reference",
        "normalized_records_and_segments",
        "passage_evidence_addressing",
        "source_backed_semantic_interpretation",
        "knowledge_frontier_derivation",
        "agent_interaction_opportunity",
        "kpr_eligibility",
    ]
    assert accounting["input_range"] == expected["required_source_range"]
    assert accounting["input_count"] == 12
    assert accounting["runtime_semantic_annotations_used"] is False
    assert all(item["record_ref"] for item in accounting["records"])
    assert all(item["evidence_address_refs"] for item in accounting["records"])


def test_source_text_yields_distinct_program_cycle_and_rationale(
    source_backed_result: dict[str, object],
) -> None:
    expected = _json(EXPECTED)["expectations"]
    knowledge = source_backed_result["knowledge"]
    program = knowledge["program_context"]
    rationale = knowledge["rationale"]

    assert program["program_ref"] != program["pilot_cycle_ref"]
    assert (
        program["implemented"]
        is expected["program_occurrence"]["proposed_program_is_implemented"]
    )
    assert program["relationship"]["predicate"] == "part_of"
    assert program["relationship_qualification"] == "proposed_model"
    assert rationale["relationship"]["predicate"] == "rationale_for"
    assert rationale["relationship"]["causality_asserted"] is False
    assert rationale["evidence_link_ids"]


def test_later_source_changes_currentness_without_inventing_a_cause(
    source_backed_result: dict[str, object],
) -> None:
    currentness = source_backed_result["knowledge"]["currentness"]

    assert currentness["ongoing_program"] is False
    assert currentness["classroom_rollout_currently_planned"] is False
    assert currentness["external_competition_current_commitment"] is False
    assert currentness["current_lead"] is False
    assert currentness["permanent_rejection"] is False
    assert currentness["historical_cause_established"] is False
    assert currentness["ownership_status"] == "unconfirmed"
    assert currentness["programme_slot_status"] == "not_scheduled"


def test_three_technical_views_preserve_perspective_before_conflict(
    source_backed_result: dict[str, object],
) -> None:
    views = source_backed_result["knowledge"]["technical_perspectives"]
    assessment = source_backed_result["knowledge"]["compatibility_assessment"]

    assert len(views) >= 3
    assert len({item["perspective"] for item in views}) >= 3
    assert len({item["observation_granularity"] for item in views}) >= 3
    assert assessment["outcome"] == "qualification_or_compatible_difference"
    assert assessment["remaining_material_incompatibility"] is False
    assert all(assessment["checks"].values())
    assert source_backed_result["knowledge"]["specialist_limits"] == {
        "universal_authority_inferred": False,
        "school_acceptance_inferred": False,
        "technical_failure_as_noncontinuation_cause_inferred": False,
    }


def test_external_originator_delivery_role_uses_cross_document_actor_context(
    source_backed_result: dict[str, object],
) -> None:
    expected = _json(EXPECTED)["expectations"]["perspective_and_granularity"]
    views = source_backed_result["knowledge"]["technical_perspectives"]
    specialist = next(
        item
        for item in views
        if item["perspective"] == expected["external_actor_perspective"]
    )

    assert specialist["actor_context"]["external"] is True
    assert specialist["actor_context"]["program_originator_or_initiator"] is True
    assert specialist["actor_context"]["delivery_provider"] is True
    assert len(specialist["actor_context"]["source_record_refs"]) >= 2
    assert (
        specialist["actor_context"]["business_interest_inferred"]
        is (expected["business_interest_inferred_from_documentary_sources"])
    )


def test_correction_frontier_and_kpr_request_remain_separate(
    source_backed_result: dict[str, object],
) -> None:
    correction = source_backed_result["knowledge"]["correction_history"]
    frontier = source_backed_result["knowledge_frontier"]
    enrichment = source_backed_result["human_enrichment"]

    assert correction["primary_value"] == 14
    assert correction["historical_value"] == 16
    assert correction["historical_claim_preserved"] is True
    assert frontier["status"] == "unresolved"
    assert frontier["actual_noncontinuation_reason_known"] is False
    assert frontier["evidence_checked_refs"]
    assert enrichment["opportunity"]["derived_from_frontier"] is True
    assert enrichment["kpr_disposition"] == "request_queued"
    assert enrichment["request"]["state"] == "queued"
    assert (
        enrichment["opportunity"]["human_enrichment_opportunity_ref"]
        != enrichment["request"]["human_enrichment_request_ref"]
    )
    assert enrichment["human_response_present"] is False
    assert "human_response" not in enrichment


def test_noncontinuation_frontier_factors_are_precise(
    source_backed_result: dict[str, object],
) -> None:
    expected = _json(EXPECTED)["expectations"]["frontier"]
    frontier = source_backed_result["knowledge_frontier"]
    factors = {item["factor"]: item for item in frontier["possible_factors"]}

    assert "ownership_or_programme_slot" not in factors
    assert set(expected["possible_factor_names"]) == set(factors)
    assert all(
        item["causal_status"] == expected["possible_factor_causal_status"]
        for item in factors.values()
    )
    assert all(item["description"] for item in factors.values())
    assert frontier["status"] == "unresolved"
    assert frontier["actual_noncontinuation_reason_known"] is False


def test_noncontinuation_request_is_retrospective_queued_and_nonblocking(
    source_backed_result: dict[str, object],
) -> None:
    expected = _json(EXPECTED)["expectations"]["human_enrichment"]
    frontier = source_backed_result["knowledge_frontier"]
    enrichment = source_backed_result["human_enrichment"]

    assert frontier["status"] == "unresolved"
    assert frontier["actual_noncontinuation_reason_known"] is False
    assert enrichment["opportunity"]["mode"] == expected["mode"]
    assert enrichment["request"]["mode"] == expected["mode"]
    assert enrichment["request"]["priority"] == expected["priority"]
    assert enrichment["request"]["blocking"] is expected["blocking"]
    assert enrichment["request"]["state"] == expected["request_state"]
