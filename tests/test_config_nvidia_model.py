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


def test_nvidia_screen_model_uses_builtin_empty_default(monkeypatch):
    monkeypatch.setenv("NVIDIA_SCREEN_MODEL", "")

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_SCREEN_MODEL == ""


def test_nvidia_screen_model_uses_env_override(monkeypatch):
    monkeypatch.setenv("NVIDIA_SCREEN_MODEL", "screen-model")

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_SCREEN_MODEL == "screen-model"


def test_nvidia_summarize_model_uses_builtin_empty_default(monkeypatch):
    monkeypatch.setenv("NVIDIA_SUMMARIZE_MODEL", "")

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_SUMMARIZE_MODEL == ""


def test_nvidia_summarize_model_uses_env_override(monkeypatch):
    monkeypatch.setenv("NVIDIA_SUMMARIZE_MODEL", "summarize-model")

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_SUMMARIZE_MODEL == "summarize-model"


def test_llm_concurrency_uses_new_default(monkeypatch):
    monkeypatch.setenv("LLM_CONCURRENCY", "")

    reloaded = reload_config_module()

    assert reloaded.LLM_CONCURRENCY == 3


def test_use_custom_api_uses_builtin_default_false(monkeypatch):
    monkeypatch.delenv("USE_CUSTOM_API", raising=False)

    reloaded = reload_config_module()

    assert reloaded.USE_CUSTOM_API is False


def test_use_custom_api_uses_env_override(monkeypatch):
    monkeypatch.setenv("USE_CUSTOM_API", "true")

    reloaded = reload_config_module()

    assert reloaded.USE_CUSTOM_API is True


def test_auto_fetch_interval_hours_uses_builtin_default(monkeypatch):
    monkeypatch.delenv("AUTO_FETCH_INTERVAL_HOURS", raising=False)

    reloaded = reload_config_module()

    assert reloaded.AUTO_FETCH_INTERVAL_HOURS == 3


def test_auto_fetch_interval_hours_uses_env_override(monkeypatch):
    monkeypatch.setenv("AUTO_FETCH_INTERVAL_HOURS", "6")

    reloaded = reload_config_module()

    assert reloaded.AUTO_FETCH_INTERVAL_HOURS == 6
