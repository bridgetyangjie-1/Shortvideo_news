"""
观众画像月度基准缓存

观众画像基于真实行业报告，报告发布周期为月度，因此不需要每天搜索。
缓存以自然月为粒度，月初/缓存缺失时触发 Kimi 搜索，每周根据榜单题材做微调。
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(
    os.getenv("COZE_WORKSPACE_PATH", os.getcwd()), "data", "audience_profile_cache.json"
)

# 兜底画像：仅在月度报告搜索完全失败且榜单标签也无法解析时使用。
# 方向 A：优先留空，不返回整套固定画像；此兜底仅用于保证流程不崩溃。
FALLBACK_PROFILE: Dict[str, Any] = {
    "gender": {"female": 0, "male": 0},
    "age": {"18-24": 0, "25-34": 0, "35-44": 0, "45+": 0},
    "regions": [],
    "traits": [],
    "content_preferences": [],
    "viewing_time": [],
    "spending_power": {},
    "user_segments": [],
}


def _ensure_cache_dir() -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)


def load_cache(today: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    加载本月有效的观众画像缓存。

    Returns:
        缓存字典（含 profile 字段），如果缓存不存在或已过期则返回 None。
    """
    _ensure_cache_dir()
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("audience_profile_cache: 缓存文件解析失败: %s", e)
        return None

    data_month = cache.get("data_month")
    profile = cache.get("profile")
    if not data_month or not isinstance(profile, dict):
        return None

    current_month = (today or datetime.now().strftime("%Y-%m-%d"))[:7]
    if data_month != current_month:
        logger.info(
            "audience_profile_cache: 缓存月份 %s 与当前月份 %s 不一致，需重新搜索",
            data_month,
            current_month,
        )
        return None

    logger.info(
        "audience_profile_cache: 命中本月缓存 %s，来源: %s",
        data_month,
        cache.get("source_title", "未知"),
    )
    return cache


def save_cache(
    profile: Dict[str, Any],
    source_url: str = "",
    source_title: str = "",
    report_date: str = "",
    today: Optional[str] = None,
) -> None:
    """保存月度观众画像缓存。"""
    _ensure_cache_dir()
    current_date = today or datetime.now().strftime("%Y-%m-%d")
    cache = {
        "data_month": current_date[:7],
        "report_date": report_date or current_date,
        "source_url": source_url,
        "source_title": source_title,
        "profile": profile,
        "updated_at": datetime.now().isoformat(),
    }
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info(
            "audience_profile_cache: 已保存 %s 观众画像缓存，来源: %s",
            cache["data_month"],
            source_title or "未知",
        )
    except OSError as e:
        logger.warning("audience_profile_cache: 缓存保存失败: %s", e)


def get_default_profile() -> Dict[str, Any]:
    """返回兜底画像（空结构），作为最终兜底。"""
    return json.loads(json.dumps(FALLBACK_PROFILE, ensure_ascii=False))
