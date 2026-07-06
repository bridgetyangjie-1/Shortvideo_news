"""
行业宏观数据月度缓存

行业报告发布周期为月度，因此以自然月为粒度缓存行业宏观数据。
月初/缓存缺失时触发 Kimi 搜索，日常运行直接读取缓存，不重复调用 API。
方向 A：搜索失败或字段缺失时留空，不返回固定默认值。
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(
    os.getenv("COZE_WORKSPACE_PATH", os.getcwd()), "data", "industry_cache.json"
)
SEED_FILE = os.path.join(
    os.getenv("COZE_WORKSPACE_PATH", os.getcwd()), "config", "industry_seed.json"
)


def _ensure_cache_dir() -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)


def _is_meaningful_text(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    placeholders = {
        "未知", "暂无", "无", "N/A", "n/a", "null", "None", "-", "—",
        "未提供", "暂无公开月报数据", "not found", "unknown", "none",
    }
    return text not in placeholders


def _has_valid_industry_payload(industry: Dict[str, Any]) -> bool:
    if not isinstance(industry, dict):
        return False
    return _is_meaningful_text(industry.get("app_mau")) and _is_meaningful_text(
        industry.get("drama_count")
    )


def load_seed() -> Optional[Dict[str, Any]]:
    """加载仓库内行业宏观种子数据（Kimi 搜索失败时的最后回退）。"""
    if not os.path.exists(SEED_FILE):
        return None
    try:
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            seed = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("industry_cache: 种子文件解析失败: %s", exc)
        return None
    industry = seed.get("industry")
    if not _has_valid_industry_payload(industry or {}):
        return None
    logger.info("industry_cache: 命中种子数据 config/industry_seed.json")
    return seed


def load_cache(today: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    加载本月有效的行业宏观数据缓存。

    Returns:
        缓存字典（含 industry/platform 字段），如果缓存不存在或已过期则返回 None。
    """
    _ensure_cache_dir()
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("industry_cache: 缓存文件解析失败: %s", e)
        return None

    data_month = cache.get("data_month")
    industry = cache.get("industry")
    if not data_month or not isinstance(industry, dict):
        return None

    if not _has_valid_industry_payload(industry):
        logger.warning(
            "industry_cache: 缓存 %s 关键字段缺失，视为无效",
            data_month,
        )
        return None

    current_month = (today or datetime.now().strftime("%Y-%m-%d"))[:7]
    if data_month != current_month:
        logger.info(
            "industry_cache: 缓存月份 %s 与当前月份 %s 不一致，需重新搜索",
            data_month,
            current_month,
        )
        return None

    logger.info(
        "industry_cache: 命中本月缓存 %s，来源: %s",
        data_month,
        industry.get("data_source", "未知"),
    )
    return cache


def save_cache(
    industry: Dict[str, Any],
    platform: Dict[str, Any],
    today: Optional[str] = None,
) -> None:
    """保存月度行业宏观数据缓存。"""
    _ensure_cache_dir()
    current_date = today or datetime.now().strftime("%Y-%m-%d")
    cache = {
        "data_month": current_date[:7],
        "industry": industry,
        "platform": platform,
        "updated_at": datetime.now().isoformat(),
    }
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info(
            "industry_cache: 已保存 %s 行业宏观数据缓存，来源: %s",
            cache["data_month"],
            industry.get("data_source", "未知"),
        )
    except OSError as e:
        logger.warning("industry_cache: 缓存保存失败: %s", e)
