"""Selective preview/apply with externally resolved acceptance and authority.

POSIX descriptor-relative access avoids symlink traversal. Cooperating writers
lock the repository directory. Host isolation is still required against a
hostile concurrent process moving directories or modifying open files.
"""

from __future__ import annotations

import base64
import datetime as dt
import difflib
import fcntl
import os
import stat
import uuid
from dataclasses import replace
from pathlib import Path

from cp_knowledge_tools.operations.contracts import EnvironmentKind, TargetKind
from cp_knowledge_tools.operations.governance.authority import (
    AuthorityRequirement,
    RuntimeAuthorityResolver,
)
from cp_knowledge_tools.operations.results import to_primitive
from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes

from .acquisition import repository_commit
from .assessment import DecisionSource, accepted_decision, decision_fingerprint
from .inspection import inspect_candidate
from .models import (
    AdoptionPlan,
    ApplyResult,
    CandidateFacts,
    CopiedCodeProvenance,
    Phase,
    ReuseDisposition,
    ReuseError,
    to_json,
)
from .paths import RootHandle, collect_files, relative_parts, verified_root


def _plan_hash(plan: AdoptionPlan) -> str:
    return canonical_json_hash(to_primitive(replace(plan, plan_fingerprint="")))


def _hash(data: bytes | None) -> str | None:
    return sha256_bytes(data) if data is not None else None


def preview_adoption(
    facts: CandidateFacts,
    decisions: DecisionSource,
    *,
    assessment_id: str,
    source_file: str,
    target_repository: Path,
    target_repository_id: str,
    target_path: str,
    provenance_output: str,
    planned_modification: str,
    expected_target_fingerprint: str | None = None,
    replacement_text: str | None = None,
) -> AdoptionPlan:
    facts = inspect_candidate(facts.snapshot)
    decision = accepted_decision(facts, decisions, assessment_id)
    if decision.disposition is not ReuseDisposition.ADAPT:
        raise ReuseError("only ADAPT permits selected code copying")
    for path in (source_file, target_path, provenance_output):
        relative_parts(path)
    if target_path.casefold() == provenance_output.casefold():
        raise ReuseError("target and provenance must be distinct")
    if source_file not in dict(facts.snapshot.file_fingerprints):
        raise ReuseError("source unit not in inspected snapshot")
    if not planned_modification.strip():
        raise ReuseError("modification summary required")
    root = verified_root(target_repository)
    repository_commit(root)
    if (
        root.is_relative_to(facts.snapshot.root)
        or facts.snapshot.root.is_relative_to(root)
        or (
            facts.snapshot.source.kind == "local"
            and (
                root.is_relative_to(Path(facts.snapshot.source.location))
                or Path(facts.snapshot.source.location).is_relative_to(root)
            )
        )
    ):
        raise ReuseError("target and candidate scopes overlap")
    with RootHandle(facts.snapshot.root) as source:
        original = source.read(source_file, facts.snapshot.limits.max_file_bytes)
        original_text = original.decode("utf-8")
        content = original if replacement_text is None else replacement_text.encode()
        retained = tuple(
            (p, source.read(p).decode("utf-8"))
            for p in sorted(set(facts.license_files + facts.notice_files))
        )
        copyrights = tuple(
            line
            for line in original_text.splitlines()
            if "copyright" in line.lower()
            or "SPDX-License-Identifier:" in line
            or "author" in line.lower()
            and line.lstrip().startswith("#")
        )
        if replacement_text is not None and any(
            line not in replacement_text for line in copyrights
        ):
            raise ReuseError("adaptation must retain copyright and SPDX notices")
        retained += tuple((source_file, line) for line in copyrights)
    with RootHandle(root) as target:
        before = target.optional_read(target_path)
        if _hash(before) != expected_target_fingerprint:
            raise ReuseError("target conflict: expected starting fingerprint required")
        if target.optional_read(provenance_output) is not None:
            raise ReuseError("provenance target conflict")
        target_identity = target.identity
    diff = "".join(
        difflib.unified_diff(
            (before or b"").decode("utf-8").splitlines(keepends=True),
            content.decode("utf-8").splitlines(keepends=True),
            fromfile=f"before/{target_path}",
            tofile=f"after/{target_path}",
        )
    )
    plan = AdoptionPlan(
        assessment_id,
        facts.snapshot.candidate_id,
        Path(facts.snapshot.source.location).name,
        facts.snapshot.source.location,
        facts.snapshot.commit,
        source_file,
        sha256_bytes(original),
        decision.license_expression,
        retained,
        str(root),
        target_repository_id,
        target_path,
        decision.disposition,
        planned_modification,
        provenance_output,
        facts.snapshot,
        decision_fingerprint(decision),
        base64.b64encode(content).decode("ascii"),
        expected_target_fingerprint,
        target_identity,
        diff,
    )
    return replace(plan, plan_fingerprint=_plan_hash(plan))


