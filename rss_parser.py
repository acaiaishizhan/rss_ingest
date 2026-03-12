# -*- coding: utf-8 -*-
import calendar
import hashlib
import time
from typing import Any, Dict, Optional

import feedparser
import requests


def get_without_env(url: str, timeout: int, headers: Optional[Dict[str, str]] = None) -> requests.Response:
    with requests.Session() as sess:
        sess.trust_env = False
        return sess.get(url, headers=headers, timeout=timeout)


def normalize_entry(entry: Any) -> Dict[str, Any]:
    if isinstance(entry, dict):
        return entry
    if hasattr(entry, "items"):
        try:
            return dict(entry.items())
        except Exception:
            return {}
    return {}


def fetch_feed(url: str, timeout: int, retries: int, headers: Optional[Dict[str, str]] = None) -> feedparser.FeedParserDict:
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = get_without_env(url, timeout=timeout, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            feed = feedparser.parse(resp.content)
            if feed.bozo and not (feed.entries or []):
                raise RuntimeError(f"Feed parse error: {feed.bozo_exception}")
            return feed
        except Exception as exc:
            last_err = exc
            time.sleep(min(8.0, 0.8 * (2 ** attempt)))
    raise RuntimeError(f"fetch_feed failed: {last_err}")


def entry_published_ts(entry: Dict[str, Any]) -> int:
    entry = normalize_entry(entry)
    tm = entry.get("published_parsed") or entry.get("updated_parsed")
    if tm:
        try:
            return int(calendar.timegm(tm))
        except Exception:
            return 0
    return 0


def entry_text_content(entry: Dict[str, Any]) -> str:
    entry = normalize_entry(entry)
    content = entry.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        first_entry = normalize_entry(first)
        if first_entry.get("value"):
            return str(first_entry.get("value"))
    summary = entry.get("summary") or entry.get("description")
    if summary:
        return str(summary)
    return ""


def build_item_key(entry: Dict[str, Any], strategy: str, content_hash_algo: str) -> str:
    entry = normalize_entry(entry)
    strategy = (strategy or "").strip().lower()
    if strategy == "guid":
        return str(entry.get("id") or entry.get("guid") or "").strip()
    if strategy == "link":
        return str(entry.get("link") or "").strip()
    if strategy == "title_pubdate":
        title = str(entry.get("title") or "").strip()
        published = str(entry.get("published") or entry.get("updated") or "").strip()
        return f"{title}|{published}".strip("|")
    if strategy == "content_hash":
        algo = (content_hash_algo or "md5").lower()
        raw = entry_text_content(entry)
        if not raw:
            return ""
        try:
            h = hashlib.new(algo)
        except Exception:
            h = hashlib.new("md5")
        h.update(raw.encode("utf-8", errors="ignore"))
        return f"{h.name}:{h.hexdigest()}"

    key = str(entry.get("id") or entry.get("guid") or entry.get("link") or "").strip()
    if key:
        return key
    title = str(entry.get("title") or "").strip()
    published = str(entry.get("published") or entry.get("updated") or "").strip()
    return f"{title}|{published}".strip("|")
