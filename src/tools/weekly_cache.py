"""
周更数据缓存工具

用于缓存更新频率为 weekly 的数据（如行业洞察、演员榜等）。
以自然周为粒度：每周一刷新，周二至周日读取上周一产生的缓存，避免重复调用 API。
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(
    os.getenv("COZE_WORKSPACE_PATH", os.getcwd()), "data", "weekly_cache"
)


def _ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_file(key: str, week_key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}_{week_key}.json")


def _week_key(data_date: Optional[str] = None) -> str:
    """返回 data_date 所在周的周一日期（YYYY-MM-DD），作为周缓存键。"""
    try:
        dt = datetime.strptime(data_date or datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d")
    except (ValueError, TypeError):
        dt = datetime.now()
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def is_refresh_day(data_date: Optional[str] = None) -> bool:
    """判断是否为周更刷新日（周一）。"""
    try:
        dt = datetime.strptime(data_date or datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d")
    except (ValueError, TypeError):
        dt = datetime.now()
    return dt.weekday() == 0


def load_cache(key: str, data_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    加载本周有效的周更数据缓存。

    Args:
        key: 缓存标识，如 "insights" / "actors"。
        data_date: 数据日期，默认今天。

    Returns:
        缓存字典（含 payload 字段），不存在或过期则返回 None。
    """
    _ensure_cache_dir()
    file_path = _cache_file(key, _week_key(data_date))
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("weekly_cache: 缓存文件解析失败 %s: %s", file_path, e)
        return None

    payload = cache.get("payload")
    if not isinstance(payload, dict):
        return None

    logger.info("weekly_cache: 命中 %s 缓存（周 %s）", key, cache.get("week_key", "-"))
    return payload


def save_cache(
    key: str,
    payload: Dict[str, Any],
    data_date: Optional[str] = None,
) -> None:
    """保存周更数据缓存。"""
    _ensure_cache_dir()
    wk = _week_key(data_date)
    file_path = _cache_file(key, wk)
    cache = {
        "week_key": wk,
        "data_date": data_date or datetime.now().strftime("%Y-%m-%d"),
        "payload": payload,
        "updated_at": datetime.now().isoformat(),
    }
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info("weekly_cache: 已保存 %s 缓存（周 %s）", key, wk)
    except OSError as e:
        logger.warning("weekly_cache: 缓存保存失败 %s: %s", file_path, e)
