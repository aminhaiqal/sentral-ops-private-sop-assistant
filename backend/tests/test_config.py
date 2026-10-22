import importlib.util
import sys

from app.config import PROJECT_ROOT, Settings


def test_environment_example_loads_with_frontend_and_deployment_settings(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=PROJECT_ROOT / ".env.example")

    assert not settings.openai_api_key
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.app_name == "Axelyn"


def test_defaults_load_root_environment_when_started_from_backend(tmp_path, monkeypatch):
    # Reproduce a fresh project without reading or modifying the developer's .env.
    config_path = tmp_path / "backend" / "app" / "config.py"
    config_path.parent.mkdir(parents=True)
    config_path.write_text((PROJECT_ROOT / "backend" / "app" / "config.py").read_text())
    (tmp_path / ".env").write_text("QDRANT_COLLECTION=root-environment\nVITE_API_URL=\n")
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    monkeypatch.chdir(tmp_path / "backend")

    spec = importlib.util.spec_from_file_location("isolated_config", config_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    assert module.Settings().qdrant_collection == "root-environment"


def test_explicit_env_file_and_environment_override_defaults(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "QDRANT_COLLECTION=from-file\nVITE_API_URL=\nAPP_DOMAIN=assistant.example.com\n"
    )
    monkeypatch.setenv("QDRANT_COLLECTION", "from-environment")

    assert Settings(_env_file=env_file).qdrant_collection == "from-environment"
