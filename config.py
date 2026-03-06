import os
import re
from typing import Any

import yaml


CONFIG_FILENAME = "先填这个.yml"
DEFAULT_AUTO_FETCH_SCHEDULE = "0 0 * * * *"

PRIMARY_CONFIG_FIELDS = {
    "FEISHU_APP_ID": "feishuAppId",
    "FEISHU_APP_SECRET": "feishuAppSecret",
    "FEISHU_NEWS_TABLE_LINK": "newsTableLink",
    "FEISHU_RSS_TABLE_LINK": "rssTableLink",
    "FEISHU_PROMPT_DOC_LINK": "promptDocLink",
    "NVIDIA_API_KEY": "modelApiKey",
}

CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), CONFIG_FILENAME)
CONFIG_LOAD_ERRORS: list[str] = []
CONFIG_VALUE_SOURCES: dict[str, str] = {}


def load_local_env(filename: str = ".env") -> None:
    path = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue

            name, value = line.split("=", 1)
            name = name.strip()
            value = value.strip()
            if not name or name in os.environ:
                continue

            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]

            os.environ[name] = value


def _normalize_scalar_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    return ""


def load_yaml_config(filename: str = CONFIG_FILENAME) -> dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(path):
        CONFIG_LOAD_ERRORS.append(f"仓库根目录缺少 {filename}，请恢复模板文件并填写业务配置。")
        return {}

    try:
        with open(path, "r", encoding="utf-8-sig") as yaml_file:
            loaded = yaml.safe_load(yaml_file) or {}
    except yaml.YAMLError as exc:
        CONFIG_LOAD_ERRORS.append(f"{filename} 解析失败，请检查 YAML 缩进和引号：{exc}")
        return {}
    except OSError as exc:
        CONFIG_LOAD_ERRORS.append(f"{filename} 读取失败：{exc}")
        return {}

    if not isinstance(loaded, dict):
        CONFIG_LOAD_ERRORS.append(f"{filename} 顶层必须是 key-value 结构。")
        return {}

    return loaded


def _record_value_source(name: str, source: str) -> None:
    CONFIG_VALUE_SOURCES[name] = source


def read_preferred_str(name: str, yaml_key: str | None = None, default: str = "") -> str:
    if yaml_key:
        yaml_value = _normalize_scalar_str(_YAML_CONFIG.get(yaml_key))
        if yaml_value:
            _record_value_source(name, "yaml")
            return yaml_value

    env_value = os.getenv(name)
    if env_value is not None:
        env_value = env_value.strip()
        if env_value:
            _record_value_source(name, "env")
            return env_value

    _record_value_source(name, "default")
    return default


def read_env_int(name: str, default: int, minimum: int | None = None) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def describe_primary_config_source() -> str:
    sources = {
        CONFIG_VALUE_SOURCES.get(env_name)
        for env_name in PRIMARY_CONFIG_FIELDS
        if CONFIG_VALUE_SOURCES.get(env_name) in {"yaml", "env"}
    }
    if sources == {"yaml"}:
        return "YAML"
    if sources == {"env"}:
        return "环境变量"
    if sources == {"yaml", "env"}:
        return "YAML + 环境变量"
    return "未读取到业务配置"


