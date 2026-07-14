from knowledge_importer.common.config import load_project_config


def test_load_project_config() -> None:
    config = load_project_config()

    assert config.project_name == "KnowledgeImporter"
    assert config.email_import_root.exists()
    assert config.rules_path.name == "classification_rules.yaml"
    assert config.overrides_path.name == "classification_overrides.yaml"