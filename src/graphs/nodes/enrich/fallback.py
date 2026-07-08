"""
兜底填充逻辑：清洗占位演员名，不再用候选池编造演员。
"""
from typing import List, Dict

from tools.actor_name_utils import sanitize_actor_name
from utils.data_quality import sanitize_production_house


def fill_unknown_actors(rankings: List[Dict]) -> List[Dict]:
    """
    清洗榜单中的占位/幻觉演员与可疑厂牌。

    无可靠信源时保留空字符串，禁止用候选演员池凑数。
    """
    for item in rankings:
        if not isinstance(item, dict):
            continue
        item["female_lead"] = sanitize_actor_name(item.get("female_lead"))
        item["male_lead"] = sanitize_actor_name(item.get("male_lead"))
        item["production_house"] = sanitize_production_house(item.get("production_house"))
    return rankings
