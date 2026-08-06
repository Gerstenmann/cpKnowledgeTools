"""Controlled DSM schema constants."""

DSM_REQUIRED_BLOCKS = frozenset(
    {
        "domain",
        "scope",
        "vocabulary",
        "subjects",
        "signals",
        "relations",
        "runtime",
    }
)

DSM_OPTIONAL_BLOCKS = frozenset(
    {
        "examples",
        "provenance",
    }
)

DSM_ALLOWED_BLOCKS = DSM_REQUIRED_BLOCKS | DSM_OPTIONAL_BLOCKS

DOMAIN_REQUIRED_FIELDS = frozenset(
    {
        "id",
        "label",
        "layer",
        "status",
        "version",
        "owner",
        "language",
    }
)

DOMAIN_OPTIONAL_FIELDS = frozenset(
    {
        "created",
        "updated",
        "replaces",
    }
)

DOMAIN_ALLOWED_FIELDS = DOMAIN_REQUIRED_FIELDS | DOMAIN_OPTIONAL_FIELDS

TAXONOMY_STATUS_VALUES = frozenset(
    {
        "draft",
        "review",
        "approved",
        "deprecated",
        "archived",
    }
)
