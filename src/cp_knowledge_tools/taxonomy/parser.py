"""Parser for DSM machine blocks embedded in Markdown."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.resolver import BaseResolver

from cp_knowledge_tools.taxonomy.models import (
    MachineBlock,
    ParsedDocument,
    ValidationIssue,
)
from cp_knowledge_tools.taxonomy.schema import DSM_ALLOWED_BLOCKS

BLOCK_START_PATTERN = re.compile(r"^@([a-z][a-z0-9_]*)$")
KEY_PATTERN = re.compile(r"^\s*(?:-\s+)?([a-z][a-z0-9_]*):")


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    if not isinstance(node, MappingNode):
        raise ConstructorError(
            None,
            None,
            "Expected a mapping.",
            node.start_mark,
        )

    mapping: dict[Any, Any] = {}

    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)

        if key in mapping:
            raise ConstructorError(
                "While constructing a mapping",
                node.start_mark,
                f"Duplicate key: {key!r}",
                key_node.start_mark,
            )

        mapping[key] = loader.construct_object(
            value_node,
            deep=deep,
        )

    return mapping


UniqueKeyLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class DSMParser:
    """Extract and parse DSM blocks from Markdown documents."""

    def parse_file(self, path: Path | str) -> ParsedDocument:
        source_path = Path(path)
        text = source_path.read_text(encoding="utf-8")

        return self.parse_text(source_path, text)

    def parse_text(
        self,
        path: Path,
        text: str,
    ) -> ParsedDocument:
        document = ParsedDocument(path=path)

        current_name: str | None = None
        current_start = 0
        current_lines: list[str] = []

        def add_issue(
            code: str,
            message: str,
            line: int,
            block: str | None = None,
        ) -> None:
            document.issues.append(
                ValidationIssue(
                    code=code,
                    message=message,
                    path=path,
                    line=line,
                    block=block,
                )
            )

        def finish_block(end_line: int) -> None:
            nonlocal current_name
            nonlocal current_start
            nonlocal current_lines

            if current_name is None:
                return

            raw_content = "\n".join(current_lines)

            key_lines: dict[str, list[int]] = {}

            for offset, source_line in enumerate(
                current_lines,
                start=current_start + 1,
            ):
                match = KEY_PATTERN.match(source_line)

                if match:
                    key_lines.setdefault(
                        match.group(1),
                        [],
                    ).append(offset)

            block = MachineBlock(
                name=current_name,
                start_line=current_start,
                end_line=end_line,
                raw_content=raw_content,
                key_lines=key_lines,
            )

            existing = document.blocks.setdefault(
                current_name,
                [],
            )

            if existing:
                add_issue(
                    code="DSM002",
                    message=(f"Block @{current_name} occurs more than once."),
                    line=current_start,
                    block=current_name,
                )

            if not raw_content.strip():
                add_issue(
                    code="DSM006",
                    message="Machine block is empty.",
                    line=current_start,
                    block=current_name,
                )
            else:
                try:
                    block.data = yaml.load(
                        raw_content,
                        Loader=UniqueKeyLoader,
                    )
                except yaml.YAMLError as exc:
                    mark = getattr(exc, "problem_mark", None)

                    source_line = current_start

                    if mark is not None:
                        source_line = current_start + mark.line + 1

                    add_issue(
                        code="DSM007",
                        message=f"Invalid block syntax: {exc}",
                        line=source_line,
                        block=current_name,
                    )
                else:
                    if not isinstance(block.data, dict):
                        add_issue(
                            code="DSM008",
                            message=("Block content must be a top-level mapping."),
                            line=current_start + 1,
                            block=current_name,
                        )

            existing.append(block)

            current_name = None
            current_start = 0
            current_lines = []

        lines = text.splitlines()

        for line_number, source_line in enumerate(
            lines,
            start=1,
        ):
            stripped = source_line.strip()

            if current_name is None:
                if stripped == "@end":
                    add_issue(
                        code="DSM003",
                        message="@end without an open block.",
                        line=line_number,
                    )
                    continue

                start_match = BLOCK_START_PATTERN.fullmatch(stripped)

                if start_match:
                    current_name = start_match.group(1)
                    current_start = line_number
                    current_lines = []

                    if current_name not in DSM_ALLOWED_BLOCKS:
                        add_issue(
                            code="DSM004",
                            message=(f"Unsupported block @{current_name}."),
                            line=line_number,
                            block=current_name,
                        )

                continue

            if stripped == "@end":
                finish_block(line_number)
                continue

            nested_match = BLOCK_START_PATTERN.fullmatch(stripped)

            if nested_match:
                add_issue(
                    code="DSM005",
                    message=(
                        f"Block @{current_name} was not "
                        f"closed before "
                        f"@{nested_match.group(1)}."
                    ),
                    line=line_number,
                    block=current_name,
                )

                finish_block(line_number - 1)

                current_name = nested_match.group(1)
                current_start = line_number
                current_lines = []

                if current_name not in DSM_ALLOWED_BLOCKS:
                    add_issue(
                        code="DSM004",
                        message=(f"Unsupported block @{current_name}."),
                        line=line_number,
                        block=current_name,
                    )

                continue

            if "\t" in source_line:
                add_issue(
                    code="DSM009",
                    message=("Tab characters are not allowed inside machine blocks."),
                    line=line_number,
                    block=current_name,
                )

            if source_line.lstrip().startswith("#"):
                add_issue(
                    code="DSM010",
                    message=("Comments are not allowed inside machine blocks."),
                    line=line_number,
                    block=current_name,
                )

            current_lines.append(source_line)

        if current_name is not None:
            add_issue(
                code="DSM001",
                message=(f"Block @{current_name} is not closed with @end."),
                line=current_start,
                block=current_name,
            )

            finish_block(len(lines))

        return document
