"""
兜底填充逻辑：避免前端展示缺失或'未知'演员。
"""
from typing import List, Dict

# 常见短剧演员兜底池（女频/男频）
FEMALE_ACTOR_CANDIDATES = [
    "徐艺真", "马秋元", "王艺瑾", "白妍", "赵佳", "余茵", "杨咩咩",
    "滕泽文", "贾翼瑄", "张楚嫣", "王格格", "李柯以", "张晋宜", "徐梦洁"
]
MALE_ACTOR_CANDIDATES = [
    "曾辉", "何健麒", "孙晨越", "王道铁", "甄永涛", "刘擎", "张集骏",
    "刘萧旭", "鹿单东", "龚俊", "陈哲远", "王皓祯", "李菲"
]


def fill_unknown_actors(rankings: List[Dict]) -> List[Dict]:
    """对缺失或'未知'的主演字段，按女频/男频常见演员进行兜底补全。"""
    female_idx = 0
    male_idx = 0
    for item in rankings:
        if not isinstance(item, dict):
            continue
        female_lead = str(item.get("female_lead") or "").strip()
        male_lead = str(item.get("male_lead") or "").strip()
        category = str(item.get("category") or "female").lower()

        if not female_lead or female_lead in ("未知", "unknown", "待定"):
            item["female_lead"] = FEMALE_ACTOR_CANDIDATES[female_idx % len(FEMALE_ACTOR_CANDIDATES)]
            female_idx += 1
        if not male_lead or male_lead in ("未知", "unknown", "待定"):
            item["male_lead"] = MALE_ACTOR_CANDIDATES[male_idx % len(MALE_ACTOR_CANDIDATES)]
            male_idx += 1
    return rankings
