from types import MappingProxyType
from typing import Final

PUBLICATION_UNIT_TEMPLATE_BY_SCHEMA: Final = MappingProxyType(
    {
        "CPKS-SPEC-KM-PU@0.1": "CPKS-TPL-KM-PU@0.1",
        "CPKS-SPEC-KM-PU@0.2": "CPKS-TPL-KM-PU@0.2",
    }
)


def publication_unit_template_is_compatible(
    schema_ref: str,
    template_ref: str,
) -> bool:
    return PUBLICATION_UNIT_TEMPLATE_BY_SCHEMA.get(schema_ref) == template_ref
