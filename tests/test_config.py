from cp_knowledge_tools.common.config import load_project_config


def test_load_project_config(tmp_path, monkeypatch) -> None:
    email_import_root = tmp_path / "email-imports"
    email_import_root.mkdir()
    monkeypatch.setenv("KNOWLEDGE_IMPORT_EMAIL_ROOT", str(email_import_root))

    config = load_project_config()

    assert config.project_name == "cpKnowledgeSystem"
    assert config.email_import_root == email_import_root
    assert config.email_import_root.exists()
    assert config.rules_path.name == "classification_rules.yaml"
    assert config.overrides_path.name == "classification_overrides.yaml"
