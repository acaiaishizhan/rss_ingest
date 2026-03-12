import feishu_client


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = "raw-text"

    def json(self):
        return self._payload


def test_create_bitable_record_with_id_success(monkeypatch):
    monkeypatch.setattr(
        feishu_client,
        "http_post",
        lambda *_args, **_kwargs: _FakeResponse({"code": 0, "data": {"record": {"record_id": "rec_123"}}}),
    )

    ok, record_id = feishu_client.create_bitable_record_with_id(
        app_token="app",
        table_id="tbl",
        tenant_token="tenant",
        fields={"k": "v"},
        timeout=3,
        retries=1,
    )

    assert ok is True
    assert record_id == "rec_123"


def test_create_bitable_record_with_id_failure_returns_none(monkeypatch):
    monkeypatch.setattr(
        feishu_client,
        "http_post",
        lambda *_args, **_kwargs: _FakeResponse({"code": 1003, "msg": "invalid"}),
    )

    ok, record_id = feishu_client.create_bitable_record_with_id(
        app_token="app",
        table_id="tbl",
        tenant_token="tenant",
        fields={"k": "v"},
        timeout=3,
        retries=1,
    )

    assert ok is False
    assert record_id is None


def test_create_bitable_record_with_id_missing_record_id(monkeypatch):
    monkeypatch.setattr(
        feishu_client,
        "http_post",
        lambda *_args, **_kwargs: _FakeResponse({"code": 0, "data": {"record": {}}}),
    )

    ok, record_id = feishu_client.create_bitable_record_with_id(
        app_token="app",
        table_id="tbl",
        tenant_token="tenant",
        fields={"k": "v"},
        timeout=3,
        retries=1,
    )

    assert ok is True
    assert record_id is None
