from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from cp_knowledge_tools.derived import (
    ExperienceProjectionBuilder,
    ExperienceProjectionPlan,
    ExperienceProjectionStore,
    ExperienceReuseContext,
    PublicationBoundExperienceRebuilder,
)
from cp_knowledge_tools.lifecycle import (
    PublicationExecutor,
    TestIsolatedPublicationTarget,
)
from tests.lifecycle.test_publication_execution import _request


def _published_context():
    _, package, g6, request = _request()
    target = TestIsolatedPublicationTarget(
        expected_prior_states=package.expected_prior_states
    )
    execution = PublicationExecutor().execute(
        request=request,
        package=package,
        g6_result=g6,
        target=target,
        executed_at="2026-08-15T10:06:00+02:00",
    )
    assert execution.record is not None
    state = target.read(package.publication_finalization_plan.canonical_path)
    assert state is not None
    return state.manifest, state.markdown_body, execution.record


def _plan(version: str) -> ExperienceProjectionPlan:
    return ExperienceProjectionPlan(
        experience_ref="EXP-PUBLICATION-BOUND",
        focus_knowledge_object_ref=f"KO-TEST@{version}",
        as_of="2026-08-15T10:06:00+02:00",
        phases=(),
        threads=(),
        gaps=(),
        reuse_context=ExperienceReuseContext(
            domain_terms=("synthetic",),
            topic_terms=("publication-finalization",),
            purpose_terms=("experience-rebuild",),
        ),
    )


def test_success_record_marks_old_projection_stale_and_rebuilds_exact_version() -> None:
    manifest, markdown_body, record = _published_context()
    prior_manifest = deepcopy(manifest)
    prior_manifest["knowledge_object_version"] = "0.1"
    projection_a = ExperienceProjectionBuilder().build(prior_manifest, _plan("0.1"))
    store = ExperienceProjectionStore((projection_a,))

    rebuilt = PublicationBoundExperienceRebuilder().rebuild(
        manifest=manifest,
        markdown_body=markdown_body,
        plan=_plan("0.2"),
        publication_record=record,
        store=store,
    )

    assert rebuilt.disposition == "rebuilt"
    assert rebuilt.reason_code == "experience_rebuilt_from_published_unit"
    assert rebuilt.projection is not None
    assert rebuilt.projection.publication_unit_ref["version"] == "0.2"
    assert rebuilt.source_publication_unit_ref == "KO-TEST@0.2"
    assert rebuilt.publication_record_ref == record.publication_record_ref
    assert rebuilt.stale_projection_refs == (
        projection_a.experience_projection_ref,
    )
    assert store.status(projection_a.experience_projection_ref) == "stale"
    assert rebuilt.projection.semantic_signature() != projection_a.semantic_signature()


def test_delete_b_then_rebuild_same_published_version_produces_semantic_c() -> None:
    manifest, markdown_body, record = _published_context()
    store = ExperienceProjectionStore()
    rebuilder = PublicationBoundExperienceRebuilder()
    first = rebuilder.rebuild(
        manifest=manifest,
        markdown_body=markdown_body,
        plan=_plan("0.2"),
        publication_record=record,
        store=store,
    )
    assert first.projection is not None
    projection_b = first.projection

    assert store.delete(projection_b.experience_projection_ref) is True
    second = rebuilder.rebuild(
        manifest=manifest,
        markdown_body=markdown_body,
        plan=_plan("0.2"),
        publication_record=record,
        store=store,
    )
    assert second.projection is not None
    projection_c = second.projection

    assert projection_b.semantic_signature() == projection_c.semantic_signature()
    assert projection_b.to_dict() == projection_c.to_dict()
    assert store.status(projection_c.experience_projection_ref) == "current"


def test_rebuild_is_blocked_before_valid_success_publication_record() -> None:
    manifest, markdown_body, record = _published_context()
    prior_manifest = deepcopy(manifest)
    prior_manifest["knowledge_object_version"] = "0.1"
    projection_a = ExperienceProjectionBuilder().build(prior_manifest, _plan("0.1"))
    store = ExperienceProjectionStore((projection_a,))

    result = PublicationBoundExperienceRebuilder().rebuild(
        manifest=manifest,
        markdown_body=markdown_body,
        plan=_plan("0.2"),
        publication_record=replace(record, outcome="compensated_failure"),
        store=store,
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "successful_publication_record_required"
    assert result.projection is None
    assert store.status(projection_a.experience_projection_ref) == "current"


def test_rebuild_rejects_record_for_different_published_unit() -> None:
    manifest, markdown_body, record = _published_context()
    store = ExperienceProjectionStore()

    result = PublicationBoundExperienceRebuilder().rebuild(
        manifest=manifest,
        markdown_body=markdown_body,
        plan=_plan("0.2"),
        publication_record=replace(record, published_unit_refs=("KO-OTHER@0.2",)),
        store=store,
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "publication_record_unit_binding_mismatch"
    assert store.projections() == ()


def test_rebuild_recomputes_and_rejects_tampered_knowledge_content() -> None:
    manifest, markdown_body, record = _published_context()
    tampered = deepcopy(manifest)
    tampered["claims"].append({"claim_ref": {"stable_id": "CLM-TAMPERED"}})
    store = ExperienceProjectionStore()

    result = PublicationBoundExperienceRebuilder().rebuild(
        manifest=tampered,
        markdown_body=markdown_body,
        plan=_plan("0.2"),
        publication_record=record,
        store=store,
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "publication_record_knowledge_hash_mismatch"
    assert store.projections() == ()
