"""Domain-specific exceptions and CLI exit codes."""

from __future__ import annotations


EXIT_OK = 0
EXIT_VALIDATION_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_INTERNAL_ERROR = 3


class TemplateGeneratorError(Exception):
    """Base exception for expected template-generator failures."""


class ContextValidationError(TemplateGeneratorError):
    """Raised when a declarative context is invalid."""


class OutputValidationError(TemplateGeneratorError):
    """Raised when generated output does not satisfy structural rules."""


class UnsafePathError(TemplateGeneratorError):
    """Raised when a path escapes its configured output root."""
