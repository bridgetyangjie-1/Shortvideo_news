"""
AI 短剧/漫剧看板月度缓存

DataEye AI 短剧/漫剧月报为月度发布，因此以自然月为粒度缓存。
月初/缓存缺失时触发 Kimi 搜索，日常运行直接读取缓存，不重复调用 API。
搜索失败或字段缺失时留空，不返回固定默认值。
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(
    os.getenv("COZE_WORKSPACE_PATH", os.getcwd()), "data", "ai_drama_cache.json"
)


def _ensure_cache_dir() -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)


def load_cache(today: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """加载本月有效的 AI 短剧/漫剧看板缓存。"""
    _ensure_cache_dir()
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("ai_drama_cache: 缓存文件解析失败: %s", e)
        return None

    data_month = cache.get("data_month")
    dashboard = cache.get("dashboard")
    if not data_month or not isinstance(dashboard, dict):
        return None

    current_month = (today or datetime.now().strftime("%Y-%m-%d"))[:7]
    if data_month != current_month:
        logger.info(
            "ai_drama_cache: 缓存月份 %s 与当前月份 %s 不一致，需重新搜索",
            data_month,
            current_month,
        )
        return None

    # 如果缓存的核心字段全部为空，视为无效缓存，触发重新搜索
    rankings = dashboard.get("rankings") or {}
    has_kpis = bool(dashboard.get("kpis"))
    has_rankings = bool(
        (rankings.get("ai_drama") or []) or (rankings.get("ai_comic") or [])
    )
    has_trends = bool(dashboard.get("trends"))
    has_news = bool(dashboard.get("news"))
    if not any([has_kpis, has_rankings, has_trends, has_news]):
        logger.warning(
            "ai_drama_cache: 命中本月缓存 %s，但核心字段均为空，将重新搜索",
            data_month,
        )
        return None

    logger.info(
        "ai_drama_cache: 命中本月缓存 %s，来源: %s",
        data_month,
        dashboard.get("data_source", "未知"),
    )
    return cache


def save_cache(dashboard: Dict[str, Any], today: Optional[str] = None) -> None:
    """保存月度 AI 短剧/漫剧看板缓存。"""
    _ensure_cache_dir()
    current_date = today or datetime.now().strftime("%Y-%m-%d")
    cache = {
        "data_month": current_date[:7],
        "dashboard": dashboard,
        "updated_at": datetime.now().isoformat(),
    }
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info(
            "ai_drama_cache: 已保存 %s AI 短剧/漫剧缓存，来源: %s",
            cache["data_month"],
            dashboard.get("data_source", "未知"),
        )
    except OSError as e:
        logger.warning("ai_drama_cache: 缓存保存失败: %s", e)
