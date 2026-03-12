# -*- coding: utf-8 -*-
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


def _safe_json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"[Feishu] non-JSON response ({resp.status_code}): {resp.text[:200]}")


def _sleep_backoff(attempt: int) -> None:
    time.sleep(min(8.0, 0.8 * (2 ** attempt) + random.random() * 0.3))


def _http_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    timeout: int,
    retries: int,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    trust_env: bool = False,
) -> requests.Response:
    attempts = max(1, int(retries or 0))
    last_err: Optional[requests.RequestException] = None
    for i in range(attempts):
        try:
            with requests.Session() as sess:
                sess.trust_env = trust_env
                return sess.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=timeout,
                )
        except requests.RequestException as exc:
            last_err = exc
            _sleep_backoff(i)
    raise RuntimeError(f"HTTP {method.upper()} failed after retries: {last_err}")


def http_get(url: str, headers: Dict[str, str], timeout: int, retries: int, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    return _http_request("GET", url, headers, timeout, retries, params=params)


def http_post(url: str, headers: Dict[str, str], json_body: Dict[str, Any], timeout: int, retries: int) -> requests.Response:
    return _http_request("POST", url, headers, timeout, retries, json_body=json_body)


def http_put(url: str, headers: Dict[str, str], json_body: Dict[str, Any], timeout: int, retries: int) -> requests.Response:
    return _http_request("PUT", url, headers, timeout, retries, json_body=json_body)


def get_tenant_access_token(app_id: str, app_secret: str, timeout: int, retries: int) -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}
    headers = {"Content-Type": "application/json; charset=utf-8"}
    resp = http_post(url, headers, payload, timeout, retries)
    data = _safe_json(resp)
    if data.get("code") != 0:
        raise RuntimeError(f"[Feishu] token error: {data}")
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"[Feishu] token missing: {data}")
    return token


def list_bitable_records(
    app_token: str,
    table_id: str,
    tenant_token: str,
    timeout: int,
    retries: int,
    page_size: int = 500,
    max_pages: int = 50,
    filter_obj: Optional[Dict[str, Any]] = None,
    sort: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
    headers = {
        "Authorization": f"Bearer {tenant_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    items: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    for _ in range(max_pages):
        body: Dict[str, Any] = {"page_size": page_size}
        if page_token:
            body["page_token"] = page_token
        if filter_obj:
            body["filter"] = filter_obj
        if sort:
            body["sort"] = sort

        resp = http_post(url, headers, body, timeout, retries)
        data = _safe_json(resp)
        if data.get("code") != 0:
            raise RuntimeError(f"[Feishu] list records error: {data}")

        data_block = data.get("data") or {}
        items.extend(data_block.get("items") or [])
        if not data_block.get("has_more"):
            break
        page_token = data_block.get("page_token")
        if not page_token:
            break

    return items


def update_bitable_record_fields(
    app_token: str,
    table_id: str,
    tenant_token: str,
    record_id: str,
    fields: Dict[str, Any],
    timeout: int,
    retries: int,
) -> bool:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
    headers = {
        "Authorization": f"Bearer {tenant_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {"fields": fields}
    resp = http_put(url, headers, body, timeout, retries)
    data = _safe_json(resp)
    if data.get("code") != 0:
        return False
    return True


def create_bitable_record(
    app_token: str,
    table_id: str,
    tenant_token: str,
    fields: Dict[str, Any],
    timeout: int,
    retries: int,
) -> bool:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {
        "Authorization": f"Bearer {tenant_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {"fields": fields}
    resp = http_post(url, headers, body, timeout, retries)
    data = _safe_json(resp)
    if data.get("code") != 0:
        print(f"[Feishu] create record error: {data}", flush=True)
        return False
    return True


def create_bitable_record_with_id(
    app_token: str,
    table_id: str,
    tenant_token: str,
    fields: Dict[str, Any],
    timeout: int,
    retries: int,
) -> Tuple[bool, Optional[str]]:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {
        "Authorization": f"Bearer {tenant_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {"fields": fields}
    resp = http_post(url, headers, body, timeout, retries)
    data = _safe_json(resp)
    if data.get("code") != 0:
        print(f"[Feishu] create record error: {data}", flush=True)
        return False, None
    record = (data.get("data") or {}).get("record") or {}
    return True, record.get("record_id")


def send_feishu_webhook(webhook_url: str, text: str, timeout: int, retries: int) -> bool:
    headers = {"Content-Type": "application/json"}
    body = {"msg_type": "text", "content": {"text": text}}
    resp = http_post(webhook_url, headers, body, timeout, retries)
    data = _safe_json(resp)
    return data.get("code", 0) == 0


def get_document_raw_content(doc_token: str, tenant_token: str, timeout: int, retries: int) -> str:
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/raw_content"
    headers = {"Authorization": f"Bearer {tenant_token}"}
    resp = http_get(url, headers, timeout, retries)
    data = _safe_json(resp)
    if data.get("code") != 0:
        raise RuntimeError(f"[Feishu] get doc error: {data}")
    content = (data.get("data") or {}).get("content")
    if content is None:
        raise RuntimeError(f"[Feishu] doc content missing: {data}")
    return content

