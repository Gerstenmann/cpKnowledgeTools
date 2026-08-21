from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from cp_knowledge_tools.delivery.hardening import (
    CurrentnessContext,
    DeliveryClaimProjector,
)
from cp_knowledge_tools.lifecycle.enrichment import (
    HumanEnrichmentOpportunity,
    HumanEnrichmentQueue,
    LessonLearnedLifecycle,
)
from cp_knowledge_tools.semantics.hardening import (
    ConflictCompatibilityAssessment,
    TemporalConstraint,
)
from cp_knowledge_tools.sources.human_interaction import (
    HumanSourceContext,
    capture_human_interaction_source,
)

ROOT = Path(__file__).parents[3]
GOLDEN = ROOT / (
    "tests/golden/source_to_knowledge/minecraft_esports/"
    "hardening/expected/scenario.v0.1.json"
)
FIXTURES = ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/hardening"
RUNNER = ROOT / "scripts/cp_tools/run_minecraft_esports_enrichment.py"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_d1_golden_binds_every_required_positive_and_negative_assertion() -> None:
    golden = _json(GOLDEN)

    assert golden["scenario_ref"] == "GT-S2K-POSTR5-HARDENING-01"
    assert golden["scenario_version"] == "0.1"
    assert golden["baseline_scenario_ref"] == "GT-S2K-ENRICHMENT-01"
    assert set(golden["coverage"]["semantic_fidelity"]) == {
        f"SF-{number:02d}" for number in range(1, 9)
    }
    assert set(golden["coverage"]["human_enrichment"]) == {
        f"HEQ-{number:02d}" for number in range(1, 8)
    }
    assert set(golden["coverage"]["human_source"]) == {
        f"SRC-HUM-{number:02d}" for number in range(1, 4)
    }
    assert set(golden["coverage"]["negative_assertions"]) == {
        f"NEG-{number:02d}" for number in range(1, 16)
    }


