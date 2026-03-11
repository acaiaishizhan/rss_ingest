import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import rss_ingest
from rss_ingest import (
    collect_queue_items,
    persist_ready_source_states,
    run_llm_queue,
    split_sources_and_queue,
)


def test_collect_queue_items_skips_existing_keys():
    items = [
        {"item_key": "a", "content": "x"},
        {"item_key": "b", "content": "y"},
    ]
    existing = {"a"}
    out = collect_queue_items(items, existing)
    assert [i["item_key"] for i in out] == ["b"]


def test_split_sources_and_queue_returns_queue(monkeypatch):
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", lambda *args, **kwargs: None)
    sources = [{"feed_url": "x", "enabled": False, "record_id": "r1"}]
    queue, source_states, stats = split_sources_and_queue(sources, existing_keys=set(), tenant_token="t")
    assert isinstance(queue, list)
    assert isinstance(source_states, dict)
    assert isinstance(stats, dict)


def test_split_sources_and_queue_dedupes_same_key_in_single_feed(monkeypatch):
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        rss_ingest,
        "fetch_feed",
        lambda *args, **kwargs: SimpleNamespace(entries=[{"id": "dup"}, {"id": "dup"}]),
    )
    sources = [
        {
            "feed_url": "https://example.com/rss",
            "enabled": True,
            "record_id": "r1",
            "name": "feed-1",
            "item_id_strategy": "guid",
            "content_hash_algo": "md5",
            "last_item_pub_time": 0,
            "last_fetch_time": 0,
            "consecutive_fail_count": 0,
            "failed_items": None,
        }
    ]

    queue, source_states, stats = split_sources_and_queue(sources, existing_keys=set(), tenant_token="t")

    assert [item["item_key"] for item in queue] == ["dup"]
    assert source_states["r1"]["pending_count"] == 1
    assert stats["queue_total"] == 1


def test_split_sources_and_queue_skips_malformed_entry(monkeypatch):
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        rss_ingest,
        "fetch_feed",
        lambda *args, **kwargs: SimpleNamespace(entries=[{"id": "ok"}, object()]),
    )
    sources = [
        {
            "feed_url": "https://example.com/rss",
            "enabled": True,
            "record_id": "r1",
            "name": "feed-1",
            "item_id_strategy": "guid",
            "content_hash_algo": "md5",
            "last_item_pub_time": 0,
            "last_fetch_time": 0,
            "consecutive_fail_count": 0,
            "failed_items": None,
        }
    ]

    queue, source_states, stats = split_sources_and_queue(sources, existing_keys=set(), tenant_token="t")

    assert [item["item_key"] for item in queue] == ["ok"]
    assert source_states["r1"]["pending_count"] == 1
    assert stats["queue_total"] == 1


def test_analyze_with_nvidia_fallback_to_custom_api(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "n-key")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_MODEL", "model-primary")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_KEY", "c-key")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_BASE", "https://custom.example.com/v1")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_MODEL", "custom-model")

    calls = []

    def fake_call(service_name, base_url, api_key, model_name, prompt):
        calls.append((service_name, base_url, api_key, model_name))
        if service_name == "NVIDIA":
            return (
                {"categories": ["调用异常"], "score": 0.0, "summary": "", "title_zh": "", "one_liner": "", "points": []},
                "HTTP 500",
            )
        return {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []}, ""

    monkeypatch.setattr(rss_ingest, "call_openai_compatible", fake_call)

    result = rss_ingest.analyze_with_nvidia({"title": "t", "content": "c"}, "prompt")

    assert result["categories"] == ["news"]
    assert any(service == "Custom" for service, *_rest in calls)
    assert ("Custom", "https://custom.example.com/v1", "c-key", "custom-model") in calls


def test_secondary_nvidia_constants_are_updated():
    assert rss_ingest.SECONDARY_NVIDIA_MODEL == "moonshotai/kimi-k2-instruct-0905"
    assert rss_ingest.PRIMARY_NVIDIA_MAX_TOKENS == 4096


