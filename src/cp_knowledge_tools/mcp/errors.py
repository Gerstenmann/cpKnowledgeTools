"""Errors raised by the read-only cp-wiki MCP server."""


class VaultError(Exception):
    """Base exception for vault access errors."""


class VaultConfigurationError(VaultError):
    """Raised when the configured vault root is invalid."""


class VaultPathError(VaultError):
    """Raised when a requested path is invalid or escapes the vault."""


class VaultFileNotFoundError(VaultError):
    """Raised when a requested vault file does not exist."""


class UnsupportedFileTypeError(VaultError):
    """Raised when a requested file type is not supported."""