def test_neg01_through_neg15_map_to_executable_fail_closed_tests() -> None:
    golden = _json(GOLDEN)
    coverage = _json(FIXTURES / "negative_coverage.v0.1.json")

    assert set(coverage) == set(golden["coverage"]["negative_assertions"])
    assert {neg_id: item["assertion"] for neg_id, item in coverage.items()} == golden[
        "negative_expectations"
    ]
    for item in coverage.values():
        test_path = ROOT / item["test_file"]
        functions = {
            node.name
            for node in ast.walk(ast.parse(test_path.read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef)
        }
        assert item["test_function"] in functions


def test_doc04_doc08_doc09_doc05_and_doc07_bind_expected_behavior() -> None:
    cases = _json(FIXTURES / "semantic_cases.v0.1.json")["cases"]
    golden = _json(GOLDEN)["expectations"]

    conflict = ConflictCompatibilityAssessment.from_mapping(
        {
            "assessment_ref": "CCA-DOC04-DOC08",
            "claim_refs": [
                cases["perspective_qualification"]["claim_a"]["claim_ref"],
                cases["perspective_qualification"]["claim_b"]["claim_ref"],
            ],
            "checks": {key: True for key in golden["SF-07"]["compatibility_checks"]},
            "remaining_material_incompatibility": False,
            "outcome": cases["perspective_qualification"]["expected_outcome"],
        }
    )
    temporal = TemporalConstraint.from_mapping(cases["temporal_constraint"])
    current = DeliveryClaimProjector().project_current_opportunity(
        historical_claim_ref=cases["currentness"]["historical_claim_ref"],
        purpose=cases["currentness"]["purpose"],
        currentness=CurrentnessContext(status=cases["currentness"]["currentness"]),
        policy_profile_conformant=True,
    )
    correction = DeliveryClaimProjector().claim_view(
        primary_claim_ref=cases["correction_history"]["primary_claim_ref"],
        correction_history_refs=(cases["correction_history"]["historical_claim_ref"],),
    )

    assert conflict.outcome == "qualification_or_compatible_difference"
    assert temporal.certainty == "deterministic"
    assert current is None
    assert correction.primary_claim_ref == golden["SF-08"]["primary_claim_ref"]
    assert correction.correction_history_refs == tuple(
        golden["SF-08"]["correction_history_refs"]
    )
    assert (
        cases["shared_origin_evidence"]["expected_independence"]
        == (golden["SF-05"]["independence"])
    )


def test_revise_owner_unknown_and_attention_budget_form_one_controlled_path() -> None:
    fixture = _json(FIXTURES / "human_enrichment.v0.1.json")
    interaction = dict(fixture["interaction"])
    source_context = HumanSourceContext.from_mapping(interaction.pop("source_context"))
    source_record = capture_human_interaction_source(
        **interaction,
        source_context=source_context,
    )
    lifecycle = LessonLearnedLifecycle()
    candidate = lifecycle.create_candidate(
        experience_ref="EXP-SYNTHETIC-01",
        eligibility="eligible",
        semantic_payload_ref="PAYLOAD-LL-01",
        source_and_evidence_refs=("EL-EXPERIENCE",),
    )
    revised = lifecycle.revise_candidate(
        candidate,
        disposition="revise",
        human_interaction_source_record_ref=(
            source_record.human_interaction_source_record_ref
        ),
        new_semantic_payload_ref="PAYLOAD-LL-02",
    )
    queue = HumanEnrichmentQueue()
    requests = []
    for item in fixture["opportunities"]:
        opportunity = HumanEnrichmentOpportunity.from_mapping(item)
        request = queue.persist_request(opportunity)
        if request is not None:
            requests.append(request)
    closed = queue.close_with_owner_unknown(requests[0])

    assert revised.current_revision.revision == 2
    assert closed.frontier_outcome == "unchanged"
    assert len(queue.regular_batch(tuple(requests))) <= 3


def test_d9_synthetic_records_and_golden_are_isolated_from_production() -> None:
    assurance = _json(FIXTURES / "assurance_records.v0.1.json")
    production_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "src/cp_knowledge_tools").rglob("*.py"))
    ).lower()

    assert assurance["synthetic"] is True
    assert assurance["canonical"] is False
    assert assurance["review_record"]["grants_acceptance"] is False
    assert assurance["authority_record"]["grants_publication_authority"] is False
    assert assurance["publication_record"]["publication_state"] == "unpublished"
    assert "gt-s2k-postr5-hardening-01" not in production_text
    assert "minecraft" not in production_text
    assert "tests/golden" not in production_text


def test_real_source_to_knowledge_runner_materializes_post_r5_hardening(
    tmp_path: Path,
) -> None:
    runner = subprocess.run(
        [sys.executable, str(RUNNER), "--output-root", str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert runner.returncode == 0, runner.stderr

    hardening = _json(tmp_path / "result.json")["post_r5_hardening"]

    assert hardening["source_neutral_entry_point"] == (
        "cp_knowledge_tools.post_r5.run_post_r5_hardening"
    )
    assert hardening["conflict_sets"][0]["conflict_classification"] == (
        "qualification_or_compatible_difference"
    )
    assert hardening["conflict_sets"][0]["claim_refs"] == [
        "CLM-DOC04-TECHNICAL",
        "CLM-DOC08-TECHNICAL",
    ]
    assert hardening["conflict_sets"][0]["compatibility_checks"] == {
        "time_scope_checked": True,
        "context_checked": True,
        "perspective_checked": True,
        "granularity_checked": True,
        "qualification_checked": True,
    }
    assert hardening["temporal_constraints"][0]["bound_kind"] == "interval"
    assert hardening["delivery"]["current_opportunity"] is None
    assert hardening["delivery"]["correction_history_refs"] == ["CLM-CAPACITY-16"]
    assert hardening["evidence_assessments"][0]["dimensions"]["independence"] == (
        "shared_origin"
    )
    assert hardening["evidence_assessments"][0]["evidence_link_ids"] == [
        "EL-DOC05-APPROVAL",
        "EL-DOC07-APPROVAL",
    ]
    assert hardening["human_enrichment"]["persisted_request_refs"]
    assert hardening["human_source_record"]["evidence_address_ref"].startswith(
        "EA-HUM-"
    )
    assert hardening["lesson_learned_candidate"]["current_revision"]["revision"] == 2
