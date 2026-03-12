import pytest

import feishu_client


class _FakeResponse:
    def __init__(self, payload=None, json_error: bool = False):
        self._payload = payload if payload is not None else {}
        self._json_error = json_error
        self.status_code = 200
        self.text = "raw-text"

    def json(self):
        if self._json_error:
            raise ValueError("bad json")
        return self._payload


def test_send_feishu_webhook_returns_true_on_code_zero(monkeypatch):
    monkeypatch.setattr(
        feishu_client,
        "http_post",
        lambda *_args, **_kwargs: _FakeResponse({"code": 0}),
    )

    assert feishu_client.send_feishu_webhook("https://example.com/webhook", "hello", timeout=3, retries=1) is True


def test_send_feishu_webhook_returns_false_on_non_zero_code(monkeypatch):
    monkeypatch.setattr(
        feishu_client,
        "http_post",
        lambda *_args, **_kwargs: _FakeResponse({"code": 19001}),
    )

    assert feishu_client.send_feishu_webhook("https://example.com/webhook", "hello", timeout=3, retries=1) is False


def test_send_feishu_webhook_raises_on_non_json_response(monkeypatch):
    monkeypatch.setattr(
        feishu_client,
        "http_post",
        lambda *_args, **_kwargs: _FakeResponse(json_error=True),
    )

    with pytest.raises(RuntimeError):
        feishu_client.send_feishu_webhook("https://example.com/webhook", "hello", timeout=3, retries=1)
