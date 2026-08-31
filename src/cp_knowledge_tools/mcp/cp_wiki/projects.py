"""Resolve Project Homes as read-only authority *sources*, never runtime grants.

Project identity/control rules come from CPKS-SPEC-PRJ; authority-reference
semantics from CPKS-SPEC-PWI. Prose scope, tolerances and gates remain evidence
for the responsible evaluator. A successful read is not execution eligibility.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cp_knowledge_tools.operations.results import to_primitive
from cp_knowledge_tools.platform.hashing import sha256_bytes
from cp_knowledge_tools.reuse.models import ReuseError
from cp_knowledge_tools.reuse.paths import RootHandle
from cp_knowledge_tools.template_generator.errors import OutputValidationError
from cp_knowledge_tools.template_generator.yaml_io import parse_frontmatter

from .errors import VaultError
from .vault import Vault

SUPPORTED_AUTHORITY_KINDS = ("project_home", "project")
_PROJECT_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SNAKE_CASE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
_VERSION = re.compile(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?")
_MAX_SOURCE_BYTES = 2_000_000
_MAX_FILES = 10_000


class ProjectAuthorityError(VaultError):
    """A failed source resolution, with a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ProjectAuthorityResolution:
    kind: str
    reference: str
    source_path: str
    source_fingerprint: str
    source_version: str
    project_root: str
    owner: str
    project_status: str
    ai_autonomy_level: str | None
    tolerances: dict[str, Any]
    human_gate_required_for: tuple[str, ...]
    frontmatter: dict[str, Any]
    body: str
    checked_on: str
    checks: tuple[str, ...]
    schema: str = "cpkt.project_authority_source"
    schema_version: str = "0.1"
    fingerprint_algorithm: str = "sha256"
    source_status: str = "resolved"
    read_only: bool = True
    execution_authorized: bool = False
    execution_eligibility: str = "not_evaluated"
    pending_checks: tuple[str, ...] = (
        "authority_scope_for_action",
        "work_item_scope_and_dependencies",
        "ai_authority_for_action",
        "human_gates_and_hard_constraints",
        "control_conditions",
        "tool_and_data_permissions",
    )


def _error(code: str, message: str) -> ProjectAuthorityError:
    return ProjectAuthorityError(f"project_authority_{code}", message)


def _project_paths(vault: Vault):
    """Enumerate lexical paths; do not lose symlink identities via resolve()."""
    projects = vault.root / "Projects"
    if projects.is_symlink():
        raise _error("unsafe_path", "Projects must not be a symlink")
    if not projects.exists():
        return

    def fail_walk(error: OSError) -> None:
        raise _error("index_unreadable", "Cannot enumerate current Projects") from error

    count = 0
    for directory, dirs, files in os.walk(
        projects, onerror=fail_walk, followlinks=False
    ):
        # Archived material never competes with current identity, even if its
        # historical frontmatter still says active or has a larger version.
        dirs[:] = sorted(d for d in dirs if d.casefold() != "archive")
        if any((Path(directory) / d).is_symlink() for d in dirs):
            raise _error(
                "unsafe_path", "Current Project directories must not be symlinks"
            )
        for name in sorted(files):
            if Path(name).suffix.lower() not in {".md", ".markdown"}:
                continue
            count += 1
            if count > _MAX_FILES:
                raise _error(
                    "index_limit", "Current Project scan exceeds its file limit"
                )
            path = Path(directory) / name
            if path.is_symlink():
                raise _error(
                    "unsafe_path", "Current Project files must not be symlinks"
                )
            yield path.relative_to(vault.root).as_posix()


def _validate_plain_value(
    value: Any,
    ancestors: frozenset[int] = frozenset(),
    depth: int = 0,
    budget: list[int] | None = None,
) -> None:
    """Bound YAML structures and reject recursive aliases/non-JSON controls."""
    if budget is None:
        budget = [_MAX_SOURCE_BYTES]
    budget[0] -= 16 + (len(value.encode("utf-8")) if isinstance(value, str) else 0)
    if budget[0] < 0:
        raise _error("source_limit", "Expanded Project metadata exceeds its limit")
    if depth > 40:
        raise _error("invalid_metadata", "Project metadata nesting exceeds its limit")
    if isinstance(value, (dict, list)):
        if id(value) in ancestors:
            raise _error(
                "invalid_metadata", "Recursive Project metadata is not supported"
            )
        ancestors = ancestors | {id(value)}
        children: Iterable[Any]
        if isinstance(value, dict):
            if not all(isinstance(k, str) for k in value):
                raise _error(
                    "invalid_metadata", "Project metadata keys must be strings"
                )
            children = (child for pair in value.items() for child in pair)
        else:
            children = value
        for child in children:
            _validate_plain_value(child, ancestors, depth + 1, budget)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise _error(
                "invalid_metadata", "Non-finite Project metadata is not supported"
            )
    elif value is not None and not isinstance(value, (str, bool, int, dt.date)):
        raise _error("invalid_metadata", "Unsupported Project metadata value")


