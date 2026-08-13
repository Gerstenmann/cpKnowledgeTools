from __future__ import annotations

import json
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any

from cp_knowledge_tools.platform.hashing import canonical_json_hash
from cp_knowledge_tools.publication.codec import parse_yaml_frontmatter

from .models import CoreValidationInputError, PreparedCoreInputs

CORE_PROFILE = ("cpks.profile.core-knowledge", "1.1")
CORE_CORPUS = ("cpks.corpus.core-knowledge", "1.1")
CONTRACT_PROFILE = ("cpks.profile.contract-conformance", "1.1")
CANONICALIZATION_PROFILE = (
    "cpks.profile.canonicalization.canonical-json-value",
    "1.0",
)


def _raise(code: str, message: str, path: str = "/") -> None:
    raise CoreValidationInputError(code, message, path)


def _strict_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    normalized: set[str] = set()
    for key, value in pairs:
        normalized_key = unicodedata.normalize("NFC", key)
        if key in result or normalized_key in normalized:
            _raise(
                "core_knowledge_golden_corpus_integrity_failed",
                f"duplicate JSON key after NFC normalization: {key!r}",
            )
        result[key] = value
        normalized.add(normalized_key)
    return result


def _strict_json_integer(value: str) -> int:
    if value == "-0":
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            "negative zero is outside the canonical JSON domain",
        )
    return int(value)


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_pairs,
            parse_int=_strict_json_integer,
            parse_float=lambda value: _raise(
                "core_knowledge_golden_corpus_integrity_failed",
                f"floating-point value is outside the canonical JSON domain: {value}",
            ),
            parse_constant=lambda value: _raise(
                "core_knowledge_golden_corpus_integrity_failed",
                f"non-finite value is outside the canonical JSON domain: {value}",
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            f"cannot load JSON input {path}: {exc}",
        )
    if not isinstance(value, dict):
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            "Golden Corpus payload must be a JSON object",
        )
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest, _body = parse_yaml_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        _raise(
            "core_knowledge_profile_integrity_failed",
            f"cannot load manifest {path}: {exc}",
        )
    return manifest


