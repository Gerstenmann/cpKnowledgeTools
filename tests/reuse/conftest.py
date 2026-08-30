from __future__ import annotations

import datetime as dt
import subprocess

import pytest

from cp_knowledge_tools.operations.contracts import RuntimeAuthorityContract
from cp_knowledge_tools.operations.governance.authority import (
    AuthoritySourceRecord,
    RuntimeAuthorityResolver,
)
from cp_knowledge_tools.reuse.models import (
    CandidateAssessment,
    DependencyAcceptanceState,
    ReuseDisposition,
)
from cp_knowledge_tools.validation.temporal import parse_lifecycle_temporal


@pytest.fixture
def git_repo(tmp_path):
    def create(name, files):
        root = tmp_path / name
        root.mkdir()
        for path, content in files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        for args in (
            ["init", "-q"],
            ["add", "."],
            [
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-qm",
                "fixture",
            ],
        ):
            subprocess.run(
                ["git", "-C", str(root), *args], check=True, capture_output=True
            )
        return root.resolve()

    return create


@pytest.fixture
def candidate(git_repo):
    return git_repo(
        "candidate",
        {
            "src/helper.py": "# Copyright 2026 Fixture authors\n"
            "def normalize(value):\n    return value.strip()\n",
            "tests/test_helper.py": "raise RuntimeError('must not execute')\n",
            "LICENSE": "SPDX-License-Identifier: MIT\nSynthetic license evidence\n",
            "NOTICE": "Fixture authors must be attributed.\n",
            "pyproject.toml": '[project]\nname="fixture"\nversion="1.0"\n'
            'license="MIT"\ndependencies=["example>=1"]\n'
            '[build-system]\nrequires=["setuptools"]\n'
            'build-backend="setuptools.build_meta"\n',
            "README.md": "Synthetic package, not third-party code.\n",
            "setup.py": "raise RuntimeError('must not execute setup')\n",
        },
    )


@pytest.fixture
def target(git_repo):
    return git_repo("target", {"README.md": "Target\n"})


class DecisionStore:
    """Synthetic trusted decision adapter; never a production approval source."""

    def __init__(self, snapshot):
        self.decision = CandidateAssessment(
            assessment_id="assessment-test",
            candidate_id=snapshot.candidate_id,
            snapshot_fingerprint=snapshot.fingerprint,
            disposition=ReuseDisposition.ADAPT,
            acceptance=DependencyAcceptanceState.ACCEPTED,
            rationale="Select one fixture function.",
            license_expression="MIT",
            license_resolved=True,
            license_finding="Fixture reviewed.",
            license_evidence_paths=("LICENSE", "pyproject.toml"),
            security_finding="Static fixture reviewed; no runtime clearance.",
            policy_refs=("CPKS-POL-SW-SUPPLY@0.2",),
            decision_ref="fixture-decision@1",
            conditions=(),
        )

    def resolve(self, assessment_id, candidate_id):
        assert (assessment_id, candidate_id) == (
            self.decision.assessment_id,
            self.decision.candidate_id,
        )
        return self.decision


@pytest.fixture
def decisions():
    return DecisionStore


@pytest.fixture
def authority():
    def create(plan, **changes):
        mapping = {
            "contract": "cpks.runtime_authority",
            "contract_version": "0.1",
            "authority": {
                "ref": "fixture-owner",
                "version": "1",
                "class": "owner_approval",
                "issuer": "Fixture Owner",
            },
            "operations": ["reuse.adapt"],
            "targets": [
                {
                    "stable_id": plan.target_repository_id,
                    "version": None,
                    "artifact_class": "repository_artifact",
                    "target_kind": "repository",
                }
            ],
            "scope": {
                "document_types": ["repository_artifact"],
                "mutation_scope": sorted((plan.target_path, plan.provenance_output)),
            },
            "environment": {
                "kind": "local_repository",
                "identity": plan.target_repository,
            },
            "effects": {"mutate": True, "activate": False, "remote_effects": False},
            "validity": {
                "effective_from": "2026-01-01T00:00:00+00:00",
                "expires_at": "2027-01-01T00:00:00+00:00",
            },
            "approval": {
                "required": True,
                "approved_by": "Fixture Owner",
                "approved_at": "2026-01-01T00:00:00+00:00",
                "evidence_ref": "synthetic-test-only",
            },
        }
        mapping.update(changes)
        grant = RuntimeAuthorityContract.from_mapping(mapping)
        record = AuthoritySourceRecord(
            authority_ref="fixture-owner",
            version="1",
            authority_class=grant.authority.authority_class,
            issuer="Fixture Owner",
            source_path="synthetic-test-only",
            source_fingerprint="fixture",
            effective_from=parse_lifecycle_temporal("2026-01-01"),
            grants=(grant,),
            approval_verified=True,
        )

        class Source:
            def resolve(self, ref):
                assert ref == "fixture-owner"
                return record

        return RuntimeAuthorityResolver(
            Source(),
            owner_approval_source=Source(),
            known_operations=("reuse.adapt",),
            clock=lambda: dt.datetime(2026, 8, 30, tzinfo=dt.UTC),
        )

    return create
