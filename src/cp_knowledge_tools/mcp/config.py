"""Configuration for the local read-only cp-wiki MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import VaultConfigurationError

DEFAULT_VAULT_ROOT = Path("/Users/cp/Documents/cp-wiki")
VAULT_ROOT_ENV = "CP_WIKI_VAULT_ROOT"


@dataclass(frozen=True, slots=True)
class MCPConfig:
    """Immutable MCP server configuration."""

    vault_root: Path

    @classmethod
    def from_environment(cls) -> "MCPConfig":
        """Load configuration from the environment."""

        configured_root = os.environ.get(VAULT_ROOT_ENV)
        vault_root = (
            Path(configured_root).expanduser()
            if configured_root
            else DEFAULT_VAULT_ROOT
        )

        vault_root = vault_root.resolve()

        if not vault_root.exists():
            raise VaultConfigurationError(
                f"Vault root does not exist: {vault_root}"
            )

        if not vault_root.is_dir():
            raise VaultConfigurationError(
                f"Vault root is not a directory: {vault_root}"
            )

        return cls(vault_root=vault_root)