import importlib

import config


def reload_config_module():
    return importlib.reload(config)


def test_nvidia_model_uses_new_builtin_default(monkeypatch):
    monkeypatch.delenv("NVIDIA_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_DEFAULT_MODEL == "qwen/qwen3-next-80b-a3b-instruct"
    assert reloaded.NVIDIA_MODEL == "qwen/qwen3-next-80b-a3b-instruct"


def test_nvidia_model_can_follow_default_model_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_DEFAULT_MODEL", "meta/llama-3.3-70b-instruct")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_DEFAULT_MODEL == "meta/llama-3.3-70b-instruct"
    assert reloaded.NVIDIA_MODEL == "meta/llama-3.3-70b-instruct"


def test_nvidia_model_env_overrides_default_model_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_DEFAULT_MODEL", "meta/llama-3.3-70b-instruct")
    monkeypatch.setenv("NVIDIA_MODEL", "moonshotai/kimi-k2-thinking")

    reloaded = reload_config_module()

    assert reloaded.NVIDIA_DEFAULT_MODEL == "meta/llama-3.3-70b-instruct"
    assert reloaded.NVIDIA_MODEL == "moonshotai/kimi-k2-thinking"


def test_llm_concurrency_uses_new_default(monkeypatch):
    monkeypatch.delenv("LLM_CONCURRENCY", raising=False)

    reloaded = reload_config_module()

    assert reloaded.LLM_CONCURRENCY == 5
