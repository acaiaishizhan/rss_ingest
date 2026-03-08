import os
import sys
import time
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


def test_analyze_with_nvidia_fallback_to_openai_compatible(monkeypatch):
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_API_KEY", "n-key")
    monkeypatch.setattr(rss_ingest.config, "NVIDIA_MODEL", "model-primary")
    monkeypatch.setattr(rss_ingest.config, "FALLBACK_LLM_API_KEY", "f-key")
    monkeypatch.setattr(rss_ingest.config, "FALLBACK_LLM_BASE_URL", "https://fallback.example.com/v1")

    calls = []

    def fake_call(service_name, base_url, api_key, model_name, prompt):
        calls.append((service_name, model_name))
        if service_name == "NVIDIA":
            return (
                {"categories": ["调用异常"], "score": 0.0, "summary": "", "title_zh": "", "one_liner": "", "points": []},
                "HTTP 500",
            )
        return {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []}, ""

    monkeypatch.setattr(rss_ingest, "call_openai_compatible", fake_call)

    result = rss_ingest.analyze_with_nvidia({"title": "t", "content": "c"}, "prompt")

    assert result["categories"] == ["news"]
    assert any(service == "Fallback" for service, _ in calls)


def test_run_llm_queue_skips_duplicate_writes(monkeypatch):
    create_calls = []
    update_calls = []

    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 2)
    monkeypatch.setattr(
        rss_ingest,
        "analyze_with_nvidia",
        lambda article, prompt: {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []},
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


def test_run_llm_queue_persists_finished_source_before_slow_source(monkeypatch):
    events = []

    monkeypatch.setattr(rss_ingest.config, "LLM_CONCURRENCY", 2)
    monkeypatch.setattr(
        rss_ingest,
        "analyze_with_nvidia",
        lambda article, prompt: {"categories": ["news"], "score": 1.0, "one_liner": "", "points": []},
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
