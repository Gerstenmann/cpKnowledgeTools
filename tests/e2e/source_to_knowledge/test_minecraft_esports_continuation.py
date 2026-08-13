from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from cp_knowledge_tools.delivery.continuation import (
    AuthorizationDecision,
    CandidateEvidence,
    CandidateMetadata,
    CandidateScope,
    ContinuationBudget,
    ContinuationExecutor,
    ContinuationRequest,
    ContinuationServices,
    PolicyContext,
)

ROOT = Path(__file__).parents[3]
SCENARIO_PATH = ROOT / (
    "tests/golden/source_to_knowledge/minecraft_esports/continuation/"
    "expected/scenario.v0.1.json"
)
BASELINE_SCENARIO_PATH = ROOT / (
    "tests/golden/source_to_knowledge/minecraft_esports/expected/scenario.v1.json"
)
BASELINE_EXPERIENCE_PATH = ROOT / (
    "artifacts/tests/source_to_knowledge/experience-v1-2-final-validated/"
    "derived/experience_projection.json"
)
BASELINE_KO_PATH = ROOT / (
    "artifacts/tests/source_to_knowledge/experience-v1-2-final-validated/"
    "publication/KO-GT-ME-ESPORTS-PILOT@0.1.md"
)
BASELINE_FIXTURE_PATHS = tuple(
    ROOT
    / "tests/fixtures/source_to_knowledge/minecraft_esports/html"
    / name
    for name in (
        "01-program-proposal.html",
        "02-school-response.html",
        "03-pilot-status.html",
    )
)


def _scenario() -> dict[str, Any]:
    return json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))


