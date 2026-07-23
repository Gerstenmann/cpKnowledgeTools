"""YAML loading and deterministic frontmatter serialization."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import yaml

from .errors import ContextValidationError, OutputValidationError


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


class IndentedSafeDumper(yaml.SafeDumper):
    """Dumper that indents sequence items beneath their mapping key."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow=flow, indentless=False)


def _construct_unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            mark = key_node.start_mark
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r} at line {mark.line + 1}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.load(raw, Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContextValidationError(f"Kontextdatei kann nicht gelesen werden: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContextValidationError(f"Kontextdatei muss ein YAML-Mapping enthalten: {path}")
    return data


def dump_frontmatter(data: dict[str, Any]) -> str:
    stream = StringIO()
    yaml.dump(
        data,
        stream,
        Dumper=IndentedSafeDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
        indent=2,
    )
    body = stream.getvalue().rstrip("\n")
    return f"---\n{body}\n---\n"


def parse_frontmatter(text: str, source: Path) -> tuple[dict[str, Any], str]:
    if text.startswith("\ufeff"):
        raise OutputValidationError(f"{source}: UTF-8 BOM vor dem YAML-Frontmatter ist nicht zulässig.")
    if not text.startswith("---\n"):
        raise OutputValidationError(f"{source}: Datei muss unmittelbar mit '---' beginnen.")

    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise OutputValidationError(f"{source}: Abschließender YAML-Delimiter fehlt.")

    yaml_text = text[4:closing]
    markdown = text[closing + 5 :]
    try:
        data = yaml.load(yaml_text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise OutputValidationError(f"{source}: Ungültiges YAML-Frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise OutputValidationError(f"{source}: YAML-Frontmatter muss ein Mapping sein.")
    return data, markdown
