"""Source-neutral semantic reference processing."""

from .candidates import (
    KnownGap,
    SemanticCandidatePayload,
    SemanticInterpretationResult,
)
from .change_candidates import (
    ChangeCandidateEvaluation,
    ChangeCandidatePipeline,
    ChangeCandidateRequest,
    ChangeCandidateRevision,
    PriorKnowledgeState,
    SemanticChangeOperationPolicy,
    SemanticChangeProposal,
    SemanticTarget,
)
from .extraction import DeterministicEvidenceExtractor
from .findings import (
    FindingEvaluation,
    FindingInput,
    KnowledgeFinding,
    MaterialDeltaFindingEvaluator,
    SemanticState,
)
from .hardening import (
    AtomicClaimLink,
    CompatibilityChecks,
    ConflictCompatibilityAssessment,
    EvidenceAssessment,
    EvidenceDimensions,
    ProgramOccurrenceRelationship,
    RationaleRelationship,
    TemporalConstraint,
    integrate_cumulative_knowledge_state,
)
from .materializer import SemanticStateMaterializer
from .rule_interpreter import RuleBasedSemanticInterpreter
from .source_backed import SourceBackedSemanticInterpreter, source_accounting

__all__ = [
    "AtomicClaimLink",
    "CompatibilityChecks",
    "ConflictCompatibilityAssessment",
    "DeterministicEvidenceExtractor",
    "ChangeCandidateEvaluation",
    "ChangeCandidatePipeline",
    "ChangeCandidateRequest",
    "ChangeCandidateRevision",
    "FindingEvaluation",
    "FindingInput",
    "EvidenceAssessment",
    "EvidenceDimensions",
    "KnowledgeFinding",
    "KnownGap",
    "MaterialDeltaFindingEvaluator",
    "PriorKnowledgeState",
    "ProgramOccurrenceRelationship",
    "RationaleRelationship",
    "RuleBasedSemanticInterpreter",
    "SemanticCandidatePayload",
    "SemanticChangeOperationPolicy",
    "SemanticChangeProposal",
    "SemanticInterpretationResult",
    "SemanticState",
    "SemanticStateMaterializer",
    "SemanticTarget",
    "SourceBackedSemanticInterpreter",
    "TemporalConstraint",
    "integrate_cumulative_knowledge_state",
    "source_accounting",
]