def authority_requirement(plan: AdoptionPlan) -> AuthorityRequirement:
    """Use the existing authority contract; paths narrow the mutation scope."""
    return AuthorityRequirement(
        operation_id="reuse.adapt",
        target_stable_id=plan.target_repository_id,
        target_version=None,
        artifact_class="repository_artifact",
        target_kind=TargetKind.REPOSITORY,
        document_type="repository_artifact",
        mutation_scope=tuple(sorted((plan.target_path, plan.provenance_output))),
        environment_kind=EnvironmentKind.LOCAL_REPOSITORY,
        environment_identity=plan.target_repository,
        activate=False,
    )


def _put(target: RootHandle, path: str, data: bytes, expected: bytes | None) -> None:
    """Stage bytes then publish. Creation never replaces an existing entry."""
    with target.parent(path) as (fd, name):
        temporary = f".reuse-{uuid.uuid4().hex}"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        try:
            if expected is not None:
                mode = os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
                os.fchmod(descriptor, stat.S_IMODE(mode) & 0o777)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            target.check_identity()
            if target.optional_read(path) != expected:
                raise ReuseError("target conflict immediately before write")
            if expected is None:
                os.link(
                    temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False
                )
            else:
                os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError:
                pass


def apply_adoption(
    plan: AdoptionPlan,
    *,
    decisions: DecisionSource,
    authority: RuntimeAuthorityResolver | None,
    authority_ref: str,
    phase: Phase,
) -> ApplyResult:
    if phase is not Phase.IMPLEMENT:
        raise ReuseError("adoption apply requires DEV-P05 / IMPLEMENT")
    if _plan_hash(plan) != plan.plan_fingerprint:
        raise ReuseError("plan fingerprint drift")
    if plan.reuse_disposition is not ReuseDisposition.ADAPT:
        raise ReuseError("only ADAPT can apply")
    if authority is None:
        raise ReuseError("independently resolved authority is required")
    facts = inspect_candidate(plan.snapshot)
    decision = accepted_decision(facts, decisions, plan.assessment_id)
    if decision_fingerprint(decision) != plan.decision_fingerprint:
        raise ReuseError("decision drift; create a new reviewed preview")
    root = verified_root(Path(plan.target_repository))
    repository_commit(root)
    content = base64.b64decode(plan.content_base64, validate=True)
    # Hashes detect drift; they are not signatures. Rebuild every derived field
    # from live evidence so an edited plan cannot erase attribution/provenance.
    rebuilt = preview_adoption(
        facts,
        decisions,
        assessment_id=plan.assessment_id,
        source_file=plan.source_file_or_unit,
        target_repository=root,
        target_repository_id=plan.target_repository_id,
        target_path=plan.target_path,
        provenance_output=plan.provenance_output,
        planned_modification=plan.planned_modification,
        expected_target_fingerprint=plan.expected_target_fingerprint,
        replacement_text=content.decode("utf-8"),
    )
    if rebuilt != plan:
        raise ReuseError("plan no longer matches source, decision or target")
    with RootHandle(plan.snapshot.root) as source:
        snapshot_original = source.read(
            plan.source_file_or_unit, plan.snapshot.limits.max_file_bytes
        )
    if sha256_bytes(snapshot_original) != plan.source_fingerprint:
        raise ReuseError("source fingerprint drift")
    if plan.snapshot.source.kind == "local":
        original_root = Path(plan.snapshot.source.location)
        if repository_commit(original_root) != plan.snapshot.commit:
            raise ReuseError("source commit drift")
        files, _ = collect_files(original_root, plan.snapshot.limits)
        if tuple((p, sha256_bytes(data)) for p, data in files.items()) != (
            plan.snapshot.file_fingerprints
        ):
            raise ReuseError("source fingerprint drift")
    with RootHandle(root) as target:
        fcntl.flock(target.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if target.identity != plan.target_identity:
            raise ReuseError("target root identity drift")
        grant = authority.resolve(
            authority_ref=authority_ref,
            contract_value=None,
            requirement=authority_requirement(plan),
        )
        if not grant.authorized:
            raise ReuseError("authority resolution blocked adoption")
        original = target.optional_read(plan.target_path)
        if _hash(original) != plan.expected_target_fingerprint:
            raise ReuseError("target conflict")
        if target.optional_read(plan.provenance_output) is not None:
            raise ReuseError("provenance target conflict")
        if len(content) > plan.snapshot.limits.max_file_bytes:
            raise ReuseError("adopted content exceeds byte limit")
        provenance = CopiedCodeProvenance(
            plan.assessment_id,
            plan.candidate_id,
            plan.upstream_project,
            plan.upstream_repository,
            plan.upstream_commit_or_snapshot,
            plan.snapshot.fingerprint,
            plan.source_file_or_unit,
            plan.source_fingerprint,
            base64.b64encode(snapshot_original).decode("ascii"),
            plan.license_expression_or_license_state,
            tuple(
                e
                for e in facts.evidence
                if e.kind
                in {"declared_license", "license_file", "license_metadata", "copyright"}
            ),
            plan.notice_or_attribution_requirements,
            plan.target_repository,
            plan.target_path,
            sha256_bytes(content),
            plan.reuse_disposition,
            plan.planned_modification,
            decision.decision_ref,
            authority_ref,
            grant.source_fingerprint or "",
            dt.datetime.now(dt.UTC).isoformat(),
        )
        outputs = {
            plan.provenance_output: (None, to_json(provenance).encode()),
            plan.target_path: (original, content),
        }
        changed = []
        try:
            for path, (before, after) in outputs.items():
                changed.append(path)
                _put(target, path, after, before)
            for path, (_, after) in outputs.items():
                if target.read(path, max(len(after), 1)) != after:
                    raise ReuseError("postcondition reread mismatch")
        except OSError, ReuseError:
            remaining = []
            for path in reversed(changed):
                before, after = outputs[path]
                try:
                    actual = target.optional_read(
                        path, max(len(after), len(before or b""), 1)
                    )
                    if actual == before:
                        continue
                    if actual != after:
                        raise ReuseError("concurrent change prevents safe compensation")
                    if before is None:
                        with target.parent(path) as (fd, name):
                            os.unlink(name, dir_fd=fd)
                    else:
                        _put(target, path, before, after)
                except OSError, ReuseError:
                    remaining.append(path)
            return ApplyResult(
                "recovery_required" if remaining else "compensated_failure",
                tuple(remaining),
                provenance,
                "Apply failed; review remaining paths before retrying."
                if remaining
                else "Apply failed; original target bytes restored.",
            )
        return ApplyResult(
            "succeeded",
            tuple(changed),
            provenance,
            "Selected code and provenance written and reread.",
        )