def _extract_bitable_app_token(url: str) -> str:
    m = re.search(r"/base/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""


def _extract_bitable_table_id(url: str) -> str:
    m = re.search(r"[?&]table=([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""


def _extract_docx_token(url: str) -> str:
    m = re.search(r"/docx/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""


load_local_env()
_YAML_CONFIG = load_yaml_config()

FEISHU_APP_ID = read_preferred_str("FEISHU_APP_ID", "feishuAppId")
FEISHU_APP_SECRET = read_preferred_str("FEISHU_APP_SECRET", "feishuAppSecret")
FEISHU_NEWS_TABLE_LINK = read_preferred_str("FEISHU_NEWS_TABLE_LINK", "newsTableLink")
FEISHU_RSS_TABLE_LINK = read_preferred_str("FEISHU_RSS_TABLE_LINK", "rssTableLink")
FEISHU_PROMPT_DOC_LINK = read_preferred_str("FEISHU_PROMPT_DOC_LINK", "promptDocLink")
NVIDIA_API_KEY = read_preferred_str("NVIDIA_API_KEY", "modelApiKey")

FEISHU_NEWS_APP_TOKEN = _extract_bitable_app_token(FEISHU_NEWS_TABLE_LINK)
FEISHU_NEWS_TABLE_ID = _extract_bitable_table_id(FEISHU_NEWS_TABLE_LINK)
FEISHU_RSS_APP_TOKEN = _extract_bitable_app_token(FEISHU_RSS_TABLE_LINK)
FEISHU_RSS_TABLE_ID = _extract_bitable_table_id(FEISHU_RSS_TABLE_LINK)
FEISHU_PROMPT_DOC_TOKEN = _extract_docx_token(FEISHU_PROMPT_DOC_LINK)

# Compatibility field only. Actual run frequency is controlled by the FC timer trigger.
AUTO_FETCH_SCHEDULE_COMPAT = read_preferred_str(
    "AUTO_FETCH_SCHEDULE",
    "autoFetchSchedule",
    DEFAULT_AUTO_FETCH_SCHEDULE,
)

CONFIG_FILE_PRESENT = os.path.exists(CONFIG_FILE_PATH)
PRIMARY_CONFIG_SOURCE_SUMMARY = describe_primary_config_source()

NEWS_FIELD_TITLE = "标题"
NEWS_FIELD_SCORE = "AI打分"
NEWS_FIELD_CATEGORIES = "分类"
NEWS_FIELD_SUMMARY = "总结"
NEWS_FIELD_PUBLISHED_MS = "发布时间"
NEWS_FIELD_SOURCE = "来源"
NEWS_FIELD_FULL_CONTENT = "全文"
NEWS_FIELD_ITEM_KEY = "item_key"
NEWS_FIELD_CREATED_TIME = "创建时间"
NEWS_FIELD_READ = "已读"
RSS_FIELD_NAME = "name"
RSS_FIELD_FEED_URL = "feed_url"
RSS_FIELD_TYPE = "type"
RSS_FIELD_DESCRIPTION = "description"
RSS_FIELD_ENABLED = "enabled"
RSS_FIELD_STATUS = "status"
RSS_FIELD_LAST_FETCH_TIME = "last_fetch_time"
RSS_FIELD_LAST_FETCH_STATUS = "last_fetch_status"
RSS_FIELD_CONSECUTIVE_FAIL_COUNT = "consecutive_fail_count"
RSS_FIELD_LAST_ITEM_GUID = "last_item_guid"
RSS_FIELD_LAST_ITEM_PUB_TIME = "last_item_pub_time"
RSS_FIELD_ITEM_ID_STRATEGY = "item_id_strategy"
RSS_FIELD_CONTENT_LANGUAGE = "content_language"
RSS_FIELD_FAILED_ITEMS = "failed_items"
DEFAULT_ITEM_ID_STRATEGY = "guid"
DEFAULT_CONTENT_HASH_ALGO = "md5"
MAX_ENTRIES_PER_FEED = 200
NEWS_ITEM_KEY_PREFETCH_LIMIT = 500
STATUS_IDLE = "idle"
STATUS_OK = "ok"
STATUS_UNSTABLE = "unstable"
STATUS_DEAD = "dead"
STATUS_OPTIONS = {STATUS_IDLE, STATUS_OK, STATUS_UNSTABLE, STATUS_DEAD}
FETCH_STATUS_SUCCESS = "success"
FETCH_STATUS_TIMEOUT = "timeout"
FETCH_STATUS_HTTP_ERROR = "http_error"
FETCH_STATUS_PARSE_ERROR = "parse_error"
FETCH_STATUS_OPTIONS = {FETCH_STATUS_SUCCESS, FETCH_STATUS_TIMEOUT, FETCH_STATUS_HTTP_ERROR, FETCH_STATUS_PARSE_ERROR}
ITEM_ID_STRATEGY_OPTIONS = {"guid", "link", "title_pubdate", "content_hash"}
CONTENT_LANGUAGE_OPTIONS = {"zh", "en", "jp", "mixed", "other"}
HTTP_TIMEOUT = read_env_int("HTTP_TIMEOUT", 20, minimum=1)
HTTP_RETRIES = read_env_int("HTTP_RETRIES", 3, minimum=1)
NVIDIA_RETRIES = read_env_int("NVIDIA_RETRIES", 10, minimum=1)
FAILED_ITEMS_MAX = read_env_int("FAILED_ITEMS_MAX", 50, minimum=1)
FAILED_ITEMS_RETRY_LIMIT = read_env_int("FAILED_ITEMS_RETRY_LIMIT", 5, minimum=1)
FAILED_ITEMS_MAX_AGE_DAYS = read_env_int("FAILED_ITEMS_MAX_AGE_DAYS", 7, minimum=1)
FAILED_ITEMS_MAX_MISS = read_env_int("FAILED_ITEMS_MAX_MISS", 3, minimum=1)
LLM_CONCURRENCY = read_env_int("LLM_CONCURRENCY", 10, minimum=1)
PROGRESS_BAR_WIDTH = read_env_int("PROGRESS_BAR_WIDTH", 20, minimum=1)