def test_analyze_with_nvidia_marks_secondary_success(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "n-key")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", [])
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_MODEL", "model-primary")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_KEY", "")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_BASE", "")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_MODEL", "")

    calls = []

    def fake_call(service_name, base_url, api_key, model_name, prompt):
        calls.append((service_name, model_name))
        if model_name == "model-primary":
            return rss_ingest.llm_failure("NVIDIA HTTP 500"), "HTTP 500"
        return {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []}, ""

    monkeypatch.setattr(rss_ingest, "call_openai_compatible", fake_call)

    result = rss_ingest.analyze_with_nvidia({"title": "t", "content": "c", "source": "feed"}, "prompt")

    assert result["categories"] == ["news"]
    assert result["_llm_meta"]["switched_to_secondary"] is True
    assert result["_llm_meta"]["secondary_success"] is True
    assert result["_llm_meta"]["final_model"] == rss_ingest.SECONDARY_NVIDIA_MODEL
    assert calls == [
        ("NVIDIA", "model-primary"),
        ("NVIDIA", rss_ingest.SECONDARY_NVIDIA_MODEL),
    ]


def test_get_nvidia_models_keeps_both_models_on_large_queue(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_MODEL", "model-primary")

    assert rss_ingest.get_nvidia_models(queue_total=10) == [
        "model-primary",
        rss_ingest.SECONDARY_NVIDIA_MODEL,
    ]
    assert rss_ingest.get_nvidia_models(queue_total=101) == [
        "model-primary",
        rss_ingest.SECONDARY_NVIDIA_MODEL,
    ]


def test_analyze_with_nvidia_keeps_primary_first_for_large_queue(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "n-key")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", [])
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_MODEL", "model-primary")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_KEY", "")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_BASE", "")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_MODEL", "")

    calls = []

    def fake_call(service_name, base_url, api_key, model_name, prompt):
        calls.append((service_name, model_name))
        return {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []}, ""

    monkeypatch.setattr(rss_ingest, "call_openai_compatible", fake_call)

    result = rss_ingest.analyze_with_nvidia(
        {"title": "t", "content": "c", "source": "feed"},
        "prompt",
        queue_total=101,
    )

    assert result["categories"] == ["news"]
    assert result["_llm_meta"]["primary_model"] == "model-primary"
    assert result["_llm_meta"]["final_model"] == "model-primary"
    assert result["_llm_meta"]["switched_to_secondary"] is False
    assert calls == [("NVIDIA", "model-primary")]


def test_validate_runtime_config_accepts_complete_custom_api(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "FEISHU_APP_ID", "app-id")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_APP_SECRET", "app-secret")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_NEWS_APP_TOKEN", "news-token")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_NEWS_TABLE_ID", "news-table")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_RSS_APP_TOKEN", "rss-token")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_RSS_TABLE_ID", "rss-table")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_PROMPT_DOC_TOKEN", "doc-token")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", [])
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_KEY", "c-key")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_BASE", "https://custom.example.com/v1")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_MODEL", "custom-model")

    assert rss_ingest.validate_runtime_config() == []


def test_validate_runtime_config_rejects_incomplete_custom_api(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "FEISHU_APP_ID", "app-id")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_APP_SECRET", "app-secret")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_NEWS_APP_TOKEN", "news-token")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_NEWS_TABLE_ID", "news-table")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_RSS_APP_TOKEN", "rss-token")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_RSS_TABLE_ID", "rss-table")
    monkeypatch.setattr(rss_ingest.config, "FEISHU_PROMPT_DOC_TOKEN", "doc-token")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", [])
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_KEY", "c-key")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_BASE", "")
    monkeypatch.setattr(rss_ingest.config, "CUSTOM_API_MODEL", "")

    errors = rss_ingest.validate_runtime_config()

    assert "CUSTOM_API 配置不完整" in errors[0]
    assert any("至少需要配置 NVIDIA_API_KEY / NVIDIA_API_KEYS" in error for error in errors)


