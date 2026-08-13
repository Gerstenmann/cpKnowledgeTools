from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import PreparedCoreInputs

CORE_RULE_SOURCES = {
    "CPKS-SPEC-KM@0.20": "exact",
    "CPKS-SPEC-KM-PU@0.1": "exact",
    "CPKS-SPEC-KM-VOC@0.1": "exact",
}

CORE_VOCABULARIES: dict[str, dict[str, Any]] = {
    "event_participation_role": {
        "vocabulary_ref": "cpks.vocab.core.event_participation_role@0.1",
        "namespace": "cpks.vocab.core.event_participation_role",
        "extension_policy": "profile_extension_allowed",
        "terms": (
            "actor",
            "affected_party",
            "beneficiary",
            "initiator",
            "instrument",
            "location",
            "observer",
            "organizer",
            "participant",
            "recipient",
            "subject",
        ),
    },
    "relationship_predicate": {
        "vocabulary_ref": "cpks.vocab.core.relationship_predicate@0.1",
        "namespace": "cpks.vocab.core.relationship_predicate",
        "extension_policy": "profile_extension_allowed",
        "terms": (
            "causes",
            "contains",
            "contradicts",
            "depends_on",
            "derived_from",
            "enables",
            "equivalent_to",
            "follows",
            "has_evidence",
            "invalidates",
            "is_a",
            "is_alternative_to",
            "part_of",
            "precedes",
            "previous_version",
            "qualifies",
            "references",
            "supersedes",
        ),
    },
}


@dataclass(frozen=True)
class CompositionIssue:
    code: str
    path: str
    message: str
    severity: str = "fatal"


@dataclass(frozen=True)
class ProfileComposition:
    resolution: dict[str, Any]
    applicable_profiles: tuple[dict[str, Any], ...]
    effective_vocabularies: dict[str, Any]
    issues: tuple[CompositionIssue, ...]
    profile_role_terms: dict[str, dict[str, Any]]
    profile_event_type_terms: dict[str, dict[str, Any]]
    profile_event_type_namespaces: tuple[str, ...]


def _identity_text(manifest: dict[str, Any]) -> str:
    return f"{manifest['profile_ref']}@{manifest['profile_version']}"


