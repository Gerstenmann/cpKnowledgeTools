"""Bounded append-only technical evidence, never a canonical current-state store."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes

from .report import _write_private
from .repository import bounded_path, git

SCHEMA = "cpks.unattended/1"
DIRECTORY = "artifacts/assurance/scheduled"
RUN_ID = re.compile(r"\d{8}T\d{12}Z_[0-9a-f]{32}")
HASH = re.compile(r"[0-9a-f]{64}")
MAX_REPORTS = 512
MAX_REPORT_BYTES = 4_000_000
MAX_CHAIN_BYTES = 256_000_000
DIMENSIONS = {"repository", "governance", "project", "environment", "supply", "hooks"}
REQUIRED_SUCCESS_CHECKS = {
    "previous_evidence",
    "repository_observation",
    "vault_observation",
    "environment_observation",
    "supply_observation",
    "hooks_observation",
    "locked_environment",
    "fast_assurance_lint",
    "fast_environment_contract_tests",
    "protected_inputs_unchanged",
}


def _digest(value: object) -> bool:
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 4096
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _observation(value: dict, successful: bool) -> None:
    if not set(value).issubset(DIMENSIONS) or not all(
        isinstance(v, dict) for v in value.values()
    ):
        raise ValueError("invalid scheduled observation dimensions")
    if successful and set(value) != DIMENSIONS:
        raise ValueError("successful evidence lacks observation dimensions")
    repo = value["repository"]
    if successful or len(repo) > 1:
        if not isinstance(repo.get("branch"), str) or not re.fullmatch(
            r"[0-9a-f]{40,64}", str(repo.get("head"))
        ):
            raise ValueError("invalid repository identity")
        if not isinstance(repo.get("working_tree"), str) or not _digest(
            repo.get("protected_content_sha256")
        ):
            raise ValueError("invalid repository fingerprint")
        if repo.get("index_sha256") != "absent" and not _digest(
            repo.get("index_sha256")
        ):
            raise ValueError("invalid index fingerprint")
        if not _digest(repo.get("staged_entries_sha256")) or not isinstance(
            repo.get("files"), dict
        ):
            raise ValueError("invalid repository file inventory")
        if not isinstance(repo.get("untracked_paths"), list) or not all(
            _relative(p) for p in repo["untracked_paths"]
        ):
            raise ValueError("invalid untracked inventory")
        for name, item in repo["files"].items():
            if not _relative(name) or not isinstance(item, dict):
                raise ValueError("invalid protected file identity")
            if item == {"state": "absent"}:
                continue
            if (
                set(item) != {"sha256", "mode"}
                or not _digest(item["sha256"])
                or type(item["mode"]) is not int
                or not 0 <= item["mode"] <= 0o7777
            ):
                raise ValueError("invalid protected file fingerprint")
        if canonical_json_hash(repo["files"]) != repo["protected_content_sha256"]:
            raise ValueError("protected file inventory hash mismatch")
    if "governance" in value:
        rules = value["governance"]
        if not rules:
            raise ValueError("empty governance observation")
        for stable_id, rule in rules.items():
            if (
                not isinstance(rule, dict)
                or rule.get("stable_id") != stable_id
                or rule.get("integrity_ok") is not True
                or not isinstance(rule.get("version"), str)
                or not _digest(rule.get("current_state_fingerprint"))
                or not _relative(rule.get("relative_path"))
                or not _relative(rule.get("canonical_path"))
            ):
                raise ValueError("invalid active governance observation")
    if "project" in value:
        project = value["project"]
        if (
            not _relative(project.get("path"))
            or not _digest(project.get("sha256"))
            or not isinstance(project.get("project_key"), str)
            or not isinstance(project.get("version"), str)
            or project.get("execution_eligibility") != "not_evaluated"
        ):
            raise ValueError("invalid project observation")
        queues = project.get("queues")
        if not isinstance(queues, dict) or set(queues) != {"Ready", "Doing"}:
            raise ValueError("invalid project queue observation")
        for items in queues.values():
            if not isinstance(items, list) or not all(
                isinstance(i, dict)
                and set(i) == {"path", "sha256"}
                and _relative(i["path"])
                and _digest(i["sha256"])
                for i in items
            ):
                raise ValueError("invalid observed work item")
    if "environment" in value:
        environment = value["environment"]
        for name in (
            "python_pin_sha256",
            "pyproject_sha256",
            "lock_sha256",
            "uv_sha256",
            "binding_sha256",
        ):
            if not _digest(environment.get(name)):
                raise ValueError("invalid locked environment fingerprint")
        if not all(
            isinstance(environment.get(k), str)
            for k in ("python_pin", "uv_version", "environment", "interpreter")
        ):
            raise ValueError("invalid locked environment identity")
    if "supply" in value:
        supply = value["supply"]
        if (
            not isinstance(supply.get("inventory"), dict)
            or not isinstance(supply.get("scanner_bindings"), dict)
            or not supply["scanner_bindings"]
        ):
            raise ValueError("invalid supply observation")
        for tool in supply["scanner_bindings"].values():
            if (
                not isinstance(tool, dict)
                or not _digest(tool.get("executable_hash"))
                or not _digest(tool.get("admission_hash"))
                or not isinstance(tool.get("version"), str)
            ):
                raise ValueError("invalid scanner identity")
    if "hooks" in value:
        hooks = value["hooks"]
        if (
            not isinstance(hooks.get("fingerprints"), dict)
            or not hooks["fingerprints"]
            or not all(
                _relative(p) and _digest(d) for p, d in hooks["fingerprints"].items()
            )
            or hooks.get("trust_enablement") != "unknown"
        ):
            raise ValueError("invalid hook observation")


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("evidence timestamp must be a string")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("evidence timestamp requires timezone")
    return result


def validate(payload: dict, root: Path, name: str) -> None:
    """Validate the entire comparison envelope before any temporal inference."""
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA:
        raise ValueError("unsupported scheduled evidence schema")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid scheduled run ID")
    if name != f"{run_id}.json":
        raise ValueError("scheduled evidence filename/identity mismatch")
    started, completed = (
        _time(payload.get("started_at")),
        _time(payload.get("completed_at")),
    )
    if (
        completed < started
        or started.strftime("%Y%m%dT%H%M%S%fZ") != run_id.split("_")[0]
    ):
        raise ValueError("scheduled evidence chronology mismatch")
    if completed > datetime.now(UTC):
        raise ValueError("scheduled evidence completion is in the future")
    status = payload.get("status")
    if status not in {"passed", "changed", "incomplete", "failed"}:
        raise ValueError("invalid scheduled evidence status")
    expected = {
        "passed": "no_material_change",
        "changed": "material_change",
        "incomplete": "action_required",
        "failed": "action_required",
    }[status]
    if payload.get("materiality") != expected:
        raise ValueError("scheduled evidence materiality/status mismatch")
    observation = payload.get("observation")
    if not isinstance(observation, dict) or not isinstance(
        observation.get("repository"), dict
    ):
        raise ValueError("missing scheduled repository observation")
    if observation["repository"].get("root") != str(root):
        raise ValueError("scheduled evidence belongs to another repository")
    _observation(observation, status in {"passed", "changed"})
    for field in ("checks", "material_delta", "findings"):
        if not isinstance(payload.get(field), list):
            raise ValueError("invalid scheduled evidence collection")
    checks = payload["checks"]
    if not all(
        isinstance(c, dict)
        and isinstance(c.get("name"), str)
        and c.get("status") in {"passed", "failed", "incomplete", "not_applicable"}
        and type(c.get("required")) is bool
        for c in checks
    ):
        raise ValueError("invalid scheduled evidence checks")
    if len({c["name"] for c in checks}) != len(checks):
        raise ValueError("duplicate scheduled evidence check")
    if status in {"passed", "changed"}:
        passed = {
            c["name"] for c in checks if c["status"] == "passed" and c["required"]
        }
        if not REQUIRED_SUCCESS_CHECKS.issubset(passed):
            raise ValueError("successful evidence lacks mandatory routine checks")
        if any(
            c["required"] and c["status"] in {"failed", "incomplete"} for c in checks
        ):
            raise ValueError("successful evidence contains required failures")
        if payload.get("input_stability") != "stable":
            raise ValueError("successful evidence lacks final stability proof")
        if not all(
            isinstance(observation.get(k), dict)
            for k in ("governance", "project", "environment", "supply", "hooks")
        ):
            raise ValueError("successful evidence lacks complete observation")
    for field in ("previous", "comparison_baseline"):
        reference = payload.get(field)
        if reference is None:
            continue
        if not isinstance(reference, dict) or set(reference) != {"run_id", "sha256"}:
            raise ValueError("invalid scheduled evidence link")
        if not RUN_ID.fullmatch(str(reference["run_id"])) or not HASH.fullmatch(
            str(reference["sha256"])
        ):
            raise ValueError("invalid scheduled evidence link identity")
        if reference["run_id"] >= run_id:
            raise ValueError("scheduled evidence link is not earlier")
    digest = payload.get("report_hash")
    if not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise ValueError("missing scheduled evidence content hash")
    unsigned = {key: value for key, value in payload.items() if key != "report_hash"}
    if canonical_json_hash(unsigned) != digest:
        raise ValueError("scheduled evidence content hash mismatch")


def _directory(root: Path, *, create: bool = False):
    """Descriptor boundary rejects symlinks, including ancestor replacement."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root, flags)
    try:
        for part in DIRECTORY.split("/"):
            if create:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(part, mode=0o700, dir_fd=fd)
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def discover(root: Path, budget) -> dict:
    """Resolve prior reports by validated chronology and hash links, never mtime."""
    target = bounded_path(root, DIRECTORY)
    if not target.exists():
        return {"latest": None, "successful": None, "files": {}}
    fd = _directory(root)
    try:
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                budget.check()
                names.append(entry.name)
                if len(names) > MAX_REPORTS:
                    raise ValueError(
                        "scheduled evidence discovery exceeds report budget"
                    )
        reports, hashes, total = {}, {}, 0
        for name in sorted(names):
            budget.check()
            if not name.endswith(".json") or not RUN_ID.fullmatch(name[:-5]):
                raise ValueError("unexpected file in scheduled evidence directory")
            file_fd = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
            )
            with os.fdopen(file_fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                total += info.st_size
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_size > MAX_REPORT_BYTES
                    or total > MAX_CHAIN_BYTES
                ):
                    raise ValueError("scheduled evidence exceeds byte budget")
                content = stream.read(MAX_REPORT_BYTES + 1)
            if len(content) > MAX_REPORT_BYTES:
                raise ValueError("scheduled evidence exceeds byte budget")
            payload = json.loads(content)
            validate(payload, root, name)
            reports[payload["run_id"]] = payload
            hashes[payload["run_id"]] = sha256_bytes(content)
        previous = None
        for run_id, payload in sorted(reports.items()):
            link = payload["previous"]
            if previous is None:
                if link is not None:
                    raise ValueError("scheduled evidence predecessor is missing")
            elif link != {"run_id": previous, "sha256": hashes[previous]}:
                raise ValueError("scheduled evidence chain is broken or forked")
            baseline = payload["comparison_baseline"]
            if baseline is not None and (
                baseline["run_id"] not in reports
                or hashes[baseline["run_id"]] != baseline["sha256"]
                or reports[baseline["run_id"]]["status"] not in {"passed", "changed"}
            ):
                raise ValueError("scheduled evidence baseline link is invalid")
            previous = run_id
        latest = reports[previous] if previous else None
        successful = next(
            (
                p
                for _, p in reversed(sorted(reports.items()))
                if p["status"] in {"passed", "changed"}
            ),
            None,
        )
        return {"latest": latest, "successful": successful, "files": hashes}
    finally:
        os.close(fd)


