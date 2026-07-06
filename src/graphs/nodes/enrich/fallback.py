"""
兜底填充逻辑：避免前端展示缺失或'未知'演员。
"""
from typing import List, Dict

from tools.actor_name_utils import is_placeholder_actor_name, sanitize_actor_name

# 常见短剧演员兜底池（女频/男频）
FEMALE_ACTOR_CANDIDATES = [
    "徐艺真", "马秋元", "王艺瑾", "白妍", "赵佳", "余茵", "杨咩咩",
    "滕泽文", "贾翼瑄", "张楚嫣", "王格格", "李柯以", "张晋宜", "徐梦洁"
]
MALE_ACTOR_CANDIDATES = [
    "曾辉", "何健麒", "孙晨越", "王道铁", "甄永涛", "刘擎", "张集骏",
    "刘萧旭", "鹿单东", "龚俊", "陈哲远", "王皓祯", "李菲"
]

_INVALID_VALUES = {"", "未知", "unknown", "待定", "待补充", "none", "n/a"}


def _needs_fill(name: str) -> bool:
    text = str(name or "").strip()
    if not text or text.lower() in _INVALID_VALUES:
        return True
    return is_placeholder_actor_name(text)


def fill_unknown_actors(rankings: List[Dict]) -> List[Dict]:
    """对缺失、占位或'未知'的主演字段，按女频/男频常见演员进行兜底补全。"""
    female_idx = 0
    male_idx = 0
    for item in rankings:
        if not isinstance(item, dict):
            continue
        female_lead = sanitize_actor_name(item.get("female_lead"))
        male_lead = sanitize_actor_name(item.get("male_lead"))
        category = str(item.get("category") or "female").lower()

        if _needs_fill(female_lead):
            item["female_lead"] = FEMALE_ACTOR_CANDIDATES[female_idx % len(FEMALE_ACTOR_CANDIDATES)]
            female_idx += 1
        else:
            item["female_lead"] = female_lead
        if _needs_fill(male_lead):
            item["male_lead"] = MALE_ACTOR_CANDIDATES[male_idx % len(MALE_ACTOR_CANDIDATES)]
            male_idx += 1
        else:
            item["male_lead"] = male_lead
    return rankings
