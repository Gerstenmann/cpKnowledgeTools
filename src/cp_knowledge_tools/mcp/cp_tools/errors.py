"""Errors raised by the read-only cpKnowledgeTools MCP server."""


class RepositoryError(Exception):
    """Base exception for repository access errors."""


class RepositoryConfigurationError(RepositoryError):
    """Raised when the configured repository root is invalid."""


class RepositoryPathError(RepositoryError):
    """Raised when a path is invalid or escapes the repository."""


class RepositoryFileNotFoundError(RepositoryError):
    """Raised when a requested repository file does not exist."""


class RepositoryAccessDeniedError(RepositoryError):
    """Raised when access to a path is intentionally blocked."""


class RepositoryFileTooLargeError(RepositoryError):
    """Raised when a requested file exceeds the configured size limit."""


class UnsupportedFileTypeError(RepositoryError):
    """Raised when a requested file is not readable UTF-8 text."""


class GitRepositoryError(RepositoryError):
    """Raised when the configured directory is not the Git root."""


class GitCommandError(RepositoryError):
    """Raised when a permitted read-only Git command fails."""
