import os
import sys
from types import SimpleNamespace

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import rss_parser


def test_fetch_feed_allows_bozo_if_entries_exist(monkeypatch):
    monkeypatch.setattr(
        rss_parser.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, content=b"<xml/>", text=""),
    )
    fake_feed = SimpleNamespace(bozo=True, bozo_exception=RuntimeError("bad feed"), entries=[{"id": "1"}])
    monkeypatch.setattr(rss_parser.feedparser, "parse", lambda content: fake_feed)

    out = rss_parser.fetch_feed("https://example.com/rss", timeout=5, retries=1)

    assert out is fake_feed


def test_fetch_feed_raises_when_bozo_and_no_entries(monkeypatch):
    monkeypatch.setattr(
        rss_parser.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, content=b"<xml/>", text=""),
    )
    fake_feed = SimpleNamespace(bozo=True, bozo_exception=RuntimeError("bad feed"), entries=[])
    monkeypatch.setattr(rss_parser.feedparser, "parse", lambda content: fake_feed)

    with pytest.raises(RuntimeError):
        rss_parser.fetch_feed("https://example.com/rss", timeout=5, retries=1)
