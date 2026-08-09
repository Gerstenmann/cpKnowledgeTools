"""Source-neutral semantic reference processing."""

from .candidates import (
    KnownGap,
    SemanticCandidatePayload,
    SemanticInterpretationResult,
)
from .extraction import DeterministicEvidenceExtractor
from .materializer import SemanticStateMaterializer
from .rule_interpreter import RuleBasedSemanticInterpreter

__all__ = [
    "DeterministicEvidenceExtractor",
    "KnownGap",
    "RuleBasedSemanticInterpreter",
    "SemanticCandidatePayload",
    "SemanticInterpretationResult",
    "SemanticStateMaterializer",
]
