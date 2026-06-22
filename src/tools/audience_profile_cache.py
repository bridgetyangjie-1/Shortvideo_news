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

DEFAULT_PROFILE: Dict[str, Any] = {
    "gender": {"female": 70, "male": 30},
    "age": {"18-24": 20, "25-34": 42, "35-44": 28, "45+": 10},
    "regions": [
        {"name": "广东", "value": 15.5},
        {"name": "江苏", "value": 11.8},
        {"name": "浙江", "value": 9.6},
        {"name": "山东", "value": 8.4},
        {"name": "河南", "value": 7.2},
    ],
    "traits": [
        "偏好强反转高密度剧情",
        "关注女性逆袭与情绪补偿",
        "习惯通勤睡前碎片化追更",
        "对复仇打脸和身份揭晓爽点敏感",
    ],
    "content_preferences": [
        {"name": "都市爱情", "value": 32},
        {"name": "穿越重生", "value": 24},
        {"name": "复仇逆袭", "value": 18},
        {"name": "古装宫斗", "value": 14},
        {"name": "甜宠萌宝", "value": 12},
    ],
    "viewing_time": [
        {"name": "睡前 22-24点", "value": 35},
        {"name": "晚间 20-22点", "value": 28},
        {"name": "通勤/午休", "value": 22},
        {"name": "周末白天", "value": 15},
    ],
    "spending_power": {"paid_ratio": 35, "arpu": "¥18", "willingness": "中高"},
    "user_segments": [
        {"name": "核心追更党", "share": 28, "desc": "日更必追、愿意为爆款付费解锁"},
        {"name": "碎片路人", "share": 45, "desc": "通勤/睡前刷剧，免费内容为主"},
        {"name": "高消费用户", "share": 18, "desc": "对优质内容付费意愿强，关注主演"},
        {"name": "尝鲜猎奇党", "share": 9, "desc": "热衷新题材和黑马剧，易流失"},
    ],
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
    """返回默认画像，作为最终兜底。"""
    return json.loads(json.dumps(DEFAULT_PROFILE, ensure_ascii=False))
