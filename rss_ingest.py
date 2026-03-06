# -*- coding: utf-8 -*-
import datetime as dt
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional

import requests

import config
from feishu_client import (
    create_bitable_record_with_id,
    get_document_raw_content,
    get_tenant_access_token,
    list_bitable_records,
    update_bitable_record_fields,
)
from rss_parser import build_item_key, entry_published_ts, entry_text_content, fetch_feed

FAILED_CATEGORIES = {"调用失败", "调用异常", "解析失败", "JSON解析失败", "异常"}

def log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = msg.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe, flush=True)


def truncate_text(text: str, limit: int = 1000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit - 3] + "..."


def collect_queue_items(items: Iterable[dict], existing_keys: set) -> list:
    out = []
    for item in items:
        key = item.get("item_key")
        if not key or key in existing_keys:
            continue
        out.append(item)
    return out


def enqueue_unique_item(
    queue: List[Dict[str, Any]],
    queued_keys: set,
    source_state: Dict[str, Any],
    item: Dict[str, Any],
) -> bool:
    item_key = str(item.get("item_key") or "").strip()
    if not item_key or item_key in queued_keys:
        return False
    queue.append(item)
    queued_keys.add(item_key)
    source_state["pending_count"] += 1
    return True


def render_progress(done: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "0/0 [" + "".ljust(width, ".") + "]"
    filled = int(width * done / total)
    return f"{done}/{total} [" + "#" * filled + "." * (width - filled) + "]"



def clean_feishu_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        if "text" in value and isinstance(value["text"], str):
            return value["text"]
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                t = item.get("text")
                parts.append(t if isinstance(t, str) else str(item))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(value)


def is_checked(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "yes", "y", "1", "checked", "on"):
            return True
        if s in ("false", "no", "n", "0", ""):
            return False
        return True
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return True
    return bool(value)


def parse_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        s = str(value).strip()
        return int(s) if s else None
    except Exception:
        return None


def parse_ts_ms(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    fmts = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
    for fmt in fmts:
        try:
            dt_obj = dt.datetime.strptime(s, fmt)
            return int(dt_obj.timestamp() * 1000)
        except Exception:
            continue
    return 0


def clean_html_to_text(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p\s*>", "\n", html)
    html = re.sub(r"(?i)</div\s*>", "\n", html)
    html = re.sub(r"(?i)</li\s*>", "\n", html)
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_single_select(value: Any, allowed: set, default: str = "") -> str:
    s = clean_feishu_value(value).strip()
    return s if s in allowed else default


def derive_fetch_status(exc: Exception) -> str:
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return config.FETCH_STATUS_TIMEOUT
    if "parse" in msg:
        return config.FETCH_STATUS_PARSE_ERROR
    if "http" in msg:
        return config.FETCH_STATUS_HTTP_ERROR
    return config.FETCH_STATUS_HTTP_ERROR


def derive_overall_status(consecutive_fail: int, enabled: bool) -> str:
    if not enabled:
        return config.STATUS_IDLE
    if consecutive_fail >= 5:
        return config.STATUS_DEAD
    if consecutive_fail >= 2:
        return config.STATUS_UNSTABLE
    return config.STATUS_OK


def nvidia_headers() -> Dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {config.NVIDIA_API_KEY}"}


def build_prompt(article: Dict[str, Any], system_prompt: str) -> str:
    china_tz = dt.timezone(dt.timedelta(hours=8))
    now = dt.datetime.now(china_tz)
    return f"""{system_prompt}

你所处的时间为：{now.year}年{now.month:02d}月

title：{article.get('title','')}
content：{article.get('content','')}
"""


def extract_json_object(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    t = t.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    first = t.find("{")
    last = t.rfind("}")
    if first != -1 and last != -1 and last > first:
        return t[first:last + 1]
    return t


def parse_llm_json(raw_text: str, service: str) -> Optional[Dict[str, Any]]:
    json_str = extract_json_object(raw_text)
    if not json_str:
        log(f"[{service}] parse error: empty json")
        return None
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as exc:
        log(f"[{service}] parse error: {exc}")
        return None
 
def analyze_with_nvidia(article: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
    if not config.NVIDIA_API_KEY:
        log("[NVIDIA] error: missing NVIDIA_API_KEY")
        return {"categories": ["调用失败"], "score": 0.0, "summary": "missing NVIDIA_API_KEY", "title_zh": "", "one_liner": "", "points": []}

    prompt = build_prompt(article, system_prompt)
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload: Dict[str, Any] = {
        "model": "qwen/qwen3-next-80b-a3b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "top_p": 0.7,
        "max_tokens": 4096,
        "stream": False,
    }

    last_err: Optional[Exception] = None
    last_status_type: Optional[str] = None
    last_status_detail = ""
    for attempt in range(config.NVIDIA_RETRIES):
        try:
            resp = requests.post(url, headers=nvidia_headers(), json=payload, timeout=300)
            if resp.status_code in (401, 403):
                log(f"[NVIDIA] error: HTTP {resp.status_code}")
                return {"categories": ["调用失败"], "score": 0.0, "summary": "", "title_zh": "", "one_liner": "", "points": []}
            if resp.status_code in (429, 500, 502, 503, 504):
                last_status_type = "rate_limit" if resp.status_code == 429 else "server_error"
                last_status_detail = f"HTTP {resp.status_code}"
                time.sleep(1.2 * (attempt + 1))
                continue
            if resp.status_code != 200:
                return {"categories": ["调用失败"], "score": 0.0, "summary": "", "title_zh": "", "one_liner": "", "points": []}

            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return {"categories": ["调用失败"], "score": 0.0, "summary": "", "title_zh": "", "one_liner": "", "points": []}
            message = choices[0].get("message") or {}
            raw_text = (message.get("content") or "").strip()
            if raw_text:
                # Drop <think> blocks to keep final JSON only (align with test.py behavior)
                raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.S)
                if "<think>" in raw_text:
                    raw_text = raw_text.split("<think>", 1)[0]
                raw_text = raw_text.strip()
            result = parse_llm_json(raw_text, "NVIDIA")
            if result is None:
                log(f"[NVIDIA] parse failed, raw={truncate_text(raw_text, 300)}")
                return {"categories": ["调用失败"], "score": 0.0, "summary": "", "title_zh": "", "one_liner": "", "points": []}
            return result
        except Exception as exc:
            last_err = exc
            if "timeout" in str(exc).lower():
                last_status_type = "timeout"
            time.sleep(1.0 + attempt)

    if last_status_type == "rate_limit":
        log(f"[NVIDIA] error: {last_status_detail or 'HTTP 429'}")
    elif last_status_type == "server_error":
        log(f"[NVIDIA] error: {last_status_detail or 'HTTP 5xx'}")
    elif last_status_type == "timeout":
        log(f"[NVIDIA] error: {str(last_err) if last_err else 'timeout'}")
    return {"categories": ["调用异常"], "score": 0.0, "summary": str(last_err) if last_err else "", "title_zh": "", "one_liner": "", "points": []}


def normalize_points(points: Any) -> List[str]:
    if not isinstance(points, list):
        points = [str(points)]
    normalized: List[str] = []
    for p in points:
        if p is None:
            continue
        s = str(p).strip()
        if not s:
            continue
        s = " ".join(s.splitlines()).strip()
        if s:
            normalized.append(s)
    return normalized


def build_summary(one_liner: str, points: List[str]) -> str:
    if one_liner and points:
        return one_liner + "\n" + "\n".join(f"- {p}" for p in points)
    if one_liner:
        return one_liner
    if points:
        return "\n".join(f"- {p}" for p in points)
    return ""


def parse_failed_items(raw: Any) -> List[Dict[str, Any]]:
    if not raw:
        return []
    data: Any = raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            data = json.loads(s)
        except Exception:
            return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    items: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        item_key = str(item.get("item_key") or "").strip()
        if not item_key:
            continue
        items.append(
            {
                "item_key": item_key,
                "title": str(item.get("title") or ""),
                "link": str(item.get("link") or ""),
                "published_ms": parse_int(item.get("published_ms")) or 0,
                "fail_count": parse_int(item.get("fail_count")) or 0,
                "last_error": str(item.get("last_error") or ""),
                "last_seen_ms": parse_int(item.get("last_seen_ms")) or 0,
                "miss_count": parse_int(item.get("miss_count")) or 0,
            }
        )
    return items


def serialize_failed_items(items: List[Dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False)


def upsert_failed_item(
    items: List[Dict[str, Any]],
    item_key: str,
    entry_ts_ms: int,
    title: str,
    link: str,
    reason: str,
    now_ms: int,
) -> List[Dict[str, Any]]:
    for item in items:
        if item.get("item_key") == item_key:
            item["fail_count"] = int(item.get("fail_count") or 0) + 1
            item["last_error"] = reason or item.get("last_error") or ""
            item["last_seen_ms"] = now_ms
            item["miss_count"] = 0
            if title and not item.get("title"):
                item["title"] = title
            if link and not item.get("link"):
                item["link"] = link
            if entry_ts_ms and not item.get("published_ms"):
                item["published_ms"] = entry_ts_ms
            return items

    items.append(
        {
            "item_key": item_key,
            "title": title or "",
            "link": link or "",
            "published_ms": entry_ts_ms or 0,
            "fail_count": 1,
            "last_error": reason or "",
            "last_seen_ms": now_ms,
            "miss_count": 0,
        }
    )
    return items


def prune_failed_items(items: List[Dict[str, Any]], now_ms: int) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for item in items:
        key = item.get("item_key")
        if not key:
            continue
        prev = seen.get(key)
        if not prev or int(item.get("last_seen_ms") or 0) >= int(prev.get("last_seen_ms") or 0):
            seen[key] = item

    max_age_ms = config.FAILED_ITEMS_MAX_AGE_DAYS * 24 * 60 * 60 * 1000
    pruned: List[Dict[str, Any]] = []
    for item in seen.values():
        miss_count = int(item.get("miss_count") or 0)
        if miss_count >= config.FAILED_ITEMS_MAX_MISS:
            continue
        seen_ms = int(item.get("last_seen_ms") or item.get("published_ms") or 0)
        if seen_ms and now_ms - seen_ms > max_age_ms:
            continue
        pruned.append(item)

    pruned.sort(key=lambda x: int(x.get("last_seen_ms") or 0), reverse=True)
    return pruned[: config.FAILED_ITEMS_MAX]


def normalize_source(record: Dict[str, Any]) -> Dict[str, Any]:
    fields = record.get("fields") or {}
    source_id = record.get("record_id") or ""
    enabled = is_checked(fields.get(config.RSS_FIELD_ENABLED))
    last_fetch_time = parse_ts_ms(fields.get(config.RSS_FIELD_LAST_FETCH_TIME))
    last_item_pub_time = parse_ts_ms(fields.get(config.RSS_FIELD_LAST_ITEM_PUB_TIME))
    consecutive_fail = parse_int(fields.get(config.RSS_FIELD_CONSECUTIVE_FAIL_COUNT)) or 0
    item_id_strategy = normalize_single_select(
        fields.get(config.RSS_FIELD_ITEM_ID_STRATEGY),
        config.ITEM_ID_STRATEGY_OPTIONS,
        config.DEFAULT_ITEM_ID_STRATEGY,
    )

    return {
        "record_id": record.get("record_id"),
        "source_id": source_id,
        "name": clean_feishu_value(fields.get(config.RSS_FIELD_NAME)),
        "feed_url": clean_feishu_value(fields.get(config.RSS_FIELD_FEED_URL)),
        "type": clean_feishu_value(fields.get(config.RSS_FIELD_TYPE)),
        "description": clean_feishu_value(fields.get(config.RSS_FIELD_DESCRIPTION)),
        "enabled": enabled,
        "last_fetch_time": last_fetch_time,
        "last_item_pub_time": last_item_pub_time,
        "last_item_guid": clean_feishu_value(fields.get(config.RSS_FIELD_LAST_ITEM_GUID)),
        "item_id_strategy": item_id_strategy,
        "content_hash_algo": config.DEFAULT_CONTENT_HASH_ALGO,
        "consecutive_fail_count": consecutive_fail,
        "failed_items": fields.get(config.RSS_FIELD_FAILED_ITEMS),
    }


def should_fetch(source: Dict[str, Any], now_ms: int) -> bool:
    if not source.get("enabled"):
        return False
    interval_min = config.DEFAULT_FETCH_INTERVAL_MIN
    last_item_pub = source.get("last_item_pub_time") or 0
    last_fetch = source.get("last_fetch_time") or 0
    last_base = last_item_pub or last_fetch
    if last_base <= 0:
        return True
    return now_ms - last_base >= interval_min * 60 * 1000


def build_news_fields(article: Dict[str, Any], analysis: Dict[str, Any], item_key: str) -> Dict[str, Any]:
    published = article.get("published")
    if isinstance(published, (int, float)) and published > 0:
        base_ts = published
    else:
        base_ts = time.time()
    published_ts_ms = int(base_ts * 1000)

    raw_title = article.get("title") or "（无标题）"
    title_zh = (analysis.get("title_zh") or "").strip()
    title_text = title_zh if title_zh else raw_title

    score = float(analysis.get("score", 0.0) or 0.0)
    categories = analysis.get("categories") or []
    if not isinstance(categories, list):
        categories = [str(categories)]

    one_liner = (analysis.get("one_liner") or "").strip()
    points = normalize_points(analysis.get("points") or [])
    summary = build_summary(one_liner, points)

    full_content = clean_html_to_text(article.get("content") or "")

    return {
        config.NEWS_FIELD_TITLE: {"text": title_text, "link": article.get("link") or ""},
        config.NEWS_FIELD_SCORE: score,
        config.NEWS_FIELD_CATEGORIES: categories,
        config.NEWS_FIELD_SUMMARY: summary,
        config.NEWS_FIELD_PUBLISHED_MS: published_ts_ms,
        config.NEWS_FIELD_SOURCE: article.get("source") or "未知来源",
        config.NEWS_FIELD_FULL_CONTENT: full_content,
        config.NEWS_FIELD_ITEM_KEY: item_key,
    }


def prefetch_recent_item_keys(tenant_token: str) -> set:
    sort_field = config.NEWS_FIELD_CREATED_TIME
    sort = [{"field_name": sort_field, "order": "desc"}]
    records = list_bitable_records(
        config.FEISHU_NEWS_APP_TOKEN,
        config.FEISHU_NEWS_TABLE_ID,
        tenant_token,
        config.HTTP_TIMEOUT,
        config.HTTP_RETRIES,
        page_size=config.NEWS_ITEM_KEY_PREFETCH_LIMIT,
        max_pages=1,
        sort=sort,
    )
    keys = set()
    for record in records:
        fields = record.get("fields") or {}
        raw_key = fields.get(config.NEWS_FIELD_ITEM_KEY)
        key = clean_feishu_value(raw_key).strip()
        if key:
            keys.add(key)
    return keys


def build_source_update_fields(state: Dict[str, Any]) -> Dict[str, Any]:
    update_fields: Dict[str, Any] = {
        config.RSS_FIELD_STATUS: config.STATUS_OK,
        config.RSS_FIELD_LAST_FETCH_STATUS: config.FETCH_STATUS_SUCCESS,
        config.RSS_FIELD_CONSECUTIVE_FAIL_COUNT: 0,
        config.RSS_FIELD_LAST_FETCH_TIME: state["now_ms"],
        config.RSS_FIELD_FAILED_ITEMS: serialize_failed_items(
            prune_failed_items(state["updated_failed_items"], state["now_ms"])
        ),
    }
    if state["latest_pub_ms"]:
        update_fields[config.RSS_FIELD_LAST_ITEM_PUB_TIME] = state["latest_pub_ms"]
    if state["latest_key"]:
        update_fields[config.RSS_FIELD_LAST_ITEM_GUID] = state["latest_key"]
    return update_fields


def persist_source_state(state: Dict[str, Any], tenant_token: str) -> bool:
    source = state["source"]
    record_id = source.get("record_id")
    if not record_id:
        return False
    ok = update_bitable_record_fields(
        config.FEISHU_RSS_APP_TOKEN,
        config.FEISHU_RSS_TABLE_ID,
        tenant_token,
        record_id,
        build_source_update_fields(state),
        config.HTTP_TIMEOUT,
        config.HTTP_RETRIES,
    )
    if ok:
        log(f"[RSS] {source.get('name') or source.get('feed_url')} new={state['new_count']}")
    else:
        log(f"[RSS] state update failed for {source.get('name') or source.get('feed_url')}")
    return ok


def persist_ready_source_states(source_states: Dict[str, Dict[str, Any]], tenant_token: str) -> None:
    for state in source_states.values():
        if state.get("pending_count", 0) != 0 or state.get("persisted"):
            continue
        state["persisted"] = True
        if not persist_source_state(state, tenant_token):
            state["persisted"] = False


def split_sources_and_queue(
    sources: List[Dict[str, Any]],
    existing_keys: set,
    tenant_token: str,
) -> tuple[list, dict, dict]:
    queue: List[Dict[str, Any]] = []
    queued_keys: set = set()
    source_states: Dict[str, Dict[str, Any]] = {}
    stats = {
        "sources_processed": 0,
        "sources_skipped": 0,
        "entries_fetched": 0,
        "queue_total": 0,
    }

    for source in sources:
        if not source.get("feed_url"):
            stats["sources_skipped"] += 1
            continue

        now_ms = int(time.time() * 1000)

        if not should_fetch(source, now_ms):
            stats["sources_skipped"] += 1
            continue

        last_item_pub_time = source.get("last_item_pub_time") or 0
        cutoff_ms = last_item_pub_time or (source.get("last_fetch_time") or 0)
        consecutive_fail = source.get("consecutive_fail_count") or 0

        try:
            log(f"[RSS] fetching {source.get('name') or source.get('feed_url')}")
            feed = fetch_feed(source["feed_url"], config.HTTP_TIMEOUT, config.HTTP_RETRIES, headers={"User-Agent": "NewsDataRSS/1.0"})
        except Exception as exc:
            fail_count = consecutive_fail + 1
            status = derive_overall_status(fail_count, True)
            fetch_status = derive_fetch_status(exc)
            update_bitable_record_fields(
                config.FEISHU_RSS_APP_TOKEN,
                config.FEISHU_RSS_TABLE_ID,
                tenant_token,
                source["record_id"],
                {
                    config.RSS_FIELD_STATUS: status,
                    config.RSS_FIELD_LAST_FETCH_STATUS: fetch_status,
                    config.RSS_FIELD_CONSECUTIVE_FAIL_COUNT: fail_count,
                    config.RSS_FIELD_LAST_FETCH_TIME: now_ms,
                },
                config.HTTP_TIMEOUT,
                config.HTTP_RETRIES,
            )
            log(f"[RSS] fetch failed {source['feed_url']}: {exc}")
            stats["sources_skipped"] += 1
            continue

        entries = feed.entries or []
        log(f"[RSS] fetched entries={len(entries)} for {source.get('name') or source.get('feed_url')}")
        stats["entries_fetched"] += len(entries)
        if config.MAX_ENTRIES_PER_FEED and len(entries) > config.MAX_ENTRIES_PER_FEED:
            entries = entries[: config.MAX_ENTRIES_PER_FEED]

        failed_items = parse_failed_items(source.get("failed_items"))
        entry_map: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            entry_key = build_item_key(entry, source.get("item_id_strategy"), source.get("content_hash_algo"))
            if entry_key:
                entry_map[entry_key] = entry

        latest_pub_ms = 0
        latest_key = ""
        processed_keys: set = set()
        state = {
            "source": source,
            "now_ms": now_ms,
            "latest_pub_ms": latest_pub_ms,
            "latest_key": latest_key,
            "updated_failed_items": [],
            "new_count": 0,
            "pending_count": 0,
            "persisted": False,
        }
        updated_failed_items = state["updated_failed_items"]

        if failed_items:
            retry_budget = config.FAILED_ITEMS_RETRY_LIMIT
            for item in failed_items:
                item_key = item.get("item_key") or ""
                if not item_key:
                    continue
                entry = entry_map.get(item_key)
                if entry is None:
                    item["miss_count"] = int(item.get("miss_count") or 0) + 1
                    item["last_seen_ms"] = now_ms
                    updated_failed_items.append(item)
                    continue
                if item_key in existing_keys:
                    processed_keys.add(item_key)
                    continue
                if retry_budget <= 0:
                    updated_failed_items.append(item)
                    continue
                retry_budget -= 1

                entry_ts = entry_published_ts(entry)
                entry_ts_ms = entry_ts * 1000 if entry_ts else 0
                article = {
                    "title": entry.get("title") or "",
                    "content": entry_text_content(entry),
                    "link": entry.get("link") or "",
                    "published": entry_ts,
                    "source": source.get("name") or source.get("feed_url"),
                }

                queued = enqueue_unique_item(
                    queue,
                    queued_keys,
                    state,
                    {
                        "source_id": source["record_id"],
                        "item_key": item_key,
                        "article": article,
                        "entry_ts": entry_ts,
                        "entry_ts_ms": entry_ts_ms,
                        "from_failed": True,
                    },
                )
                if not queued:
                    processed_keys.add(item_key)
                    continue
                processed_keys.add(item_key)

                if entry_ts_ms > latest_pub_ms:
                    latest_pub_ms = entry_ts_ms
                    latest_key = item_key

        for entry in entries:
            entry_ts = entry_published_ts(entry)
            entry_ts_ms = entry_ts * 1000 if entry_ts else 0
            if entry_ts_ms and cutoff_ms and entry_ts_ms <= cutoff_ms:
                continue

            item_key = build_item_key(entry, source.get("item_id_strategy"), source.get("content_hash_algo"))
            if not item_key:
                continue
            if item_key in processed_keys:
                continue
            if item_key in existing_keys:
                continue

            article = {
                "title": entry.get("title") or "",
                "content": entry_text_content(entry),
                "link": entry.get("link") or "",
                "published": entry_ts,
                "source": source.get("name") or source.get("feed_url"),
            }

            queued = enqueue_unique_item(
                queue,
                queued_keys,
                state,
                {
                    "source_id": source["record_id"],
                    "item_key": item_key,
                    "article": article,
                    "entry_ts": entry_ts,
                    "entry_ts_ms": entry_ts_ms,
                    "from_failed": False,
                },
            )
            processed_keys.add(item_key)
            if not queued:
                continue

            if entry_ts_ms > latest_pub_ms:
                latest_pub_ms = entry_ts_ms
                latest_key = item_key

        state["latest_pub_ms"] = latest_pub_ms
        state["latest_key"] = latest_key
        source_states[source["record_id"]] = state
        stats["sources_processed"] += 1

    stats["queue_total"] = len(queue)
    return queue, source_states, stats


def run_llm_queue(
    queue: List[Dict[str, Any]],
    source_states: Dict[str, Dict[str, Any]],
    tenant_token: str,
    existing_keys: set,
    system_prompt: str,
    stats: Dict[str, int],
) -> None:
    total = len(queue)
    if total <= 0:
        log("[LLM] queue empty")
        return

    lock = threading.Lock()
    in_flight_keys: set = set()

    def handle_item(item: Dict[str, Any]) -> None:
        state = source_states[item["source_id"]]
        article = item["article"]
        item_key = item["item_key"]
        has_in_flight_key = False
        state_to_persist: Optional[Dict[str, Any]] = None

        try:
            with lock:
                if item_key in existing_keys or item_key in in_flight_keys:
                    return
                in_flight_keys.add(item_key)
                has_in_flight_key = True

            analysis = analyze_with_nvidia(article, system_prompt)
            categories = analysis.get("categories") or []
            if isinstance(categories, list) and any(c in FAILED_CATEGORIES for c in categories):
                with lock:
                    stats["llm_failed"] += 1
                    upsert_failed_item(
                        state["updated_failed_items"],
                        item_key,
                        item["entry_ts_ms"],
                        article.get("title") or "",
                        article.get("link") or "",
                        "llm_failed",
                        state["now_ms"],
                    )
                return

            with lock:
                stats["llm_success"] += 1

            fields = build_news_fields(article, analysis, item_key)
            ok, _ = create_bitable_record_with_id(
                config.FEISHU_NEWS_APP_TOKEN,
                config.FEISHU_NEWS_TABLE_ID,
                tenant_token,
                fields,
                config.HTTP_TIMEOUT,
                config.HTTP_RETRIES,
            )
            if not ok:
                with lock:
                    stats["feishu_create_failed"] += 1
                return

            with lock:
                existing_keys.add(item_key)
                stats["entries_processed"] += 1
                stats["entries_new"] += 1
                state["new_count"] += 1
        finally:
            with lock:
                if has_in_flight_key:
                    in_flight_keys.discard(item_key)
                state["pending_count"] -= 1
                if state["pending_count"] == 0 and not state["persisted"]:
                    state["persisted"] = True
                    state_to_persist = state
            if state_to_persist is not None and not persist_source_state(state_to_persist, tenant_token):
                with lock:
                    state_to_persist["persisted"] = False

    done = 0
    with ThreadPoolExecutor(max_workers=config.LLM_CONCURRENCY) as executor:
        futures = [executor.submit(handle_item, item) for item in queue]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                with lock:
                    stats["llm_failed"] += 1
                log(f"[LLM] task failed: {exc}")
            done += 1
            bar = render_progress(done, total, width=config.PROGRESS_BAR_WIDTH)
            msg = f"[LLM] {bar} ok={stats['llm_success']} fail={stats['llm_failed']}"
            if sys.stdout.isatty():
                sys.stdout.write("\r" + msg)
                sys.stdout.flush()
            else:
                log(msg)
        if sys.stdout.isatty():
            sys.stdout.write("\n")
            sys.stdout.flush()


def validate_runtime_config() -> List[str]:
    errors: List[str] = []

    def require(value: str, label: str, hint: str) -> None:
        if not value:
            errors.append(f"{label} 未配置。{hint}")

    require(config.FEISHU_APP_ID, "FEISHU_APP_ID", "请填写飞书应用 App ID。")
    require(config.FEISHU_APP_SECRET, "FEISHU_APP_SECRET", "请填写飞书应用 App Secret。")
    require(
        config.FEISHU_NEWS_APP_TOKEN,
        "FEISHU_NEWS_APP_TOKEN / FEISHU_NEWS_TABLE_LINK",
        "建议直接填写 FEISHU_NEWS_APP_TOKEN；也可以通过 FEISHU_NEWS_TABLE_LINK 自动解析。",
    )
    require(
        config.FEISHU_NEWS_TABLE_ID,
        "FEISHU_NEWS_TABLE_ID / FEISHU_NEWS_TABLE_LINK",
        "建议直接填写 FEISHU_NEWS_TABLE_ID；也可以通过 FEISHU_NEWS_TABLE_LINK 自动解析。",
    )
    require(
        config.FEISHU_RSS_APP_TOKEN,
        "FEISHU_RSS_APP_TOKEN / FEISHU_RSS_TABLE_LINK",
        "建议直接填写 FEISHU_RSS_APP_TOKEN；也可以通过 FEISHU_RSS_TABLE_LINK 自动解析。",
    )
    require(
        config.FEISHU_RSS_TABLE_ID,
        "FEISHU_RSS_TABLE_ID / FEISHU_RSS_TABLE_LINK",
        "建议直接填写 FEISHU_RSS_TABLE_ID；也可以通过 FEISHU_RSS_TABLE_LINK 自动解析。",
    )
    require(
        config.FEISHU_PROMPT_DOC_TOKEN,
        "FEISHU_PROMPT_DOC_TOKEN / FEISHU_PROMPT_DOC_LINK",
        "建议直接填写 FEISHU_PROMPT_DOC_TOKEN；也可以通过 FEISHU_PROMPT_DOC_LINK 自动解析。",
    )
    require(
        config.NVIDIA_API_KEY,
        "NVIDIA_API_KEY",
        "当前版本默认使用 NVIDIA API 做新闻分析，未提供其他模型降级路径。",
    )
    return errors


def log_runtime_config_errors(errors: List[str]) -> None:
    log("[Config] startup validation failed. The function will stop before fetching RSS.")
    for index, error in enumerate(errors, start=1):
        log(f"[Config] {index}. {error}")


def main() -> Dict[str, Any]:
    try:
        config_errors = validate_runtime_config()
        if config_errors:
            log_runtime_config_errors(config_errors)
            raise RuntimeError("required configuration is missing or invalid")

        log(
            "[Config] startup validation passed. "
            f"fetch_interval_minutes={config.DEFAULT_FETCH_INTERVAL_MIN} "
            f"llm_concurrency={config.LLM_CONCURRENCY}"
        )
        tenant_token = get_tenant_access_token(config.FEISHU_APP_ID, config.FEISHU_APP_SECRET, config.HTTP_TIMEOUT, config.HTTP_RETRIES)
        system_prompt = get_document_raw_content(
            config.FEISHU_PROMPT_DOC_TOKEN,
            tenant_token,
            config.HTTP_TIMEOUT,
            config.HTTP_RETRIES,
        )
        log(f"[Prompt] fetched {len(system_prompt)} chars")
        if not system_prompt.strip():
            raise RuntimeError("prompt document is empty")
        records = list_bitable_records(
            config.FEISHU_RSS_APP_TOKEN,
            config.FEISHU_RSS_TABLE_ID,
            tenant_token,
            config.HTTP_TIMEOUT,
            config.HTTP_RETRIES,
        )

        sources = [normalize_source(r) for r in records if r.get("record_id")]
        enabled_sources = [s for s in sources if s.get("enabled")]
        log(f"[RSS] sources total={len(sources)} enabled={len(enabled_sources)}")
        try:
            existing_keys = prefetch_recent_item_keys(tenant_token)
            log(f"[Dedup] prefetched keys: {len(existing_keys)}")
        except Exception as exc:
            log(f"[Dedup] prefetch failed: {exc}")
            existing_keys = set()

        queue, source_states, fetch_stats = split_sources_and_queue(enabled_sources, existing_keys, tenant_token)
        persist_ready_source_states(source_states, tenant_token)
        stats = {
            "llm_success": 0,
            "llm_failed": 0,
            "feishu_create_failed": 0,
            "entries_processed": 0,
            "entries_new": 0,
        }
        stats.update(fetch_stats)
        log(f"[Queue] total={stats['queue_total']} sources_processed={stats['sources_processed']} sources_skipped={stats['sources_skipped']}")

        run_llm_queue(queue, source_states, tenant_token, existing_keys, system_prompt, stats)
        persist_ready_source_states(source_states, tenant_token)

        log(
            "[Summary] "
            f"sources_done={stats['sources_processed']} "
            f"sources_skipped={stats['sources_skipped']} "
            f"entries_fetched={stats['entries_fetched']} "
            f"queue_total={stats['queue_total']} "
            f"processed={stats['entries_processed']} "
            f"new={stats['entries_new']} "
            f"llm_ok={stats['llm_success']} "
            f"llm_failed={stats['llm_failed']} "
            f"feishu_failed={stats['feishu_create_failed']}"
        )
        return {
            "ok": True,
            "message": "rss ingest completed",
            "stats": stats,
        }
    except Exception as exc:
        log(f"[Main] fatal error: {exc}")
        raise


def handler(event, context):
    return main()


if __name__ == "__main__":
    main()
