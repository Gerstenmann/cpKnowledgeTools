"""Software reuse assessment core. Agent/runtime adapters provide live judgments."""

from .acquisition import ResearchWorkspace
from .adoption import apply_adoption, authority_requirement, preview_adoption
from .assessment import (
    DecisionSource,
    integration_handover,
    research_gate,
    validate_assessment,
)
from .inspection import inspect_candidate, inspect_internal
from .models import CandidateSource, CapabilityNeed, to_json

__all__ = [
    "CandidateSource",
    "CapabilityNeed",
    "DecisionSource",
    "ResearchWorkspace",
    "apply_adoption",
    "authority_requirement",
    "inspect_candidate",
    "inspect_internal",
    "integration_handover",
    "preview_adoption",
    "research_gate",
    "to_json",
    "validate_assessment",
]
