from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cp_knowledge_tools.sources.human_interaction import (
    HumanSourceContext,
    capture_human_interaction_source,
)

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / (
    "tests/fixtures/source_to_knowledge/minecraft_esports/"
    "hardening/human_enrichment.v0.1.json"
)


def _interaction() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["interaction"]


def test_src_hum_01_and_03_capture_immutable_addressable_retrospective_source() -> None:
    fixture = _interaction()
    context = HumanSourceContext.from_mapping(fixture["source_context"])
    record = capture_human_interaction_source(
        **{key: value for key, value in fixture.items() if key != "source_context"},
        source_context=context,
    )

    assert record.source_context.retrospective_recollection is True
    assert len(record.content_hash) == 64
    assert record.evidence_address_ref.startswith("EA-HUM-")
    assert record.to_dict()["response_content"] == fixture["response_content"]
    with pytest.raises(FrozenInstanceError):
        record.response_content = "mutated"


def test_src_hum_01_later_input_creates_a_new_record_not_a_mutation() -> None:
    fixture = _interaction()
    context = HumanSourceContext.from_mapping(fixture.pop("source_context"))
    first = capture_human_interaction_source(**fixture, source_context=context)
    second = capture_human_interaction_source(
        **{
            **fixture,
            "interaction_ref": "INT-SYNTHETIC-RETRO-02",
            "response_content": "A later synthetic clarification.",
            "provided_at": "2026-08-20T10:00:00+02:00",
            "captured_at": "2026-08-20T10:01:00+02:00",
        },
        source_context=context,
    )

    assert first.human_interaction_source_record_ref != (
        second.human_interaction_source_record_ref
    )
    assert first.content_hash != second.content_hash
    assert first.response_content == "I do not reliably remember the exact cause."


def test_src_hum_02_direct_response_has_no_interpretation_field() -> None:
    fixture = _interaction()
    context = HumanSourceContext.from_mapping(fixture.pop("source_context"))
    record = capture_human_interaction_source(**fixture, source_context=context)

    assert "interpretation" not in record.to_dict()
    assert "system_interpretation" not in record.to_dict()


def test_real_human_source_capture_fails_closed_without_policy_references() -> None:
    fixture = _interaction()
    fixture["human_enrichment_request_ref"] = None
    fixture["knowledge_frontier_ref"] = None
    fixture["access_policy_refs"] = []
    fixture["processing_policy_refs"] = []
    context = HumanSourceContext.from_mapping(fixture.pop("source_context"))

    with pytest.raises(ValueError, match="requires explicit Policy references"):
        capture_human_interaction_source(**fixture, source_context=context)
