from pathlib import Path

import pytest

from cp_knowledge_tools.template_generator.context_loader import available_contexts, load_context


@pytest.mark.parametrize("context_id", ["organizations", "products"])
def test_builtin_context_is_valid(context_id: str) -> None:
    context = load_context(context_id)
    assert context.context_id == context_id
    assert context.output_root.parts[0] == "Templates"
    assert context.documents
    assert all(document.path.suffix == ".md" for document in context.documents)


def test_builtin_contexts_are_discoverable() -> None:
    assert {"organizations", "products"}.issubset(set(available_contexts()))
