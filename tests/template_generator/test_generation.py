from pathlib import Path

import pytest

from cp_knowledge_tools.template_generator.generator import TemplateGenerator


@pytest.mark.parametrize("context_id", ["organizations", "products"])
def test_generation_and_validation(tmp_path: Path, context_id: str) -> None:
    generator = TemplateGenerator()
    result = generator.generate(context_id, tmp_path)

    assert result.valid
    assert result.written_files
    assert (result.output_root / "Erläuterung.md").is_file()
    assert generator.validate(context_id, tmp_path) == []


def test_generation_is_non_destructive_by_default(tmp_path: Path) -> None:
    generator = TemplateGenerator()
    first = generator.generate("organizations", tmp_path)
    target = first.output_root / "00 Organization Template.md"
    original = target.read_text(encoding="utf-8")
    target.write_text(original + "\nMANUAL CHANGE\n", encoding="utf-8")

    second = generator.generate("organizations", tmp_path, validate=False)

    assert target in second.skipped_files
    assert "MANUAL CHANGE" in target.read_text(encoding="utf-8")