def reference(payload: dict | None, chain: dict) -> dict | None:
    if payload is None:
        return None
    return {"run_id": payload["run_id"], "sha256": chain["files"][payload["run_id"]]}


def persist(payload: dict, root: Path) -> Path:
    """Persist only a new ignored, untracked fixed-path evidence file."""
    name = f"{payload['run_id']}.json"
    validate(payload, root, name)
    relative = f"{DIRECTORY}/{name}"
    bounded_path(root, relative)
    if git(root, "-c", "core.fsmonitor=false", "ls-files", "--", DIRECTORY).strip():
        raise ValueError("scheduled evidence boundary contains tracked files")
    if (
        git(root, "-c", "core.fsmonitor=false", "check-ignore", "--", relative).strip()
        != relative
    ):
        raise ValueError("scheduled evidence output must be ignored")
    content = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    if len(content) > MAX_REPORT_BYTES:
        raise ValueError("scheduled evidence exceeds report byte budget")
    fd = _directory(root, create=True)
    try:
        # Lock the directory itself: no mutable pointer or lock-file evidence.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            from .unattended import Budget

            current = discover(root, Budget(20))
        except ValueError, OSError, TypeError, KeyError, RecursionError:
            if (
                payload["status"] not in {"incomplete", "failed"}
                or payload["previous"] is not None
            ):
                raise ValueError(
                    "prior evidence changed or became unreadable before append"
                ) from None
            # Preserve the failed discovery as evidence without inventing a link.
            if not any(
                c["name"] == "previous_evidence" and c["status"] == "incomplete"
                for c in payload["checks"]
            ):
                raise ValueError(
                    "unreadable history requires explicit incomplete observation"
                ) from None
        else:
            if reference(current["latest"], current) != payload["previous"]:
                raise ValueError(
                    "concurrent evidence append changed the predecessor; "
                    "rerun observation"
                )
        _write_private(fd, name, content)
    finally:
        os.close(fd)
    return root / relative