def test_call_openai_compatible_retries_on_empty_json(monkeypatch):
    monkeypatch.setattr(rss_ingest, "LLM_MAX_RETRY", 3)
    monkeypatch.setattr(rss_ingest.time, "sleep", lambda *_args, **_kwargs: None)

    class FakeResp:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    responses = [
        FakeResp({"choices": [{"message": {"content": ""}}]}),
        FakeResp({"choices": [{"message": {"content": "{\"categories\":[\"news\"],\"score\":1,\"one_liner\":\"\",\"points\":[]}"}}]}),
    ]
    call_count = {"n": 0}

    def fake_post(*_args, **_kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    monkeypatch.setattr(rss_ingest.requests, "post", fake_post)

    result, reason = rss_ingest.call_openai_compatible(
        "NVIDIA",
        "https://example.com/v1",
        "k",
        "m",
        "prompt",
    )

    assert reason == ""
    assert result["categories"] == ["news"]
    assert call_count["n"] == 2


def test_call_openai_compatible_retries_on_invalid_action(monkeypatch):
    monkeypatch.setattr(rss_ingest, "LLM_MAX_RETRY", 3)
    monkeypatch.setattr(rss_ingest.time, "sleep", lambda *_args, **_kwargs: None)

    class FakeResp:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    responses = [
        FakeResp({"choices": [{"message": {"content": "{\"action\":\"skip\",\"categories\":[\"news\"],\"score\":1,\"one_liner\":\"\",\"points\":[]}"}}]}),
        FakeResp({"choices": [{"message": {"content": "{\"action\":\"ingest\",\"categories\":[\"news\"],\"score\":1,\"one_liner\":\"\",\"points\":[]}"}}]}),
    ]
    call_count = {"n": 0}

    def fake_post(*_args, **_kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    monkeypatch.setattr(rss_ingest.requests, "post", fake_post)

    result, reason = rss_ingest.call_openai_compatible(
        "NVIDIA",
        "https://example.com/v1",
        "k",
        "m",
        "prompt",
    )

    assert reason == ""
    assert result["action"] == "ingest"
    assert result["categories"] == ["news"]
    assert call_count["n"] == 2


def test_call_openai_compatible_uses_model_specific_max_tokens(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_MODEL", "model-primary")

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "{\"categories\":[\"news\"],\"score\":1,\"one_liner\":\"\",\"points\":[]}"
                        }
                    }
                ]
            }

    payloads = []

    def fake_post(_url, headers=None, json=None, timeout=None):
        payloads.append(json)
        return FakeResp()

    monkeypatch.setattr(rss_ingest.requests, "post", fake_post)

    rss_ingest.call_openai_compatible("NVIDIA", "https://example.com/v1", "k", "model-primary", "prompt")
    rss_ingest.call_openai_compatible(
        "NVIDIA",
        "https://example.com/v1",
        "k",
        rss_ingest.SECONDARY_NVIDIA_MODEL,
        "prompt",
    )

    assert payloads[0]["max_tokens"] == rss_ingest.PRIMARY_NVIDIA_MAX_TOKENS
    assert payloads[1]["max_tokens"] == rss_ingest.SECONDARY_NVIDIA_MAX_TOKENS


def test_get_nvidia_api_keys_merges_primary_and_extra(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "k1")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", ["k2", "k1", "k3"])

    assert rss_ingest.get_nvidia_api_keys() == ["k1", "k2", "k3"]


def test_get_effective_llm_workers_uses_per_key_concurrency(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 3)
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "k1")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", ["k2", "k3"])

    assert rss_ingest.get_effective_llm_workers() == 9


def test_get_effective_llm_workers_fallback_only(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 3)
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", [])

    assert rss_ingest.get_effective_llm_workers() == 3