def _read_candidate(vault: Vault, relative_path: str):
    try:
        path = vault.resolve_path(relative_path)
        # Read and hash the same bytes; never fingerprint a second version of
        # a source after parsing an earlier one. This is not an OS sandbox.
        with RootHandle(vault.root) as source_root:
            raw = source_root.read(relative_path, _MAX_SOURCE_BYTES)
        text = raw.decode("utf-8")
        if not text.startswith(("---", "\ufeff")):
            return None
        text = text.replace("\r\n", "\n")
        # Inspect YAML nodes before construction. A duplicate field in a known
        # non-Project record must not invalidate an unrelated Project Home.
        # Unlike safe_load, this retains every occurrence of the type key.
        closing = text.find("\n---\n", 4)
        if not text.startswith("---\n") or closing < 0:
            raise _error("index_unreadable", "Malformed Project frontmatter boundary")
        node = yaml.compose(text[4:closing], Loader=yaml.SafeLoader)
        if not isinstance(node, yaml.MappingNode):
            raise _error("index_unreadable", "Project frontmatter must be a mapping")
        if any(
            not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str"
            for key, _ in node.value
        ):
            raise _error("index_unreadable", "Cannot classify Project metadata keys")
        types = [value for key, value in node.value if key.value == "type"]
        if any(
            not isinstance(value, yaml.ScalarNode)
            or value.tag != "tag:yaml.org,2002:str"
            for value in types
        ):
            raise _error("index_unreadable", "Cannot classify Project metadata type")
        if not any(value.value == "project" for value in types):
            return None
        # Existing strict loader rejects duplicate keys at every nesting level
        # of an actual authority candidate, including conflicting type keys.
        frontmatter, body = parse_frontmatter(text, path)
        _validate_plain_value(frontmatter)
        return frontmatter, body, sha256_bytes(raw)
    except (
        OSError,
        UnicodeError,
        OutputValidationError,
        TypeError,
        ValueError,
        RecursionError,
        yaml.YAMLError,
        ReuseError,
    ):
        # Do not include YAML source excerpts (or arbitrary field contents) in
        # a diagnostic. An unreadable candidate cannot silently disappear.
        raise _error(
            "index_unreadable", f"Cannot inspect Project metadata: {relative_path}"
        ) from None


def _date(value: Any, field: str) -> dt.date:
    if type(value) is dt.date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            pass
    raise _error("invalid_metadata", f"{field} must be an ISO calendar date")


