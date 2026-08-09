from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cp_knowledge_tools.sources.models import EvidenceAddress

from .candidates import ExtractionProvenance, SemanticValue


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    value: SemanticValue
    provenance: ExtractionProvenance


class DeterministicEvidenceExtractor:
    """Source-neutral extraction over the text carried by Evidence Address."""

    def extract(
        self,
        address: EvidenceAddress,
        specification: dict[str, Any],
    ) -> ExtractionResult | None:
        pattern = specification["pattern"]
        flags = re.IGNORECASE if specification.get("ignore_case", False) else 0
        match = re.search(pattern, address.text, flags=flags)
        if match is None:
            return None

        capture_group = specification.get("capture_group", "value")
        extracted_text = match.group(capture_group).strip()
        parser = specification.get("parser", "text")
        parameters = specification.get("parser_parameters", {})
        value = self._parse(extracted_text, parser, parameters)
        return ExtractionResult(
            value=value,
            provenance=ExtractionProvenance(
                evidence_address_ref=address.evidence_address_ref,
                extractor_kind="regex",
                pattern=pattern,
                capture_group=capture_group,
                parser=parser,
                parser_parameters=tuple(
                    sorted((str(key), str(value)) for key, value in parameters.items())
                ),
                extracted_text=extracted_text,
                extracted_value=value,
            ),
        )

    def _parse(
        self,
        extracted_text: str,
        parser: str,
        parameters: dict[str, Any],
    ) -> SemanticValue:
        if parser in {"text", "entity_mention"}:
            return extracted_text
        if parser == "integer":
            return int(extracted_text.replace(",", "").replace(" ", ""))
        if parser == "date":
            input_format = parameters.get("input_format", "%d %B %Y")
            return datetime.strptime(extracted_text, input_format).date().isoformat()
        if parser == "lower_snake_case":
            return re.sub(r"[^a-z0-9]+", "_", extracted_text.lower()).strip("_")
        raise ValueError(f"Unsupported deterministic parser: {parser}")