def test_scenario_fixture_hashes_are_fixed() -> None:
    scenario = _scenario()

    for candidate in scenario["candidate_sources"]:
        payload = (ROOT / candidate["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == candidate["sha256"]


def test_golden_expectations_are_not_pipeline_inputs() -> None:
    scenario = _scenario()
    scenario["golden_truth"] = {
        candidate["source_ref"]: {"resolved_gap_refs": [], "facts": {}}
        for candidate in scenario["candidate_sources"]
    }
    calls: list[str] = []
    repository = ScenarioRepository(scenario, calls)

    result = ContinuationExecutor().execute(
        _request(
            scenario,
            "standard",
            tuple(item["source_ref"] for item in scenario["candidate_sources"]),
        ),
        repository.services(),
        _authorizer(calls),
    )

    assert result.outcome == "complete"
    assert len(result.resolved_gaps) == 7


class ScenarioRepository:
    def __init__(self, scenario: dict[str, Any], calls: list[str]) -> None:
        self.scenario = scenario
        self.calls = calls
        self.paths = {
            item["source_ref"]: ROOT / item["path"]
            for item in scenario["candidate_sources"]
        }

    def discover(
        self, request: ContinuationRequest, round_index: int, limit: int
    ) -> tuple[str, ...]:
        self.calls.append("discover")
        allowed = set(request.candidate_scope.allowed_source_refs)
        return tuple(ref for ref in self.paths if ref in allowed)[:limit]

    def read_metadata(self, candidate_ref: str) -> CandidateMetadata:
        self.calls.append(f"read_metadata:{candidate_ref}")
        soup = BeautifulSoup(
            self.paths[candidate_ref].read_text(encoding="utf-8"), "html.parser"
        )
        source_time = soup.find("meta", attrs={"name": "source-time"})
        topic_terms = soup.find("meta", attrs={"name": "topic-terms"})
        assert source_time and source_time.get("content")
        assert topic_terms and topic_terms.get("content")
        return CandidateMetadata(
            candidate_ref=candidate_ref,
            source_time=str(source_time["content"]),
            topic_terms=tuple(str(topic_terms["content"]).split()),
        )

    def rank(
        self, metadata: CandidateMetadata, gap_refs: tuple[str, ...]
    ) -> float:
        self.calls.append(f"rank:{metadata.candidate_ref}")
        role = next(
            item["role"]
            for item in self.scenario["candidate_sources"]
            if item["source_ref"] == metadata.candidate_ref
        )
        return {
            "evaluation_and_outcome": 2.0,
            "follow_up_decisions": 1.0,
            "decoy": 0.0,
        }[role]

    def read_content(self, candidate_ref: str) -> str:
        self.calls.append(f"read_content:{candidate_ref}")
        return self.paths[candidate_ref].read_text(encoding="utf-8")

    def interpret(
        self,
        metadata: CandidateMetadata,
        content: str,
        gap_refs: tuple[str, ...],
    ) -> CandidateEvidence:
        self.calls.append(f"interpret:{metadata.candidate_ref}")
        soup = BeautifulSoup(content, "html.parser")
        facts = tuple(
            (str(node["data-fact"]), str(node["data-value"]))
            for node in soup.select("[data-fact][data-value]")
        )
        fact_names = {name for name, _ in facts}
        coverage_by_fact = {
            "pilot_execution": ("PILOT-EXECUTION",),
            "pilot_evaluation_occurrence": ("PILOT-EVALUATION-OCCURRENCE",),
            "coding_progression": ("PILOT-EVALUATION-RESULT",),
            "overall_assessment": ("PILOT-OUTCOME",),
            "second_after_school_cycle": ("PILOT-REPETITION",),
            "classroom_2024_25": ("CLASSROOM-INTEGRATION-FOLLOWUP",),
            "external_competition_2024_25": (
                "EXTERNAL-COMPETITION-FOLLOWUP",
            ),
        }
        covered_suffixes = {
            suffix
            for fact_name in fact_names
            for suffix in coverage_by_fact.get(fact_name, ())
        }
        resolved = tuple(
            gap_ref
            for gap_ref in gap_refs
            if any(gap_ref.endswith(suffix) for suffix in covered_suffixes)
        )
        return CandidateEvidence(
            evidence_ref=f"CE-{metadata.candidate_ref}",
            source_ref=metadata.candidate_ref,
            resolved_gap_refs=resolved,
            facts=facts,
        )

    def services(self) -> ContinuationServices:
        return ContinuationServices(
            discover=self.discover,
            read_metadata=self.read_metadata,
            rank=self.rank,
            read_content=self.read_content,
            interpret=self.interpret,
        )


def _request(
    scenario: dict[str, Any], budget_name: str, sources: tuple[str, ...]
) -> ContinuationRequest:
    budget = scenario["budget_profiles"][budget_name]
    return ContinuationRequest(
        continuation_request_ref=f"CREQ-{budget_name.upper()}",
        consumer_ref="OWNER-BUSINESS-REVIEW",
        purpose=scenario["purpose"],
        experience_ref=scenario["preserve"]["experience_ref"],
        continuation_requirement_ref=scenario["preserve"][
            "continuation_requirement_ref"
        ],
        gap_refs=tuple(scenario["preserve"]["gap_refs"]),
        search_after=scenario["golden_as_of"],
        candidate_scope=CandidateScope("MINECRAFT-CONTINUATION", sources),
        budget=ContinuationBudget(**budget),
        policy_context=PolicyContext(
            "TEST-CONTINUATION-POLICY@0.1",
            "local_synthetic_test",
            (),
            ("PA-SYNTHETIC",),
        ),
        requested_at="2026-08-13T12:00:00+02:00",
    )


def _authorizer(
    calls: list[str], deny: str | None = None
) -> Callable[[str, ContinuationRequest, str | None], AuthorizationDecision]:
    def authorize(
        operation: str,
        request: ContinuationRequest,
        candidate_ref: str | None,
    ) -> AuthorizationDecision:
        suffix = f":{candidate_ref}" if candidate_ref else ""
        calls.append(f"authorize:{operation}{suffix}")
        return AuthorizationDecision(
            permitted=operation != deny,
            policy_decision_ref=f"PDEC-{operation.upper()}-{candidate_ref or 'SCOPE'}",
            reason="synthetic_test_policy",
        )

    return authorize


def _run(
    *,
    budget_name: str = "standard",
    sources: tuple[str, ...] = ("DOC-04", "DOC-05", "DOC-06"),
    deny: str | None = None,
):
    scenario = _scenario()
    calls: list[str] = []
    repository = ScenarioRepository(scenario, calls)
    result = ContinuationExecutor().execute(
        _request(scenario, budget_name, sources),
        repository.services(),
        _authorizer(calls, deny),
    )
    return scenario, result, calls


def test_standard() -> None:
    scenario, result, _ = _run()
    expected = scenario["cases"]["standard"]

    assert result.outcome == expected["expected_outcome"]
    assert result.stop_reason == expected["expected_stop_reason"]
    assert list(result.content_reads) == expected["expected_content_reads"]
    assert len(result.resolved_gaps) == expected["expected_resolved_gap_count"]
    assert result.unresolved_gaps == ()
    assert result.lesson_learned_eligibility == expected[
        "expected_lesson_learned_eligibility"
    ]
    assert "DOC-06" not in result.content_reads
    assert result.budget_usage.candidate_sources == 3
    assert result.budget_usage.search_rounds == 1
    assert result.budget_usage.metadata_reads == 3
    assert result.budget_usage.content_reads == 2
    assert result.budget_usage.branches == 0
    assert result.budget_usage.depth == 1
    assert len(result.policy_decision_refs) == 6


def test_tight_budget() -> None:
    scenario, result, _ = _run(budget_name="tight")
    expected = scenario["cases"]["tight_budget"]

    assert result.outcome == expected["expected_outcome"]
    assert result.stop_reason == expected["expected_stop_reason"]
    assert len(result.content_reads) == expected["expected_content_read_count"]
    assert len(result.resolved_gaps) == expected["expected_resolved_gap_count"]
    assert result.unresolved_gaps
    assert result.budget_usage.content_reads == 1
    assert result.budget_usage.content_reads <= result.budget_usage.metadata_reads


def test_no_discovery_authorization() -> None:
    scenario, result, calls = _run(deny="discover")
    expected = scenario["cases"]["no_discovery_authorization"]

    assert calls == ["authorize:discover"]
    assert result.outcome == expected["expected_outcome"]
    assert result.stop_reason == expected["expected_stop_reason"]
    assert list(result.sources_discovered) == expected[
        "expected_sources_discovered"
    ]
    assert "DOC-04" not in str(result.to_dict())


def test_metadata_allowed_content_denied() -> None:
    scenario, result, calls = _run(deny="read_content")
    expected = scenario["cases"]["metadata_allowed_content_denied"]

    assert result.outcome == expected["expected_outcome"]
    assert result.stop_reason == expected["expected_stop_reason"]
    assert len(result.content_reads) == expected["expected_content_read_count"]
    assert len(result.resolved_gaps) == expected["expected_resolved_gap_count"]
    assert not any(call.startswith("read_content:") for call in calls)


def test_decoy() -> None:
    scenario, result, calls = _run(sources=("DOC-06",))
    expected = scenario["cases"]["decoy"]

    assert result.outcome == expected["expected_outcome"]
    assert result.stop_reason == expected["expected_stop_reason"]
    assert len(result.content_reads) == expected["expected_content_read_count"]
    assert len(result.resolved_gaps) == expected["expected_resolved_gap_count"]
    assert "rank:DOC-06" in calls
    assert "read_content:DOC-06" not in calls


def test_no_silent_write() -> None:
    baseline_scenario = BASELINE_SCENARIO_PATH.read_bytes()
    baseline_experience = BASELINE_EXPERIENCE_PATH.read_bytes()
    baseline_ko = BASELINE_KO_PATH.read_bytes()
    baseline_fixtures = {
        path: path.read_bytes() for path in BASELINE_FIXTURE_PATHS
    }
    scenario = _scenario()
    preserve_copy = copy.deepcopy(scenario["preserve"])

    _, result, _ = _run()

    assert result.outcome == "complete"
    assert BASELINE_SCENARIO_PATH.read_bytes() == baseline_scenario
    assert BASELINE_EXPERIENCE_PATH.read_bytes() == baseline_experience
    assert BASELINE_KO_PATH.read_bytes() == baseline_ko
    assert {
        path: path.read_bytes() for path in BASELINE_FIXTURE_PATHS
    } == baseline_fixtures
    assert scenario["preserve"] == preserve_copy