def _parse_profile_ref(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    profile_ref, separator, version = value.rpartition("@")
    if not separator or not profile_ref or not version:
        return None
    return profile_ref, version


def _core_effective_vocabularies() -> dict[str, Any]:
    return {
        name: {
            "core_vocabulary_ref": definition["vocabulary_ref"],
            "extension_policy": definition["extension_policy"],
            "namespaces": [definition["namespace"]],
            "accepted_values": list(definition["terms"]),
            "terms": [
                {
                    "code": term,
                    "term_ref": term,
                    "source_ref": definition["vocabulary_ref"],
                }
                for term in definition["terms"]
            ],
        }
        for name, definition in sorted(CORE_VOCABULARIES.items())
    }


def _issue(
    issues: list[CompositionIssue],
    message: str,
    path: str,
    *,
    code: str = "core_knowledge_profile_resolution_failed",
) -> None:
    issues.append(CompositionIssue(code=code, path=path, message=message))


def _profile_rule(
    payload: dict[str, Any], target: str
) -> dict[str, Any] | None:
    matches = [
        rule
        for rule in payload.get("validator_rules", [])
        if isinstance(rule, dict) and rule.get("target") == target
    ]
    if len(matches) != 1:
        return None
    rule = matches[0]
    required = ("validator_rule_ref", "severity", "diagnostic_code", "rule_source")
    if not all(isinstance(rule.get(name), str) and rule[name] for name in required):
        return None
    return {
        "validator_rule_ref": rule["validator_rule_ref"],
        "severity": rule["severity"],
        "diagnostic_code": rule["diagnostic_code"],
        "rule_sources": [rule["rule_source"]],
    }


def _validate_compatibility(
    payload: dict[str, Any],
    profile_ref: str,
    issues: list[CompositionIssue],
) -> None:
    compatibility: dict[str, str] = {}
    values = payload.get("compatible_core_versions")
    if not isinstance(values, list):
        _issue(
            issues,
            f"applicable Profile {profile_ref} has no Core compatibility set",
            f"/applicable_profiles/{profile_ref}/compatible_core_versions",
        )
        return
    for item in values:
        if not isinstance(item, dict):
            continue
        source = item.get("rule_source")
        mode = item.get("compatibility_mode")
        if isinstance(source, str) and isinstance(mode, str):
            if source in compatibility:
                _issue(
                    issues,
                    f"applicable Profile {profile_ref} repeats {source}",
                    f"/applicable_profiles/{profile_ref}/compatible_core_versions",
                )
            compatibility[source] = mode
    for source, required_mode in CORE_RULE_SOURCES.items():
        if compatibility.get(source) != required_mode:
            _issue(
                issues,
                (
                    f"applicable Profile {profile_ref} is not {required_mode} "
                    f"compatible with {source}"
                ),
                f"/applicable_profiles/{profile_ref}/compatible_core_versions",
            )


def _extension_points(
    payload: dict[str, Any],
    profile_ref: str,
    issues: list[CompositionIssue],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    values = payload.get("extension_points")
    if not isinstance(values, list):
        _issue(
            issues,
            f"applicable Profile {profile_ref} has no extension-point declarations",
            f"/applicable_profiles/{profile_ref}/extension_points",
        )
        return result
    for item in values:
        if not isinstance(item, dict):
            continue
        namespace = item.get("namespace")
        if not isinstance(namespace, str) or not namespace:
            continue
        if namespace in result:
            _issue(
                issues,
                f"applicable Profile {profile_ref} repeats namespace {namespace}",
                f"/applicable_profiles/{profile_ref}/extension_points",
                code="core_vocabulary_namespace_collision",
            )
        result[namespace] = item
    return result


def _validated_terms(
    *,
    vocabulary: dict[str, Any],
    namespace: str,
    profile_ref: str,
    vocabulary_name: str,
    issues: list[CompositionIssue],
) -> list[dict[str, Any]]:
    values = vocabulary.get("terms")
    if not isinstance(values, list) or not values:
        _issue(
            issues,
            f"normative vocabulary {namespace} has no terms",
            f"/applicable_profiles/{profile_ref}/controlled_vocabularies/{vocabulary_name}",
        )
        return []
    terms: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            _issue(
                issues,
                f"normative vocabulary {namespace} contains a malformed term",
                (
                    f"/applicable_profiles/{profile_ref}/controlled_vocabularies/"
                    f"{vocabulary_name}/terms/{index}"
                ),
            )
            continue
        code = item.get("code")
        term_ref = item.get("term_ref")
        if (
            not isinstance(code, str)
            or not code
            or term_ref != f"{namespace}.{code}"
            or term_ref in seen
        ):
            _issue(
                issues,
                f"normative vocabulary {namespace} contains an invalid term identity",
                (
                    f"/applicable_profiles/{profile_ref}/controlled_vocabularies/"
                    f"{vocabulary_name}/terms/{index}"
                ),
            )
            continue
        allowed_event_types = item.get("allowed_event_types")
        if allowed_event_types is not None and (
            not isinstance(allowed_event_types, list)
            or not allowed_event_types
            or not all(
                isinstance(event_type, str) and event_type
                for event_type in allowed_event_types
            )
        ):
            _issue(
                issues,
                f"normative vocabulary term {term_ref} has invalid constraints",
                (
                    f"/applicable_profiles/{profile_ref}/controlled_vocabularies/"
                    f"{vocabulary_name}/terms/{index}/allowed_event_types"
                ),
            )
            continue
        seen.add(term_ref)
        terms.append(dict(item))
    return terms


def compose_applicable_profiles(
    manifest: dict[str, Any], inputs: PreparedCoreInputs
) -> ProfileComposition:
    """Compose only the concrete active Profiles supplied for this Publication Unit."""
    issues: list[CompositionIssue] = []
    declared_values = manifest.get("profile_refs")
    declared_identities: list[tuple[str, str]] = []
    if not isinstance(declared_values, list):
        _issue(issues, "Publication Unit profile_refs must be a list", "/profile_refs")
        declared_values = []
    for index, value in enumerate(declared_values):
        identity = _parse_profile_ref(value)
        if identity is None:
            _issue(
                issues,
                "Publication Unit contains a non-concrete Profile reference",
                f"/profile_refs/{index}",
            )
        else:
            declared_identities.append(identity)
    if len(set(declared_identities)) != len(declared_identities):
        _issue(issues, "Publication Unit repeats a Profile reference", "/profile_refs")

    supplied = {
        (item["profile_ref"], item["profile_version"]): item
        for item in inputs.applicable_profile_manifests
    }
    declared_set = set(declared_identities)
    supplied_set = set(supplied)
    if declared_set != supplied_set:
        missing = sorted(declared_set - supplied_set)
        injected = sorted(supplied_set - declared_set)
        if missing:
            _issue(
                issues,
                "Publication Unit Profile was not supplied: "
                + ", ".join(f"{ref}@{version}" for ref, version in missing),
                "/profile_refs",
            )
        if injected:
            _issue(
                issues,
                "unreferenced applicable Profile was supplied: "
                + ", ".join(f"{ref}@{version}" for ref, version in injected),
                "/applicable_profiles",
            )

    supplied_refs = sorted(f"{ref}@{version}" for ref, version in supplied_set)
    declared_refs = sorted(f"{ref}@{version}" for ref, version in declared_set)
    profiles_report = tuple(
        {
            "profile_ref": item["profile_ref"],
            "profile_version": item["profile_version"],
            "status": item["status"],
            "manifest_hash": inputs.applicable_profile_hashes[_identity_text(item)],
            "included_in_effective_context": False,
        }
        for item in sorted(
            inputs.applicable_profile_manifests,
            key=lambda value: (value["profile_ref"], value["profile_version"]),
        )
    )
    exact_match = not issues and declared_set == supplied_set
    if not exact_match:
        return ProfileComposition(
            resolution={
                "status": "failed",
                "declared_profile_refs": declared_refs,
                "supplied_profile_refs": supplied_refs,
                "exact_match": False,
            },
            applicable_profiles=profiles_report,
            effective_vocabularies=_core_effective_vocabularies(),
            issues=tuple(issues),
            profile_role_terms={},
            profile_event_type_terms={},
            profile_event_type_namespaces=(),
        )

    vocabularies: list[dict[str, Any]] = []
    namespaces: set[str] = set()
    term_refs: set[str] = set()
    for identity in sorted(supplied_set):
        profile = supplied[identity]
        profile_ref = f"{identity[0]}@{identity[1]}"
        payload = profile["payload"]
        _validate_compatibility(payload, profile_ref, issues)
        declared_extensions = _extension_points(payload, profile_ref, issues)
        used_extensions: set[str] = set()
        controlled = payload.get("controlled_vocabularies")
        if not isinstance(controlled, dict):
            _issue(
                issues,
                f"applicable Profile {profile_ref} has no controlled vocabularies",
                f"/applicable_profiles/{profile_ref}/controlled_vocabularies",
            )
            continue
        for name, vocabulary in sorted(controlled.items()):
            path = f"/applicable_profiles/{profile_ref}/controlled_vocabularies/{name}"
            if not isinstance(name, str) or not isinstance(vocabulary, dict):
                _issue(issues, "normative vocabulary declaration is malformed", path)
                continue
            namespace = vocabulary.get("namespace")
            vocabulary_ref = vocabulary.get("vocabulary_ref")
            version = vocabulary.get("vocabulary_version")
            if (
                not isinstance(namespace, str)
                or not namespace
                or vocabulary_ref != namespace
                or not isinstance(version, str)
                or not version
            ):
                _issue(issues, "normative vocabulary identity is invalid", path)
                continue
            if namespace.startswith("cpks.vocab.core.") or namespace in namespaces:
                _issue(
                    issues,
                    f"Profile vocabulary namespace collides: {namespace}",
                    path,
                    code="core_vocabulary_namespace_collision",
                )
                continue
            extension = declared_extensions.get(namespace)
            if extension is None:
                _issue(
                    issues,
                    f"normative vocabulary {namespace} has no declared extension point",
                    path,
                )
                continue
            field_bindings = vocabulary.get("field_bindings", [])
            target = extension.get("target_path_or_role")
            if target != name and target not in field_bindings:
                _issue(
                    issues,
                    f"extension point does not bind normative vocabulary {namespace}",
                    path,
                )
                continue
            used_extensions.add(namespace)
            extends = vocabulary.get("extends")
            if extends is not None:
                core = CORE_VOCABULARIES.get(name)
                if (
                    core is None
                    or core["vocabulary_ref"] != extends
                    or core["extension_policy"] != "profile_extension_allowed"
                ):
                    _issue(
                        issues,
                        f"normative extension target is unknown or closed: {extends}",
                        path,
                    )
                    continue
            terms = _validated_terms(
                vocabulary=vocabulary,
                namespace=namespace,
                profile_ref=profile_ref,
                vocabulary_name=name,
                issues=issues,
            )
            role_rule = _profile_rule(payload, "event_participation")
            event_type_rule = _profile_rule(payload, "event_state.event_type_ref")
            if name == "event_participation_role" and any(
                "allowed_event_types" in item for item in terms
            ) and role_rule is None:
                _issue(
                    issues,
                    f"Profile role constraints in {namespace} have no validator rule",
                    path,
                )
            if name == "event_type" and event_type_rule is None:
                _issue(
                    issues,
                    f"Profile event types in {namespace} have no validator rule",
                    path,
                )
            duplicate_terms = sorted(
                item["term_ref"] for item in terms if item["term_ref"] in term_refs
            )
            if duplicate_terms:
                _issue(
                    issues,
                    "Profile vocabulary term collision: " + ", ".join(duplicate_terms),
                    path,
                    code="core_vocabulary_namespace_collision",
                )
            namespaces.add(namespace)
            term_refs.update(item["term_ref"] for item in terms)
            vocabularies.append(
                {
                    "name": name,
                    "namespace": namespace,
                    "vocabulary_ref": f"{vocabulary_ref}@{version}",
                    "profile_ref": profile_ref,
                    "terms": terms,
                    "role_rule": role_rule,
                    "event_type_rule": event_type_rule,
                }
            )
        for namespace in sorted(set(declared_extensions) - used_extensions):
            _issue(
                issues,
                f"unknown normative extension point: {namespace}",
                f"/applicable_profiles/{profile_ref}/extension_points",
            )

    if issues:
        return ProfileComposition(
            resolution={
                "status": "failed",
                "declared_profile_refs": declared_refs,
                "supplied_profile_refs": supplied_refs,
                "exact_match": True,
            },
            applicable_profiles=profiles_report,
            effective_vocabularies=_core_effective_vocabularies(),
            issues=tuple(issues),
            profile_role_terms={},
            profile_event_type_terms={},
            profile_event_type_namespaces=(),
        )

    effective = _core_effective_vocabularies()
    role_terms: dict[str, dict[str, Any]] = {}
    event_terms: dict[str, dict[str, Any]] = {}
    event_namespaces: set[str] = set()
    for vocabulary in sorted(
        vocabularies,
        key=lambda item: (item["name"], item["namespace"], item["profile_ref"]),
    ):
        name = vocabulary["name"]
        target = effective.setdefault(
            name,
            {
                "core_vocabulary_ref": None,
                "extension_policy": "profile_defined",
                "namespaces": [],
                "accepted_values": [],
                "terms": [],
            },
        )
        target["namespaces"].append(vocabulary["namespace"])
        for item in sorted(vocabulary["terms"], key=lambda term: term["term_ref"]):
            public_term = {
                "code": item["code"],
                "term_ref": item["term_ref"],
                "source_ref": vocabulary["profile_ref"],
            }
            if "allowed_event_types" in item:
                public_term["allowed_event_types"] = sorted(
                    item["allowed_event_types"]
                )
            target["terms"].append(public_term)
            target["accepted_values"].append(item["term_ref"])
            term_context = {
                **public_term,
                "namespace": vocabulary["namespace"],
            }
            if name == "event_participation_role":
                term_context["validator_rule"] = vocabulary["role_rule"]
                role_terms[item["term_ref"]] = term_context
            elif name == "event_type":
                term_context["validator_rule"] = vocabulary["event_type_rule"]
                event_terms[item["term_ref"]] = term_context
                event_namespaces.add(vocabulary["namespace"])
        target["namespaces"] = sorted(set(target["namespaces"]))
        target["accepted_values"] = sorted(set(target["accepted_values"]))
        target["terms"] = sorted(
            target["terms"], key=lambda item: (item["term_ref"], item["source_ref"])
        )

    included_profiles = tuple(
        {**profile, "included_in_effective_context": True}
        for profile in profiles_report
    )
    return ProfileComposition(
        resolution={
            "status": "resolved",
            "declared_profile_refs": declared_refs,
            "supplied_profile_refs": supplied_refs,
            "exact_match": True,
        },
        applicable_profiles=included_profiles,
        effective_vocabularies=effective,
        issues=(),
        profile_role_terms=role_terms,
        profile_event_type_terms=event_terms,
        profile_event_type_namespaces=tuple(sorted(event_namespaces)),
    )
