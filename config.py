import os
import re

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_NEWS_TABLE_LINK = os.getenv("FEISHU_NEWS_TABLE_LINK", "")
FEISHU_RSS_TABLE_LINK = os.getenv("FEISHU_RSS_TABLE_LINK", "")
FEISHU_PROMPT_DOC_LINK = os.getenv("FEISHU_PROMPT_DOC_LINK", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "60"))

def _extract_bitable_app_token(url: str) -> str:
    m = re.search(r"/base/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""

def _extract_bitable_table_id(url: str) -> str:
    m = re.search(r"[?&]table=([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""

def _extract_docx_token(url: str) -> str:
    m = re.search(r"/docx/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""

FEISHU_APP_TOKEN = _extract_bitable_app_token(FEISHU_NEWS_TABLE_LINK)
FEISHU_NEWS_TABLE_ID = _extract_bitable_table_id(FEISHU_NEWS_TABLE_LINK)
FEISHU_RSS_TABLE_ID = _extract_bitable_table_id(FEISHU_RSS_TABLE_LINK)
FEISHU_PROMPT_DOC_TOKEN = _extract_docx_token(FEISHU_PROMPT_DOC_LINK)

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
HTTP_TIMEOUT = 20
HTTP_RETRIES = 3
NVIDIA_RETRIES = int(os.getenv("NVIDIA_RETRIES", "10"))
FAILED_ITEMS_MAX = int(os.getenv("FAILED_ITEMS_MAX", "50"))
FAILED_ITEMS_RETRY_LIMIT = int(os.getenv("FAILED_ITEMS_RETRY_LIMIT", "5"))
FAILED_ITEMS_MAX_AGE_DAYS = int(os.getenv("FAILED_ITEMS_MAX_AGE_DAYS", "7"))
FAILED_ITEMS_MAX_MISS = int(os.getenv("FAILED_ITEMS_MAX_MISS", "3"))
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "4"))
PROGRESS_BAR_WIDTH = int(os.getenv("PROGRESS_BAR_WIDTH", "20"))
DEFAULT_FETCH_INTERVAL_MIN = FETCH_INTERVAL_MINUTES

