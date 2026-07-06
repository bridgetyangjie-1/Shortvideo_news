"""
演员姓名校验：识别 LLM 占位名、测试名与无效值。
"""
from __future__ import annotations

import re
from typing import Any

# 常见占位/示例姓名（含大小写变体在比较时统一处理）
PLACEHOLDER_ACTOR_NAMES = frozenset({
    "张三", "李四", "王五", "赵六", "钱七", "孙八", "周九", "吴十",
    "小明", "小红", "小刚", "小丽", "测试", "示例", "某某", "某人",
    "女主", "男主", "女主角", "男主角", "演员甲", "演员乙",
    "未知", "待补充", "待定", "unknown", "none", "n/a", "null",
})

# 单姓 + 常见占位名（如「张XX」类模板）
_PLACEHOLDER_GIVEN = frozenset({"三", "四", "五", "六", "七", "八", "九", "十", "某", "X", "x"})


def _normalize(name: Any) -> str:
    if name is None:
        return ""
    return str(name).strip()


def is_placeholder_actor_name(name: Any) -> bool:
    """判断是否为占位/无效演员名。"""
    text = _normalize(name)
    if not text:
        return True
    lower = text.lower()
    if lower in {n.lower() for n in PLACEHOLDER_ACTOR_NAMES}:
        return True
    # 「张X」「李X」等模板
    if len(text) == 2 and text[0] in "张李王赵钱孙周吴郑陈刘":
        if text[1] in _PLACEHOLDER_GIVEN:
            return True
    # 纯数字或带括号说明
    if re.fullmatch(r"[\d\s]+", text):
        return True
    if re.search(r"(待填|示例|测试|placeholder)", lower):
        return True
    return False


def sanitize_actor_name(name: Any) -> str:
    """占位名返回空字符串，否则返回去空白后的原名。"""
    text = _normalize(name)
    if is_placeholder_actor_name(text):
        return ""
    return text


def sanitize_ranking_actors(item: dict) -> dict:
    """就地清洗榜单条目中的男女主字段。"""
    if not isinstance(item, dict):
        return item
    for field in ("female_lead", "male_lead"):
        if field in item:
            item[field] = sanitize_actor_name(item.get(field))
    return item
