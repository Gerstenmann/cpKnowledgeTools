"""Structural and identity validation for DSM documents."""

from __future__ import annotations

import re
from pathlib import Path

from cp_knowledge_tools.taxonomy.models import (
    MachineBlock,
    ParsedDocument,
    ValidationIssue,
)
from cp_knowledge_tools.taxonomy.parser import DSMParser
from cp_knowledge_tools.taxonomy.schema import (
    DOMAIN_ALLOWED_FIELDS,
    DOMAIN_REQUIRED_FIELDS,
    DSM_REQUIRED_BLOCKS,
    TAXONOMY_STATUS_VALUES,
)

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$"
)


class DSMValidator:
    """Validate one Domain Specific Markup document."""

    def __init__(
        self,
        parser: DSMParser | None = None,
    ) -> None:
        self.parser = parser or DSMParser()

    def validate_file(
        self,
        path: Path | str,
    ) -> ParsedDocument:
        document = self.parser.parse_file(path)
        self.validate_document(document)

        return document

    def validate_document(
        self,
        document: ParsedDocument,
    ) -> None:
        for block_name in sorted(DSM_REQUIRED_BLOCKS):
            if not document.blocks.get(block_name):
                self._add_issue(
                    document=document,
                    code="DSM100",
                    message=(
                        f"Required block "
                        f"@{block_name} is missing."
                    ),
                    line=1,
                    block=block_name,
                )

        domain_block = document.first_block("domain")

        if domain_block is not None:
            self._validate_domain_block(
                document,
                domain_block,
            )

    def _validate_domain_block(
        self,
        document: ParsedDocument,
        block: MachineBlock,
    ) -> None:
        data = block.data

        if not isinstance(data, dict):
            return

        for field_name in sorted(DOMAIN_REQUIRED_FIELDS):
            value = data.get(field_name)

            if value is None or value == "":
                self._add_issue(
                    document=document,
                    code="DSM101",
                    message=(
                        f"Required field "
                        f"{field_name!r} is missing "
                        "or empty."
                    ),
                    line=block.line_for_key(field_name),
                    block="domain",
                )

        for field_name in data:
            if field_name not in DOMAIN_ALLOWED_FIELDS:
                self._add_issue(
                    document=document,
                    code="DSM102",
                    message=(
                        f"Unsupported field "
                        f"{field_name!r} in @domain."
                    ),
                    line=block.line_for_key(field_name),
                    block="domain",
                )

        domain_id = data.get("id")

        if (
            domain_id is not None
            and not IDENTIFIER_PATTERN.fullmatch(
                str(domain_id)
            )
        ):
            self._add_issue(
                document=document,
                code="DSM103",
                message=(
                    "Domain ID must contain only "
                    "lowercase letters, digits and "
                    "underscores, and must start "
                    "with a letter."
                ),
                line=block.line_for_key("id"),
                block="domain",
            )

        if data.get("layer") not in {None, "domain"}:
            self._add_issue(
                document=document,
                code="DSM104",
                message="Field 'layer' must be 'domain'.",
                line=block.line_for_key("layer"),
                block="domain",
            )

        status = data.get("status")

        if (
            status is not None
            and status not in TAXONOMY_STATUS_VALUES
        ):
            allowed = ", ".join(
                sorted(TAXONOMY_STATUS_VALUES)
            )

            self._add_issue(
                document=document,
                code="DSM105",
                message=(
                    f"Invalid status {status!r}. "
                    f"Allowed values: {allowed}."
                ),
                line=block.line_for_key("status"),
                block="domain",
            )

        version = data.get("version")

        if (
            version is not None
            and not VERSION_PATTERN.fullmatch(
                str(version)
            )
        ):
            self._add_issue(
                document=document,
                code="DSM106",
                message=(
                    "Version must use semantic version "
                    "syntax such as 1.0 or 1.0.1."
                ),
                line=block.line_for_key("version"),
                block="domain",
            )

    @staticmethod
    def _add_issue(
        document: ParsedDocument,
        code: str,
        message: str,
        line: int,
        block: str | None = None,
    ) -> None:
        document.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                path=document.path,
                line=line,
                block=block,
            )
        )