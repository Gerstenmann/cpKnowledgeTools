from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class PublicationUnitCodecError(ValueError):
    """Raised when a Publication Unit cannot be parsed without ambiguity."""


class _PublicationUnitLoader(yaml.SafeLoader):
    pass


_PublicationUnitLoader.yaml_implicit_resolvers = {
    key: [
        (tag, pattern)
        for tag, pattern in resolvers
        if tag != "tag:yaml.org,2002:timestamp"
    ]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _construct_unique_mapping(
    loader: _PublicationUnitLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    pairs = loader.construct_pairs(node, deep=deep)
    result: dict[Any, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicationUnitCodecError(f"duplicate YAML key: {key!r}")
        result[key] = value
    return result


_PublicationUnitLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class PublicationUnitDocument:
    """Logical Publication Unit: structured manifest plus exact Markdown body."""

    manifest: dict[str, Any]
    markdown_body: str

    def clone(self) -> PublicationUnitDocument:
        return PublicationUnitDocument(deepcopy(self.manifest), self.markdown_body)


def parse_yaml_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and preserve the body after one separator newline."""
    if not text.startswith("---\n"):
        raise PublicationUnitCodecError("document must start with YAML frontmatter")

    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise PublicationUnitCodecError("document has no closing frontmatter delimiter")

    yaml_text = text[4:closing]
    body = text[closing + len("\n---\n") :]
    if body.startswith("\n"):
        body = body[1:]

    try:
        manifest = yaml.load(yaml_text, Loader=_PublicationUnitLoader)
    except (yaml.YAMLError, PublicationUnitCodecError) as exc:
        raise PublicationUnitCodecError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PublicationUnitCodecError("frontmatter must be a mapping")
    if not all(isinstance(key, str) for key in manifest):
        raise PublicationUnitCodecError("frontmatter keys must be strings")
    return manifest, body


def parse_publication_unit(text: str) -> PublicationUnitDocument:
    manifest, body = parse_yaml_frontmatter(text)
    return PublicationUnitDocument(manifest=manifest, markdown_body=body)


def load_publication_unit(path: Path) -> PublicationUnitDocument:
    return parse_publication_unit(path.read_text(encoding="utf-8"))


def render_publication_unit(document: PublicationUnitDocument) -> str:
    manifest_text = yaml.safe_dump(
        document.manifest,
        allow_unicode=True,
        sort_keys=False,
    )
    return f"---\n{manifest_text}---\n\n{document.markdown_body}"
