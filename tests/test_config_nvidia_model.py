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


def test_llm_concurrency_uses_new_default(monkeypatch):
    monkeypatch.delenv("LLM_CONCURRENCY", raising=False)

    reloaded = reload_config_module()

    assert reloaded.LLM_CONCURRENCY == 5
