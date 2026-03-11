import importlib

import config


def reload_config_module():
    return importlib.reload(config)


def test_nvidia_model_uses_new_builtin_default(monkeypatch):
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)

    reloaded = reload_config_module()

    assert not hasattr(reloaded, "NVIDIA_DEFAULT_MODEL")
    assert reloaded.NVIDIA_MODEL == "qwen/qwen3-next-80b-a3b-instruct"


def test_nvidia_model_uses_env_override(monkeypatch):
    monkeypatch.setenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_MODEL == "meta/llama-3.3-70b-instruct"


def test_nvidia_secondary_model_uses_builtin_default(monkeypatch):
    monkeypatch.delenv("NVIDIA_SECONDARY_MODEL", raising=False)

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_SECONDARY_MODEL == "moonshotai/kimi-k2-instruct-0905"


def test_nvidia_secondary_model_uses_env_override(monkeypatch):
    monkeypatch.setenv("NVIDIA_SECONDARY_MODEL", "moonshotai/custom-secondary")

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_SECONDARY_MODEL == "moonshotai/custom-secondary"


def test_llm_concurrency_uses_new_default(monkeypatch):
    monkeypatch.delenv("LLM_CONCURRENCY", raising=False)

    reloaded = reload_config_module()

    assert reloaded.LLM_CONCURRENCY == 5


def test_use_custom_api_uses_builtin_default_false(monkeypatch):
    monkeypatch.delenv("USE_CUSTOM_API", raising=False)

    reloaded = reload_config_module()

    assert reloaded.USE_CUSTOM_API is False


def test_use_custom_api_uses_env_override(monkeypatch):
    monkeypatch.setenv("USE_CUSTOM_API", "true")

    reloaded = reload_config_module()

    assert reloaded.USE_CUSTOM_API is True
