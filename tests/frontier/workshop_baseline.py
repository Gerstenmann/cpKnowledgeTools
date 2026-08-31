"""WI-018 observation harness, not a semantic producer or product validator.

Run: python -m tests.frontier.workshop_baseline --output <run.json>
The only processing path is existing local capture/normalize/policy/resolve.
Audited product fingerprints make an absence claim stale when code changes.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cp_knowledge_tools import semantics
from cp_knowledge_tools.policy import (
    PolicyConfiguration,
    PolicyEvaluationInput,
    PolicyEvaluator,
    PolicyRule,
    PolicySubject,
    ProfileApplicability,
)
from cp_knowledge_tools.sources import CapturedSource, EvidenceAddress
from cp_knowledge_tools.sources.adapters.local_html import LocalHtmlAdapter

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "tests/fixtures/source_to_knowledge/workshop_versatility"
AUDIT = ROOT / "tests/golden/source_to_knowledge/workshop_versatility/audit.v1.json"
NOW = "2026-08-31T10:00:00+02:00"  # Frozen synthetic capture/policy context.
CONSUMER = "SYNTHETIC-WI018-READER"
PURPOSE = "synthetic_frontier_review"
ANCHOR = "PA-SYNTHETIC-WI018"
POLICY = "SYNTHETIC-WI018-LOCAL-READ"
SCOPE = "synthetic_source_resolution"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Passage:
    captured: CapturedSource
    address: EvidenceAddress
    content: str


def resolve_local(
    captured: CapturedSource, address: EvidenceAddress, *, effect: str = "permit"
) -> str | None:
    """Real policy and Source boundary; synthetic authority only, no external use."""
    subjects = (
        PolicySubject(
            "evidence_address", address.evidence_address_ref, "1", "Source and Evidence"
        ),
        PolicySubject(
            "source_snapshot", address.snapshot_ref, "1", "Source and Evidence"
        ),
    )
    operations = ("resolve_evidence", "read_content")
    evaluation = PolicyEvaluationInput(
        policy_evaluation_ref="PEVAL-SYNTHETIC-WI018",
        actor_or_consumer_ref=CONSUMER,
        purpose=PURPOSE,
        requested_operation=None,
        requested_action="resolve_evidence",
        requested_data_operations=operations,
        requested_effect_scope=SCOPE,
        subject_refs=subjects,
        policy_config_ref=f"{POLICY}@1",
        processing_zone="local_synthetic_test",
        profile_refs=(),
        profile_applicability=ProfileApplicability(resolution_status="resolved"),
        policy_anchor_ids=(ANCHOR,),
        requested_at=NOW,
        context_valid_at=NOW,
    )
    configuration = PolicyConfiguration(
        policy_ref=POLICY,
        version="1",
        status="active",
        rules=tuple(
            PolicyRule(
                policy_rule_ref=f"SYNTHETIC-WI018-{i}",
                actor_or_consumer_ref=CONSUMER,
                purpose=PURPOSE,
                requested_operation=None,
                requested_action="resolve_evidence",
                requested_data_operations=operations,
                subject_ref=subject,
                required_policy_anchor_ids=(ANCHOR,),
                effect=effect,
                reason=f"synthetic_exact_scope_{effect}",
                authorized_scope=SCOPE,
            )
            for i, subject in enumerate(subjects)
        ),
        decision_authority_ref="SYNTHETIC-TEST-POLICY-OWNER",
        valid_from="2026-08-31T09:00:00+02:00",
        valid_until="2026-08-31T11:00:00+02:00",
        synthetic_test_fixture=True,
    )
    decision = PolicyEvaluator().evaluate(evaluation, configuration)
    result = LocalHtmlAdapter().resolve_content(
        captured,
        address,
        consumer_ref=CONSUMER,
        purpose=PURPOSE,
        mode="content",
        evaluation=evaluation,
        decision=decision,
    )
    return result.content if result.status == "resolved" else None


def prepare_inputs(input_root: Path = INPUTS) -> dict[str, Passage]:
    """Only source manifest/content enters processing. No Expected/semantic rules."""
    scenario = json.loads((input_root / "scenario.v1.json").read_text())
    assert set(scenario) == {
        "scenario_id",
        "scenario_version",
        "scenario_role",
        "synthetic",
        "domain",
        "sources",
        "bounds",
        "processing",
    }, "Unexpected scenario input field; Expected belongs outside runtime input"
    assert scenario["scenario_role"] == "frontier" and scenario["synthetic"]
    bounds = scenario["bounds"]
    assert set(bounds) == {
        "source_count",
        "evidence_fragments_max",
        "candidate_payloads_max",
        "identity_questions_max",
        "known_gaps_max",
        "planned_stochastic_repetitions_per_frozen_configuration",
        "external_requests",
    }, "Unexpected bounds input field; no embedded Expected payload"
    assert set(scenario["processing"]) == {
        "current",
        "future_input_allowlist",
        "excluded_from_generator_input",
        "external_processing",
    }, "Unexpected processing input field; no embedded Expected payload"
    assert len(scenario["sources"]) == bounds["source_count"] == 3
    assert bounds["external_requests"] == 0
    passages: dict[str, Passage] = {}
    for source in scenario["sources"]:
        assert set(source) == {"source_key", "path", "language"}, (
            "Unexpected source input field; no embedded Expected payload"
        )
        path = (input_root / source["path"]).resolve()
        assert path.parent == input_root.resolve() and path.suffix == ".html"
        adapter = LocalHtmlAdapter()
        capture = adapter.capture(
            source["source_key"], path, captured_at=NOW, policy_refs=(ANCHOR,)
        )
        representation = adapter.normalize(capture)
        capture.validate()
        representation.validate()
        assert representation.contract_version == "0.2"
        assert all(
            c.status == "complete"
            for c in (
                representation.capture_coverage,
                representation.extraction_coverage,
                representation.normalization_coverage,
            )
        )
        paragraphs = [
            s for s in representation.segments if s.segment_type == "paragraph"
        ]
        assert len(paragraphs) == 3
        for i, segment in enumerate(paragraphs, 1):
            address = adapter.evidence_address_for_segment(capture, segment)
            content = resolve_local(capture, address)
            assert content is not None and content == segment.content
            key = f"{source['source_key']}:p{i}"
            assert key not in passages
            passages[key] = Passage(capture, address, content)
    assert len(passages) <= bounds["evidence_fragments_max"] == 9
    return passages


def product_inventory() -> dict[str, Any]:
    """Observe real exports/entry points, not a guessed nonexistent import name."""
    paths = sorted((ROOT / "src/cp_knowledge_tools").rglob("*.py"))
    paths.append(ROOT / "pyproject.toml")
    files = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    exports = {}
    for name in semantics.__all__:
        value = getattr(semantics, name)
        exports[name] = {
            "module": value.__module__,
            "signature": str(inspect.signature(value)),
        }
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    return {
        "product_tree_sha256": digest,
        "files": files,
        "semantic_exports": exports,
        "entry_points": project["scripts"],
        "runtime_dependencies": project["dependencies"],
    }


def baseline() -> dict[str, Any]:
    started_at = datetime.now().astimezone().isoformat()
    passages = prepare_inputs()
    inventory = product_inventory()
    # Audit is reporting evidence only. It never enters prepare_inputs or a producer.
    audit = json.loads(AUDIT.read_text())
    audit_current = inventory["product_tree_sha256"] == audit["product_tree_sha256"]
    return {
        "scenario": "workshop-versatility@1",
        "started_at": started_at,
        "completed_at": datetime.now().astimezone().isoformat(),
        "synthetic_capture_context_at": NOW,
        "evidence_kind": "self_check",
        "source_boundary_status": "green",
        "generation_status": (
            "not_executed_missing_capability"
            if audit_current
            else "requires_reinspection"
        ),
        "capability_evidence": audit
        if audit_current
        else "audited product bytes changed",
        "external_requests": 0,
        "generated_candidates": [],
        "contract_test_vectors_are_generated_candidates": False,
        "contract_verification": "separate tests/frontier/test_workshop_versatility.py",
        "input_hashes": {p.name: sha(p) for p in sorted(INPUTS.iterdir())},
        "resolved_evidence": {
            key: {"address": asdict(p.address), "content": p.content}
            for key, p in passages.items()
        },
        "inventory": inventory,
        "limits": [
            "Missing capability is a bounded inspected-code finding, not an LLM run.",
            "Dataclass vectors do not validate untrusted responses.",
            "Old Core validator bindings do not prove current full conformance.",
            "Model plausibility and business effectiveness remain unevaluated.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = baseline()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "scenario",
                    "source_boundary_status",
                    "generation_status",
                    "external_requests",
                )
            }
        )
    )
    return 0 if report["generation_status"] == "not_executed_missing_capability" else 2


if __name__ == "__main__":
    raise SystemExit(main())
