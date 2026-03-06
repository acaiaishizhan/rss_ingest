import math
import os
import re


DEFAULT_AUTO_FETCH_SCHEDULE = "0 0 * * * *"


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


load_local_env()


def read_optional_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def read_required_str(name: str) -> str:
    return read_optional_str(name, "")


def read_int(name: str, default: int, minimum: int | None = None) -> int:
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


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def _extract_bitable_app_token(url: str) -> str:
    m = re.search(r"/base/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""


def _extract_bitable_table_id(url: str) -> str:
    m = re.search(r"[?&]table=([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""


def _extract_docx_token(url: str) -> str:
    m = re.search(r"/docx/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else ""


def _split_schedule_fields(schedule: str) -> list[str]:
    parts = schedule.strip().split()
    if parts and parts[0].startswith("CRON_TZ="):
        parts = parts[1:]
    return parts


def _extract_step(value: str) -> int:
    m = re.fullmatch(r"(?:\*|\d+)/(\d+)", value)
    if not m:
        return 0
    step = int(m.group(1))
    return step if step > 0 else 0


def _extract_sorted_numbers(value: str, minimum: int, maximum: int) -> list[int]:
    if not value or any(ch in value for ch in ("*", "/", "-", "?", "L", "W", "#")):
        return []
    items = []
    for part in value.split(","):
        if not part.isdigit():
            return []
        number = int(part)
        if number < minimum or number > maximum:
            return []
        items.append(number)
    return sorted(set(items))


def _derive_step_from_numbers(numbers: list[int], cycle: int) -> int:
    if not numbers:
        return 0
    if len(numbers) == 1:
        return cycle
    diffs = []
    for left, right in zip(numbers, numbers[1:]):
        if right > left:
            diffs.append(right - left)
    wrap_diff = cycle - numbers[-1] + numbers[0]
    if wrap_diff > 0:
        diffs.append(wrap_diff)
    step = 0
    for diff in diffs:
        step = diff if step == 0 else math.gcd(step, diff)
    return step


def _derive_interval_from_schedule(schedule: str, fallback: int = 60) -> int:
    fields = _split_schedule_fields(schedule)
    if len(fields) >= 6:
        minute_field = fields[1]
        hour_field = fields[2]
    elif len(fields) == 5:
        minute_field = fields[0]
        hour_field = fields[1]
    else:
        return fallback

    if minute_field == "*":
        return 1

    minute_step = _extract_step(minute_field)
    if minute_step:
        return minute_step

    minute_numbers = _extract_sorted_numbers(minute_field, 0, 59)
    if minute_numbers and hour_field == "*":
        if len(minute_numbers) == 1:
            return 60
        minute_list_step = _derive_step_from_numbers(minute_numbers, 60)
        return minute_list_step or fallback

    if minute_field.isdigit() and hour_field == "*":
        return 60

    hour_step = _extract_step(hour_field)
    if hour_step and (minute_field.isdigit() or minute_field == "0"):
        return hour_step * 60

    hour_numbers = _extract_sorted_numbers(hour_field, 0, 23)
    if hour_numbers and (minute_field.isdigit() or minute_field == "0"):
        hour_list_step = _derive_step_from_numbers(hour_numbers, 24)
        return (hour_list_step * 60) if hour_list_step else fallback

    if minute_field.isdigit() and hour_field.isdigit():
        return 24 * 60

    return fallback


FEISHU_APP_ID = read_required_str("FEISHU_APP_ID")
FEISHU_APP_SECRET = read_required_str("FEISHU_APP_SECRET")
FEISHU_NEWS_TABLE_LINK = read_optional_str("FEISHU_NEWS_TABLE_LINK")
FEISHU_RSS_TABLE_LINK = read_optional_str("FEISHU_RSS_TABLE_LINK")
FEISHU_PROMPT_DOC_LINK = read_optional_str("FEISHU_PROMPT_DOC_LINK")
NVIDIA_API_KEY = read_optional_str("NVIDIA_API_KEY")

LEGACY_FEISHU_APP_TOKEN = read_optional_str("FEISHU_APP_TOKEN")

# New deployments should provide links; token/id fields remain as hidden compatibility fallbacks.
FEISHU_NEWS_APP_TOKEN = _first_non_empty(
    _extract_bitable_app_token(FEISHU_NEWS_TABLE_LINK),
    read_optional_str("FEISHU_NEWS_APP_TOKEN"),
    LEGACY_FEISHU_APP_TOKEN,
)
FEISHU_NEWS_TABLE_ID = _first_non_empty(
    _extract_bitable_table_id(FEISHU_NEWS_TABLE_LINK),
    read_optional_str("FEISHU_NEWS_TABLE_ID"),
)
FEISHU_RSS_APP_TOKEN = _first_non_empty(
    _extract_bitable_app_token(FEISHU_RSS_TABLE_LINK),
    read_optional_str("FEISHU_RSS_APP_TOKEN"),
    LEGACY_FEISHU_APP_TOKEN,
)
FEISHU_RSS_TABLE_ID = _first_non_empty(
    _extract_bitable_table_id(FEISHU_RSS_TABLE_LINK),
    read_optional_str("FEISHU_RSS_TABLE_ID"),
)
FEISHU_PROMPT_DOC_TOKEN = _first_non_empty(
    _extract_docx_token(FEISHU_PROMPT_DOC_LINK),
    read_optional_str("FEISHU_PROMPT_DOC_TOKEN"),
)

# Backward-compatible alias for legacy callers and old deployments.
FEISHU_APP_TOKEN = FEISHU_NEWS_APP_TOKEN

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
AUTO_FETCH_SCHEDULE = read_optional_str("AUTO_FETCH_SCHEDULE", DEFAULT_AUTO_FETCH_SCHEDULE)
FETCH_INTERVAL_MINUTES = read_int(
    "FETCH_INTERVAL_MINUTES",
    _derive_interval_from_schedule(AUTO_FETCH_SCHEDULE, fallback=60),
    minimum=1,
)
HTTP_TIMEOUT = read_int("HTTP_TIMEOUT", 20, minimum=1)
HTTP_RETRIES = read_int("HTTP_RETRIES", 3, minimum=1)
NVIDIA_RETRIES = read_int("NVIDIA_RETRIES", 10, minimum=1)
FAILED_ITEMS_MAX = read_int("FAILED_ITEMS_MAX", 50, minimum=1)
FAILED_ITEMS_RETRY_LIMIT = read_int("FAILED_ITEMS_RETRY_LIMIT", 5, minimum=1)
FAILED_ITEMS_MAX_AGE_DAYS = read_int("FAILED_ITEMS_MAX_AGE_DAYS", 7, minimum=1)
FAILED_ITEMS_MAX_MISS = read_int("FAILED_ITEMS_MAX_MISS", 3, minimum=1)
LLM_CONCURRENCY = read_int("LLM_CONCURRENCY", 10, minimum=1)
PROGRESS_BAR_WIDTH = read_int("PROGRESS_BAR_WIDTH", 20, minimum=1)
DEFAULT_FETCH_INTERVAL_MIN = FETCH_INTERVAL_MINUTES