def _assert_canonical_domain(value: Any, path: str = "") -> None:
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        _raise(
            "core_knowledge_input_canonicalization_failed",
            "floating-point values are not supported by this validator slice",
            path or "/",
        )
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            _raise(
                "core_knowledge_input_canonicalization_failed",
                "input string is not NFC-normalized",
                path or "/",
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_canonical_domain(item, f"{path}/{index}")
        return
    if isinstance(value, dict):
        normalized_keys: set[str] = set()
        for key, item in value.items():
            if not isinstance(key, str):
                _raise(
                    "core_knowledge_input_canonicalization_failed",
                    "object key is not a string",
                    path or "/",
                )
            normalized = unicodedata.normalize("NFC", key)
            if normalized != key or normalized in normalized_keys:
                _raise(
                    "core_knowledge_input_canonicalization_failed",
                    "object key is not uniquely NFC-normalized",
                    f"{path}/{key}",
                )
            normalized_keys.add(normalized)
            _assert_canonical_domain(item, f"{path}/{key}")
        return
    _raise(
        "core_knowledge_input_canonicalization_failed",
        f"unsupported canonical JSON value type: {type(value).__name__}",
        path or "/",
    )


def _content_hash(
    manifest: dict[str, Any],
    *,
    field_name: str = "content_hash",
    code: str,
    expected_scope: str,
) -> str:
    content_hash = manifest.get(field_name)
    if not isinstance(content_hash, dict):
        _raise(code, f"manifest {field_name} is missing", f"/{field_name}")
    if content_hash.get("algorithm") != "sha-256":
        _raise(
            code,
            "manifest hash algorithm must be sha-256",
            f"/{field_name}/algorithm",
        )
    if content_hash.get("hash_scope") != expected_scope:
        _raise(
            code,
            f"manifest hash scope must be {expected_scope}",
            f"/{field_name}/hash_scope",
        )
    canonical = content_hash.get("canonicalization_profile")
    if not isinstance(canonical, dict) or (
        canonical.get("profile_ref"), canonical.get("profile_version")
    ) != CANONICALIZATION_PROFILE:
        _raise(
            code,
            "manifest does not use the required canonicalization profile",
            f"/{field_name}/canonicalization_profile",
        )
    expected = content_hash.get("value")
    if not isinstance(expected, str) or len(expected) != 64:
        _raise(code, "manifest content hash is invalid", f"/{field_name}/value")
    return expected


def _validate_profile_manifest(
    manifest: dict[str, Any],
    expected_identity: tuple[str, str] | None = None,
) -> tuple[tuple[str, str], str]:
    identity = (manifest.get("profile_ref"), manifest.get("profile_version"))
    if not all(isinstance(item, str) and item for item in identity):
        _raise(
            "core_knowledge_profile_resolution_failed",
            "active Profile identity is missing or invalid",
        )
    if expected_identity is not None and identity != expected_identity:
        _raise(
            "core_knowledge_profile_resolution_failed",
            (
                "required active profile "
                f"{expected_identity[0]}@{expected_identity[1]} was not supplied"
            ),
        )
    profile_ref, version = identity
    if manifest.get("status") != "active":
        _raise(
            "core_knowledge_profile_resolution_failed",
            f"required active profile {profile_ref}@{version} was not supplied",
        )
    if manifest.get("document_type") != "profile_manifest":
        _raise(
            "core_knowledge_profile_integrity_failed",
            "required Profile input is not a profile_manifest",
            "/document_type",
        )
    payload = manifest.get("payload")
    if not isinstance(payload, dict) or (
        payload.get("profile_ref"), payload.get("profile_version")
    ) != identity:
        _raise(
            "core_knowledge_profile_integrity_failed",
            f"profile payload identity does not match {profile_ref}@{version}",
            "/payload",
        )
    _assert_canonical_domain(payload, "/payload")
    expected_hash = _content_hash(
        manifest,
        code="core_knowledge_profile_integrity_failed",
        expected_scope="profile_manifest_payload",
    )
    expected_manifest_hash = _content_hash(
        manifest,
        field_name="manifest_hash",
        code="core_knowledge_profile_integrity_failed",
        expected_scope="profile_manifest_payload",
    )
    actual_hash = canonical_json_hash(payload)
    if actual_hash != expected_hash or actual_hash != expected_manifest_hash:
        _raise(
            "core_knowledge_profile_integrity_failed",
            f"profile hash mismatch: expected {expected_hash}, got {actual_hash}",
            "/content_hash/value",
        )
    return identity, actual_hash


def prepare_core_inputs(
    *,
    profile_manifest: dict[str, Any],
    corpus_manifest: dict[str, Any],
    corpus_payload: dict[str, Any],
    required_profile_manifests: list[dict[str, Any]],
    applicable_profile_manifests: list[dict[str, Any]] | None = None,
) -> PreparedCoreInputs:
    """Resolve and verify the exact externally supplied active validation set."""
    profile_manifest = deepcopy(profile_manifest)
    corpus_manifest = deepcopy(corpus_manifest)
    corpus_payload = deepcopy(corpus_payload)
    required_profile_manifests = deepcopy(required_profile_manifests)
    applicable_profile_manifests = deepcopy(applicable_profile_manifests or [])

    _core_identity, core_hash = _validate_profile_manifest(
        profile_manifest, CORE_PROFILE
    )
    supplied: dict[tuple[str, str], dict[str, Any]] = {}
    for item in required_profile_manifests:
        identity = (item.get("profile_ref"), item.get("profile_version"))
        if identity in supplied:
            _raise(
                "core_knowledge_profile_resolution_failed",
                f"required Profile {identity[0]}@{identity[1]} was supplied twice",
            )
        supplied[identity] = item
    required_hashes: dict[str, str] = {}
    for identity in (CONTRACT_PROFILE, CANONICALIZATION_PROFILE):
        manifest = supplied.get(identity)
        if manifest is None:
            _raise(
                "core_knowledge_profile_resolution_failed",
                f"required active profile {identity[0]}@{identity[1]} is missing",
            )
        _resolved_identity, digest = _validate_profile_manifest(manifest, identity)
        required_hashes[f"{identity[0]}@{identity[1]}"] = digest

    applicable_hashes: dict[str, str] = {}
    applicable_identities: set[tuple[str, str]] = set()
    infrastructure_profiles = {
        CORE_PROFILE,
        CONTRACT_PROFILE,
        CANONICALIZATION_PROFILE,
    }
    for manifest in applicable_profile_manifests:
        identity, digest = _validate_profile_manifest(manifest)
        if identity in infrastructure_profiles:
            _raise(
                "core_knowledge_profile_resolution_failed",
                (
                    f"Validator infrastructure Profile {identity[0]}@{identity[1]} "
                    "cannot be supplied as an applicable runtime Profile"
                ),
            )
        if identity in applicable_identities:
            _raise(
                "core_knowledge_profile_resolution_failed",
                f"applicable Profile {identity[0]}@{identity[1]} was supplied twice",
            )
        applicable_identities.add(identity)
        applicable_hashes[f"{identity[0]}@{identity[1]}"] = digest

    declared_required = profile_manifest["payload"].get("required_profiles", [])
    declared_identities = {
        (item.get("profile_ref"), version)
        for item in declared_required
        if isinstance(item, dict)
        for version in item.get("compatible_versions", [])
    }
    for identity in (CONTRACT_PROFILE, CANONICALIZATION_PROFILE):
        if identity not in declared_identities:
            _raise(
                "core_knowledge_profile_integrity_failed",
                (
                    "Core Profile does not declare required profile "
                    f"{identity[0]}@{identity[1]}"
                ),
                "/payload/required_profiles",
            )

    corpus_identity = (
        corpus_manifest.get("corpus_ref"),
        corpus_manifest.get("corpus_version"),
    )
    if corpus_identity != CORE_CORPUS or corpus_manifest.get("status") != "active":
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            (
                f"required active corpus {CORE_CORPUS[0]}@{CORE_CORPUS[1]} "
                "was not supplied"
            ),
        )
    if corpus_manifest.get("document_type") != "golden_corpus_manifest":
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            "required Corpus input is not a golden_corpus_manifest",
            "/document_type",
        )
    if (
        corpus_manifest.get("profile_ref"),
        corpus_manifest.get("profile_version"),
    ) != CORE_PROFILE:
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            "corpus is not bound to the active Core Knowledge Profile",
            "/profile_ref",
        )

    _assert_canonical_domain(corpus_payload, "/corpus_payload")
    expected_corpus_hash = _content_hash(
        corpus_manifest,
        code="core_knowledge_golden_corpus_integrity_failed",
        expected_scope="golden_corpus_payload",
    )
    actual_corpus_hash = canonical_json_hash(corpus_payload)
    if actual_corpus_hash != expected_corpus_hash:
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            "Golden Corpus payload hash does not match its active manifest",
            "/content_hash/value",
        )
    if (
        corpus_payload.get("corpus_ref"),
        corpus_payload.get("corpus_version"),
    ) != CORE_CORPUS or (
        corpus_payload.get("profile_ref"),
        corpus_payload.get("profile_version"),
    ) != CORE_PROFILE:
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            "Golden Corpus payload identity or Profile binding is invalid",
        )

    cases = corpus_payload.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != 16
        or corpus_manifest.get("case_count") != 16
        or corpus_payload.get("case_count") != 16
    ):
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            "active Core Golden Corpus must contain exactly 16 cases",
            "/cases",
        )
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases) or len(set(case_ids)) != len(case_ids):
        _raise(
            "core_knowledge_golden_corpus_integrity_failed",
            "Golden Corpus case identities are missing or duplicated",
            "/cases",
        )
    declared_rules = profile_manifest["payload"].get("validator_rules")
    if not isinstance(declared_rules, list):
        _raise(
            "core_knowledge_profile_integrity_failed",
            "Core Profile validator_rules are missing",
            "/payload/validator_rules",
        )
    declared_rule_refs = [
        rule.get("validator_rule_ref")
        for rule in declared_rules
        if isinstance(rule, dict)
    ]
    if len(declared_rule_refs) != len(declared_rules) or len(
        set(declared_rule_refs)
    ) != len(declared_rule_refs):
        _raise(
            "core_knowledge_profile_integrity_failed",
            "Core Profile rule references are missing or duplicated",
            "/payload/validator_rules",
        )
    declared_rule_set = set(declared_rule_refs)
    for index, case in enumerate(cases):
        rule_refs = case.get("rule_refs") if isinstance(case, dict) else None
        if not isinstance(rule_refs, list) or not set(rule_refs) <= declared_rule_set:
            _raise(
                "core_knowledge_golden_corpus_integrity_failed",
                "Golden case refers to a rule outside the active Core Profile",
                f"/cases/{index}/rule_refs",
            )

    fixtures = profile_manifest["payload"].get("fixture_refs", [])
    matching = [
        item
        for item in fixtures
        if isinstance(item, dict)
        and (item.get("corpus_ref"), item.get("corpus_version")) == CORE_CORPUS
    ]
    if len(matching) != 1:
        _raise(
            "core_knowledge_profile_integrity_failed",
            "Core Profile does not uniquely bind the active Core Corpus",
            "/payload/fixture_refs",
        )
    fixture_hash = matching[0].get("content_hash", {}).get("value")
    fixture_content_hash = matching[0].get("content_hash", {})
    if (
        fixture_hash != actual_corpus_hash
        or fixture_content_hash.get("algorithm") != "sha-256"
        or fixture_content_hash.get("hash_scope") != "golden_corpus_payload"
        or fixture_content_hash.get("canonicalization_profile")
        != {
            "profile_ref": CANONICALIZATION_PROFILE[0],
            "profile_version": CANONICALIZATION_PROFILE[1],
        }
    ):
        _raise(
            "core_knowledge_profile_integrity_failed",
            "Core Profile fixture hash does not match the active Core Corpus",
            "/payload/fixture_refs/0/content_hash/value",
        )

    return PreparedCoreInputs(
        profile_manifest=profile_manifest,
        corpus_manifest=corpus_manifest,
        corpus_payload=corpus_payload,
        required_profile_manifests=tuple(required_profile_manifests),
        applicable_profile_manifests=tuple(applicable_profile_manifests),
        profile_hash=core_hash,
        corpus_hash=actual_corpus_hash,
        required_profile_hashes=required_hashes,
        applicable_profile_hashes=applicable_hashes,
    )
