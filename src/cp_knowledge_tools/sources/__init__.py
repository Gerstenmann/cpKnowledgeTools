"""Source and Evidence technical materialization."""

from .human_interaction import (
    HumanInteractionSourceRecord,
    HumanSourceContext,
    capture_human_interaction_source,
)
from .models import (
    CapturedSource,
    Coverage,
    Diagnostic,
    EvidenceAddress,
    Fingerprint,
    NormalizedRecord,
    NormalizedSourceRepresentation,
    RawContentReference,
    Selector,
    SourceMapping,
    SourceRecord,
    SourceSnapshot,
    StructuredSegment,
    TransformationRun,
)

__all__ = [
    "CapturedSource",
    "Coverage",
    "Diagnostic",
    "EvidenceAddress",
    "Fingerprint",
    "HumanInteractionSourceRecord",
    "HumanSourceContext",
    "NormalizedRecord",
    "NormalizedSourceRepresentation",
    "RawContentReference",
    "Selector",
    "SourceMapping",
    "SourceRecord",
    "SourceSnapshot",
    "StructuredSegment",
    "TransformationRun",
    "capture_human_interaction_source",
]
