import os
import re


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


def read_env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


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


def extract_bitable_app_token(url: str) -> str:
    match = re.search(r"/base/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else ""


def extract_bitable_table_id(url: str) -> str:
    match = re.search(r"[?&]table=([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else ""


def extract_docx_token(url: str) -> str:
    match = re.search(r"/docx/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else ""


load_local_env()

FEISHU_APP_ID = read_env_str("FEISHU_APP_ID")
FEISHU_APP_SECRET = read_env_str("FEISHU_APP_SECRET")
FEISHU_NEWS_TABLE_LINK = read_env_str("FEISHU_NEWS_TABLE_LINK")
FEISHU_RSS_TABLE_LINK = read_env_str("FEISHU_RSS_TABLE_LINK")
FEISHU_PROMPT_DOC_LINK = read_env_str("FEISHU_PROMPT_DOC_LINK")
NVIDIA_API_KEY = read_env_str("NVIDIA_API_KEY")

FEISHU_NEWS_APP_TOKEN = extract_bitable_app_token(FEISHU_NEWS_TABLE_LINK)
FEISHU_NEWS_TABLE_ID = extract_bitable_table_id(FEISHU_NEWS_TABLE_LINK)
FEISHU_RSS_APP_TOKEN = extract_bitable_app_token(FEISHU_RSS_TABLE_LINK)
FEISHU_RSS_TABLE_ID = extract_bitable_table_id(FEISHU_RSS_TABLE_LINK)
FEISHU_PROMPT_DOC_TOKEN = extract_docx_token(FEISHU_PROMPT_DOC_LINK)

PRIMARY_CONFIG_SOURCE_SUMMARY = "env"

NEWS_FIELD_TITLE = "\u6807\u9898"
NEWS_FIELD_SCORE = "AI\u6253\u5206"
NEWS_FIELD_CATEGORIES = "\u5206\u7c7b"
NEWS_FIELD_SUMMARY = "\u603b\u7ed3"
NEWS_FIELD_PUBLISHED_MS = "\u53d1\u5e03\u65f6\u95f4"
NEWS_FIELD_SOURCE = "\u6765\u6e90"
NEWS_FIELD_FULL_CONTENT = "\u5168\u6587"
NEWS_FIELD_ITEM_KEY = "item_key"
NEWS_FIELD_CREATED_TIME = "\u521b\u5efa\u65f6\u95f4"
NEWS_FIELD_READ = "\u5df2\u8bfb"
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