def test_call_nvidia_compatible_uses_multiple_keys_in_parallel(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "k1")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", ["k2"])

    barrier = threading.Barrier(2)
    used_keys = []
    used_keys_lock = threading.Lock()

    def fake_call(service_name, base_url, api_key, model_name, prompt):
        barrier.wait(timeout=1)
        with used_keys_lock:
            used_keys.append(api_key)
        time.sleep(0.05)
        return {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []}, ""

    monkeypatch.setattr(rss_ingest, "call_openai_compatible", fake_call)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(rss_ingest.call_nvidia_compatible, "model-primary", "prompt-1"),
            executor.submit(rss_ingest.call_nvidia_compatible, "model-primary", "prompt-2"),
        ]
        for future in futures:
            result, reason = future.result()
            assert reason == ""
            assert result["categories"] == ["news"]

    assert used_keys == ["k1", "k2"] or used_keys == ["k2", "k1"]


def test_run_llm_queue_skips_duplicate_writes(monkeypatch):
    create_calls = []
    update_calls = []

    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 2)
    monkeypatch.setattr(
        rss_ingest,
        "analyze_with_nvidia",
        lambda article, prompt, queue_total=0: {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []},
    )

    def fake_create(*args, **kwargs):
        fields = args[3]
        create_calls.append(fields[rss_ingest.config.NEWS_FIELD_ITEM_KEY])
        time.sleep(0.05)
        return True, "news-record"

    def fake_update(*args, **kwargs):
        update_calls.append(args[3])
        return True

    monkeypatch.setattr(rss_ingest, "create_bitable_record_with_id", fake_create)
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", fake_update)

    source_states = {
        "r1": {
            "source": {"record_id": "r1", "name": "feed-1", "feed_url": "https://example.com/rss"},
            "now_ms": 123,
            "latest_pub_ms": 456,
            "latest_key": "dup",
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 2,
            "persisted": False,
        }
    }
    queue = [
        {
            "source_id": "r1",
            "item_key": "dup",
            "article": {"title": "same", "content": "x", "link": "", "published": 0, "source": "feed-1"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        },
        {
            "source_id": "r1",
            "item_key": "dup",
            "article": {"title": "same", "content": "x", "link": "", "published": 0, "source": "feed-1"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        },
    ]
    stats = {
        "llm_success": 0,
        "llm_failed": 0,
        "feishu_create_failed": 0,
        "entries_processed": 0,
        "entries_new": 0,
    }
    existing_keys = set()

    run_llm_queue(queue, source_states, "tenant", existing_keys, "prompt", stats)

    assert create_calls == ["dup"]
    assert update_calls == ["r1"]
    assert source_states["r1"]["pending_count"] == 0
    assert source_states["r1"]["new_count"] == 1
    assert source_states["r1"]["persisted"] is True
    assert "dup" in existing_keys


def test_run_llm_queue_counts_secondary_switch(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 1)
    monkeypatch.setattr(
        rss_ingest,
        "analyze_with_nvidia",
        lambda article, prompt, queue_total=0: {
            "categories": ["news"],
            "score": 1.0,
            "one_liner": "",
            "points": [],
            "_llm_meta": {"switched_to_secondary": True, "secondary_success": True},
        },
    )
    monkeypatch.setattr(rss_ingest, "create_bitable_record_with_id", lambda *args, **kwargs: (True, "news-record"))
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", lambda *args, **kwargs: True)

    source_states = {
        "r1": {
            "source": {"record_id": "r1", "name": "feed-1", "feed_url": "https://example.com/rss"},
            "now_ms": 123,
            "latest_pub_ms": 456,
            "latest_key": "k1",
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 1,
            "persisted": False,
        }
    }
    queue = [
        {
            "source_id": "r1",
            "item_key": "k1",
            "article": {"title": "t", "content": "x", "link": "", "published": 0, "source": "feed-1"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        }
    ]
    stats = {
        "llm_success": 0,
        "llm_failed": 0,
        "feishu_create_failed": 0,
        "entries_processed": 0,
        "entries_new": 0,
    }

    run_llm_queue(queue, source_states, "tenant", set(), "prompt", stats)

    assert stats["llm_requests_total"] == 1
    assert stats["llm_switched_to_secondary"] == 1
    assert stats["llm_secondary_success"] == 1
    assert stats["llm_success"] == 1


def test_run_llm_queue_passes_total_to_analyze(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 1)
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "k1")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", [])

    seen_totals = []

    def fake_analyze(article, prompt, queue_total=0):
        seen_totals.append(queue_total)
        return {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []}

    monkeypatch.setattr(rss_ingest, "analyze_with_nvidia", fake_analyze)
    monkeypatch.setattr(rss_ingest, "create_bitable_record_with_id", lambda *args, **kwargs: (True, "news-record"))
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", lambda *args, **kwargs: True)

    source_states = {
        "r1": {
            "source": {"record_id": "r1", "name": "feed-1", "feed_url": "https://example.com/rss"},
            "now_ms": 123,
            "latest_pub_ms": 456,
            "latest_key": "k1",
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 2,
            "persisted": False,
        }
    }
    queue = [
        {
            "source_id": "r1",
            "item_key": "k1",
            "article": {"title": "t1", "content": "x", "link": "", "published": 0, "source": "feed-1"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        },
        {
            "source_id": "r1",
            "item_key": "k2",
            "article": {"title": "t2", "content": "y", "link": "", "published": 0, "source": "feed-1"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        },
    ]
    stats = {
        "llm_success": 0,
        "llm_failed": 0,
        "feishu_create_failed": 0,
        "entries_processed": 0,
        "entries_new": 0,
    }

    run_llm_queue(queue, source_states, "tenant", set(), "prompt", stats)

    assert seen_totals == [2, 2]


def test_run_llm_queue_uses_effective_worker_count(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 3)
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "k1")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEYS", ["k2", "k3"])

    seen_workers = []

    class FakeExecutor:
        def __init__(self, max_workers):
            seen_workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, item):
            class FakeFuture:
                def result(self_inner):
                    return fn(item)

            return FakeFuture()

    monkeypatch.setattr(rss_ingest, "ThreadPoolExecutor", FakeExecutor)
    monkeypatch.setattr(rss_ingest, "as_completed", lambda futures: futures)
    monkeypatch.setattr(
        rss_ingest,
        "analyze_with_nvidia",
        lambda article, prompt, queue_total=0: {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []},
    )
    monkeypatch.setattr(rss_ingest, "create_bitable_record_with_id", lambda *args, **kwargs: (True, "news-record"))
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", lambda *args, **kwargs: True)

    source_states = {
        "r1": {
            "source": {"record_id": "r1", "name": "feed-1", "feed_url": "https://example.com/rss"},
            "now_ms": 123,
            "latest_pub_ms": 456,
            "latest_key": "k1",
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 2,
            "persisted": False,
        }
    }
    queue = [
        {
            "source_id": "r1",
            "item_key": "k1",
            "article": {"title": "t1", "content": "x", "link": "", "published": 0, "source": "feed-1"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        },
        {
            "source_id": "r1",
            "item_key": "k2",
            "article": {"title": "t2", "content": "y", "link": "", "published": 0, "source": "feed-1"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        },
    ]
    stats = {
        "llm_success": 0,
        "llm_failed": 0,
        "feishu_create_failed": 0,
        "entries_processed": 0,
        "entries_new": 0,
    }

    run_llm_queue(queue, source_states, "tenant", set(), "prompt", stats)

    assert seen_workers == [2]


def test_run_llm_queue_filters_pass_action(monkeypatch):
    create_calls = []
    update_calls = []

    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 1)
    monkeypatch.setattr(
        rss_ingest,
        "analyze_with_nvidia",
        lambda article, prompt, queue_total=0: {"action": "pass", "reason": "命中过滤规则"},
    )

    def fake_create(*args, **kwargs):
        create_calls.append((args, kwargs))
        return True, "news-record"

    def fake_update(*args, **kwargs):
        update_calls.append(args[3])
        return True

    monkeypatch.setattr(rss_ingest, "create_bitable_record_with_id", fake_create)
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", fake_update)

    source_states = {
        "r1": {
            "source": {"record_id": "r1", "name": "feed-1", "feed_url": "https://example.com/rss"},
            "now_ms": 123,
            "latest_pub_ms": 456,
            "latest_key": "k1",
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 1,
            "persisted": False,
        }
    }
    queue = [
        {
            "source_id": "r1",
            "item_key": "k1",
            "article": {"title": "t", "content": "x", "link": "", "published": 0, "source": "feed-1"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        }
    ]
    stats = {
        "llm_success": 0,
        "llm_failed": 0,
        "feishu_create_failed": 0,
        "entries_processed": 0,
        "entries_new": 0,
    }

    run_llm_queue(queue, source_states, "tenant", set(), "prompt", stats)

    assert stats["llm_filtered"] == 1
    assert stats["llm_success"] == 0
    assert stats["llm_failed"] == 0
    assert stats["entries_new"] == 0
    assert create_calls == []
    assert update_calls == ["r1"]
    assert source_states["r1"]["pending_count"] == 0
    assert source_states["r1"]["persisted"] is True


def test_run_llm_queue_persists_finished_source_before_slow_source(monkeypatch):
    events = []

    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 2)
    monkeypatch.setattr(
        rss_ingest,
        "analyze_with_nvidia",
        lambda article, prompt, queue_total=0: {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []},
    )

    def fake_create(*args, **kwargs):
        fields = args[3]
        item_key = fields[rss_ingest.config.NEWS_FIELD_ITEM_KEY]
        events.append(f"create_start:{item_key}")
        if item_key == "slow":
            time.sleep(0.2)
        else:
            time.sleep(0.02)
        events.append(f"create_end:{item_key}")
        return True, f"news-{item_key}"

    def fake_update(*args, **kwargs):
        events.append(f"persist:{args[3]}")
        return True

    monkeypatch.setattr(rss_ingest, "create_bitable_record_with_id", fake_create)
    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", fake_update)

    source_states = {
        "fast-src": {
            "source": {"record_id": "fast-src", "name": "fast", "feed_url": "https://example.com/fast"},
            "now_ms": 1,
            "latest_pub_ms": 10,
            "latest_key": "fast",
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 1,
            "persisted": False,
        },
        "slow-src": {
            "source": {"record_id": "slow-src", "name": "slow", "feed_url": "https://example.com/slow"},
            "now_ms": 2,
            "latest_pub_ms": 20,
            "latest_key": "slow",
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 1,
            "persisted": False,
        },
    }
    queue = [
        {
            "source_id": "fast-src",
            "item_key": "fast",
            "article": {"title": "fast", "content": "x", "link": "", "published": 0, "source": "fast"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        },
        {
            "source_id": "slow-src",
            "item_key": "slow",
            "article": {"title": "slow", "content": "y", "link": "", "published": 0, "source": "slow"},
            "entry_ts": 0,
            "entry_ts_ms": 0,
            "from_failed": False,
        },
    ]
    stats = {
        "llm_success": 0,
        "llm_failed": 0,
        "feishu_create_failed": 0,
        "entries_processed": 0,
        "entries_new": 0,
    }

    run_llm_queue(queue, source_states, "tenant", set(), "prompt", stats)

    assert events.index("persist:fast-src") < events.index("create_end:slow")


def test_persist_ready_source_states_updates_zero_pending_source(monkeypatch):
    update_calls = []

    def fake_update(*args, **kwargs):
        update_calls.append(args[3])
        return True

    monkeypatch.setattr(rss_ingest, "update_bitable_record_fields", fake_update)

    source_states = {
        "r1": {
            "source": {"record_id": "r1", "name": "feed-1", "feed_url": "https://example.com/rss"},
            "now_ms": 123,
            "latest_pub_ms": 456,
            "latest_key": "k1",
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 0,
            "persisted": False,
        }
    }

    persist_ready_source_states(source_states, "tenant")

    assert update_calls == ["r1"]
    assert source_states["r1"]["persisted"] is True
