"""
标签标准化与题材分类
"""
from typing import List, Dict

# 标签同义词映射
TAG_SYNONYMS = {
    "都市言情": "都市爱情",
    "爱情": "都市爱情",
    "虐渣打脸": "打脸虐渣",
    "穿书": "穿越",
    "女强": "女性成长",
    "大女主": "女性成长",
    "男频": "男性向",
    "女频": "女性向",
    "甜宠言情": "甜宠",
    "古装爱情": "古风爱情",
    "玄幻修仙": "玄幻仙侠",
    "系统种田": "系统",
    "赘婿": "赘婿逆袭",
    "战神": "战神归来",
    "神医": "无敌神医",
    "年代文": "年代",
    "宅斗": "宫斗宅斗",
    "先婚后爱": "先婚厚爱",
    "闪婚甜宠": "闪婚",
    "重生复仇": "重生",
    "马甲文": "马甲",
    "总裁": "霸总",
    "豪门": "豪门世家",
    "逆袭打脸": "打脸",
    "奇幻脑洞": "奇幻",
    "古风权谋": "权谋",
    "奇幻爱情": "奇幻",
}

# 题材分类
GENRE_CATEGORIES: Dict[str, List[str]] = {
    "female": ["都市爱情", "甜宠", "宫斗宅斗", "古风爱情", "重生", "穿越", "女性成长", "先婚厚爱", "马甲", "闪婚", "豪门世家", "霸总", "复仇", "逆袭"],
    "male": ["战神归来", "赘婿逆袭", "都市玄幻", "玄幻仙侠", "逆袭", "大男主", "无敌神医", "强者回归", "系统"],
    "neutral": ["悬疑", "喜剧", "家庭伦理", "亲情", "剧情", "种田经营", "年代"]
}


def canonicalize_tag(tag: str) -> str:
    """单标签标准化（同义词映射 + 去空白）。"""
    clean = str(tag or "").strip()
    if not clean:
        return ""
    return TAG_SYNONYMS.get(clean, clean)


def normalize_tags(tags: List[str]) -> List[str]:
    """标准化标签列表，合并同义词并去重。"""
    if not tags:
        return []
    normalized: List[str] = []
    for tag in tags:
        clean = canonicalize_tag(tag)
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized


def classify_category(tags: List[str]) -> str:
    """根据标签判断女频/男频/中性"""
    if not tags:
        return "neutral"
    normalized_tags = normalize_tags(tags)
    for tag in normalized_tags:
        if tag in GENRE_CATEGORIES["female"]:
            return "female"
        if tag in GENRE_CATEGORIES["male"]:
            return "male"
    return "neutral"


def get_genre_distribution(dramas: List[Dict]) -> Dict[str, int]:
    """统计题材分布"""
    distribution: Dict[str, int] = {}
    for drama in dramas:
        tags = drama.get("tags", [])
        normalized = normalize_tags(tags)
        for tag in normalized:
            distribution[tag] = distribution.get(tag, 0) + 1
    return dict(sorted(distribution.items(), key=lambda x: x[1], reverse=True))


def get_category_distribution(dramas: List[Dict]) -> Dict[str, int]:
    """统计女频/男频/中性分布"""
    distribution = {"female": 0, "male": 0, "neutral": 0}
    for drama in dramas:
        tags = drama.get("tags", [])
        category = classify_category(tags)
        distribution[category] += 1
    return distribution