def _validate_home(fm: dict[str, Any], relative: str, today: dt.date) -> None:
    for field in ("title", "owner", "project_type", "canonical_path"):
        if not isinstance(fm.get(field), str) or not fm[field].strip():
            raise _error(
                "invalid_metadata", f"Project {field} must be a nonempty string"
            )
    version = fm.get("version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise _error(
            "invalid_metadata",
            "Project version must have two or three numeric segments",
        )
    for field in ("project_type", "delivery_profile"):
        if field in fm and (
            not isinstance(fm[field], str) or not _SNAKE_CASE.fullmatch(fm[field])
        ):
            raise _error(
                "invalid_metadata", f"Project {field} must be lower_snake_case"
            )
    if fm.get("project_status") != "active":
        raise _error("not_active", "Project Home is not active for execution authority")
    if not isinstance(fm.get("governance_profile"), str) or fm[
        "governance_profile"
    ] not in {"micro", "lean", "standard", "controlled"}:
        raise _error("invalid_metadata", "Unknown Project governance profile")
    if not isinstance(fm.get("risk_level"), str) or fm["risk_level"] not in {
        "low",
        "medium",
        "high",
        "critical",
    }:
        raise _error("invalid_metadata", "Unknown Project risk level")
    created, revised = (_date(fm.get(field), field) for field in ("created", "revised"))
    if created > revised or revised > today:
        raise _error(
            "invalid_metadata", "Project dates are inconsistent or in the future"
        )
    if unicodedata.normalize("NFC", fm["canonical_path"]) != unicodedata.normalize(
        "NFC", relative
    ):
        raise _error(
            "path_mismatch", "Project canonical_path differs from its actual path"
        )
    title = unicodedata.normalize("NFC", fm["title"].strip())
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " - ", title)
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"(?:\s*-\s*){2,}", " - ", title).rstrip(". ")
    if unicodedata.normalize("NFC", Path(relative).name) != title + ".md":
        raise _error(
            "path_mismatch", "Project Home filename differs from its normalized title"
        )
    if len(Path(relative).parts) < 3:
        raise _error("path_mismatch", "Project Home must be inside a Project root")

    autonomy = fm.get("ai_autonomy_level")
    if "ai_autonomy_level" in fm and (
        not isinstance(autonomy, str)
        or autonomy not in {"observe", "recommend", "coordinate", "bounded_execute"}
    ):
        raise _error("invalid_metadata", "Unknown Project AI autonomy level")
    tolerances = fm.get("tolerances", {})
    if not isinstance(tolerances, dict):
        raise _error("invalid_metadata", "Project tolerances must be a mapping")
    if not tolerances and (
        autonomy in {"coordinate", "bounded_execute"}
        or fm["governance_profile"] in {"standard", "controlled"}
    ):
        raise _error("invalid_metadata", "Project controls require nonempty tolerances")
    for dimension, field in (
        ("scope", "expansion_allowed"),
        ("authority", "self_extension_allowed"),
        ("quality", "acceptance_criteria_may_be_weakened"),
    ):
        value = tolerances.get(dimension)
        if isinstance(value, dict) and field in value and value[field] is not False:
            raise _error(
                "invalid_metadata", "Project tolerances cannot relax a hard constraint"
            )
    risk = tolerances.get("risk")
    if (
        isinstance(risk, dict)
        and "escalate_at" in risk
        and (
            not isinstance(risk["escalate_at"], str)
            or risk["escalate_at"] not in {"low", "medium", "high", "critical"}
        )
    ):
        raise _error("invalid_metadata", "Unknown Project risk escalation level")
    gates = fm.get("human_gate_required_for", [])
    if not isinstance(gates, list) or any(
        not isinstance(gate, str) or not _SNAKE_CASE.fullmatch(gate) for gate in gates
    ):
        raise _error(
            "invalid_metadata", "Project human gates must be lower_snake_case strings"
        )


def resolve_project_authority(
    vault: Vault,
    reference: str,
    *,
    kind: str = "project_home",
    today: dt.date | None = None,
) -> ProjectAuthorityResolution:
    """Resolve a PWI kind/reference to one current active Project Home.

    Both ``project_home`` and ``project`` name the same source kind. References
    are exact unversioned project keys. No caller scope, permit flag, cached
    decision or Work Item is accepted as an authority source. The returned
    controls still require action-specific interpretation under live rules.
    """
    if kind not in SUPPORTED_AUTHORITY_KINDS:
        raise _error("kind_unsupported", "Unsupported Project authority source kind")
    if not isinstance(reference, str) or not _PROJECT_KEY.fullmatch(reference):
        raise _error("invalid_reference", "Expected an exact unversioned project_key")
    checked_on = today if today is not None else dt.date.today()
    if type(checked_on) is not dt.date:
        raise _error("invalid_date", "Resolution date must be a calendar date")
    candidates: list[tuple[str, dict[str, Any], str, str]] = []
    for relative in _project_paths(vault):
        candidate = _read_candidate(vault, relative)
        if candidate is None:
            continue
        fm, body, fingerprint = candidate
        if fm.get("type") == "project" and fm.get("project_key") == reference:
            if candidates:
                raise _error(
                    "ambiguous", "Multiple current Project Homes share the project_key"
                )
            candidates.append((relative, fm, body, fingerprint))
    if not candidates:
        raise _error("not_found", "No current Project Home matches the project_key")
    relative, fm, body, fingerprint = candidates[0]
    _validate_home(fm, relative, checked_on)
    return ProjectAuthorityResolution(
        kind="project_home",
        reference=reference,
        source_path=relative,
        source_fingerprint=fingerprint,
        source_version=fm["version"],
        project_root=Path(relative).parent.as_posix(),
        owner=fm["owner"],
        project_status=fm["project_status"],
        ai_autonomy_level=fm.get("ai_autonomy_level"),
        tolerances=to_primitive(fm.get("tolerances", {})),
        human_gate_required_for=tuple(fm.get("human_gate_required_for", [])),
        frontmatter=to_primitive(fm),
        body=body,
        checked_on=checked_on.isoformat(),
        checks=(
            "supported_authority_kind",
            "exact_project_key",
            "unique_current_home",
            "active_project",
            "project_metadata",
            "canonical_path",
            "source_fingerprint",
        ),
    )
