from pathlib import Path

from cp_knowledge_tools.template_generator.generator import TemplateGenerator


def test_validator_detects_tab_character(tmp_path: Path) -> None:
    generator = TemplateGenerator()
    result = generator.generate("organizations", tmp_path)
    target = result.output_root / "00 Organization Template.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("owner: ORG-TBD", "owner:\tORG-TBD"),
        encoding="utf-8",
    )

    errors = generator.validate("organizations", tmp_path)

    assert any("Tabulatorzeichen" in error for error in errors)
