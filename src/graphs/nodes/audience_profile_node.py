"""
受众画像节点 - 基于榜单标签推理受众特征
无需调用外部API，纯本地规则计算
"""
import logging
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import AudienceProfile, AudienceProfileInput, AudienceProfileOutput

logger = logging.getLogger(__name__)


# ==================== 标签 → 受众画像映射规则 ====================

TAG_AUDIENCE_RULES = {
    # 女频标签 → 女性占比高
    "都市爱情": {"gender": {"female": 75, "male": 25}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "甜宠": {"gender": {"female": 80, "male": 20}, "age": {"18-24": 25, "25-34": 40, "35-44": 25, "45+": 10}},
    "高糖甜宠": {"gender": {"female": 82, "male": 18}, "age": {"18-24": 28, "25-34": 40, "35-44": 22, "45+": 10}},
    "宫斗宅斗": {"gender": {"female": 70, "male": 30}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "古风爱情": {"gender": {"female": 75, "male": 25}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "古装爱情": {"gender": {"female": 75, "male": 25}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "重生": {"gender": {"female": 65, "male": 35}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "穿越": {"gender": {"female": 60, "male": 40}, "age": {"18-24": 25, "25-34": 35, "35-44": 25, "45+": 15}},
    "穿越重生": {"gender": {"female": 63, "male": 37}, "age": {"18-24": 22, "25-34": 35, "35-44": 28, "45+": 15}},
    "女性成长": {"gender": {"female": 85, "male": 15}, "age": {"18-24": 20, "25-34": 40, "35-44": 30, "45+": 10}},
    "先婚后爱": {"gender": {"female": 78, "male": 22}, "age": {"18-24": 20, "25-34": 38, "35-44": 30, "45+": 12}},
    "闪婚": {"gender": {"female": 72, "male": 28}, "age": {"18-24": 22, "25-34": 36, "35-44": 28, "45+": 14}},
    "霸总": {"gender": {"female": 82, "male": 18}, "age": {"18-24": 25, "25-34": 42, "35-44": 25, "45+": 8}},
    "总裁": {"gender": {"female": 80, "male": 20}, "age": {"18-24": 24, "25-34": 42, "35-44": 26, "45+": 8}},
    "真假千金": {"gender": {"female": 78, "male": 22}, "age": {"18-24": 20, "25-34": 35, "35-44": 32, "45+": 13}},
    "打脸虐渣": {"gender": {"female": 75, "male": 25}, "age": {"18-24": 18, "25-34": 35, "35-44": 32, "45+": 15}},
    "复仇": {"gender": {"female": 68, "male": 32}, "age": {"18-24": 18, "25-34": 35, "35-44": 32, "45+": 15}},
    "复仇逆袭": {"gender": {"female": 68, "male": 32}, "age": {"18-24": 18, "25-34": 35, "35-44": 32, "45+": 15}},
    "萌宝": {"gender": {"female": 78, "male": 22}, "age": {"18-24": 15, "25-34": 38, "35-44": 35, "45+": 12}},
    "带球跑": {"gender": {"female": 80, "male": 20}, "age": {"18-24": 20, "25-34": 40, "35-44": 28, "45+": 12}},
    "破镜重圆": {"gender": {"female": 76, "male": 24}, "age": {"18-24": 18, "25-34": 38, "35-44": 30, "45+": 14}},
    "年下恋": {"gender": {"female": 82, "male": 18}, "age": {"18-24": 28, "25-34": 42, "35-44": 22, "45+": 8}},

    # 男频标签 → 男性占比高
    "战神归来": {"gender": {"female": 20, "male": 80}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "战神": {"gender": {"female": 22, "male": 78}, "age": {"18-24": 16, "25-34": 32, "35-44": 34, "45+": 18}},
    "赘婿逆袭": {"gender": {"female": 25, "male": 75}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "赘婿": {"gender": {"female": 25, "male": 75}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "都市玄幻": {"gender": {"female": 30, "male": 70}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "玄幻仙侠": {"gender": {"female": 35, "male": 65}, "age": {"18-24": 25, "25-34": 35, "35-44": 25, "45+": 15}},
    "仙侠": {"gender": {"female": 35, "male": 65}, "age": {"18-24": 25, "25-34": 35, "35-44": 25, "45+": 15}},
    "大男主": {"gender": {"female": 22, "male": 78}, "age": {"18-24": 18, "25-34": 32, "35-44": 35, "45+": 15}},
    "无敌神医": {"gender": {"female": 28, "male": 72}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "强者回归": {"gender": {"female": 25, "male": 75}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "逆袭": {"gender": {"female": 40, "male": 60}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "权谋": {"gender": {"female": 35, "male": 65}, "age": {"18-24": 18, "25-34": 32, "35-44": 32, "45+": 18}},
    "都市异能": {"gender": {"female": 32, "male": 68}, "age": {"18-24": 22, "25-34": 36, "35-44": 28, "45+": 14}},

    # 中性标签
    "悬疑": {"gender": {"female": 45, "male": 55}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "喜剧": {"gender": {"female": 50, "male": 50}, "age": {"18-24": 25, "25-34": 35, "35-44": 25, "45+": 15}},
    "家庭伦理": {"gender": {"female": 55, "male": 45}, "age": {"18-24": 10, "25-34": 25, "35-44": 40, "45+": 25}},
    "亲情": {"gender": {"female": 60, "male": 40}, "age": {"18-24": 10, "25-34": 25, "35-44": 35, "45+": 30}},
    "剧情": {"gender": {"female": 50, "male": 50}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "现实": {"gender": {"female": 52, "male": 48}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
}

# 地域偏好映射（基于题材）
REGION_RULES = {
    "都市爱情": [{"name": "广东", "value": 12}, {"name": "浙江", "value": 10}, {"name": "江苏", "value": 9}],
    "甜宠": [{"name": "广东", "value": 13}, {"name": "山东", "value": 10}, {"name": "河南", "value": 9}],
    "霸总": [{"name": "广东", "value": 14}, {"name": "浙江", "value": 11}, {"name": "江苏", "value": 9}],
    "战神归来": [{"name": "山东", "value": 14}, {"name": "河北", "value": 11}, {"name": "河南", "value": 10}],
    "战神": [{"name": "山东", "value": 14}, {"name": "河北", "value": 11}, {"name": "河南", "value": 10}],
    "赘婿逆袭": [{"name": "山东", "value": 13}, {"name": "四川", "value": 10}, {"name": "河北", "value": 9}],
    "赘婿": [{"name": "山东", "value": 13}, {"name": "四川", "value": 10}, {"name": "河北", "value": 9}],
    "家庭伦理": [{"name": "河南", "value": 12}, {"name": "山东", "value": 11}, {"name": "四川", "value": 10}],
    "穿越重生": [{"name": "广东", "value": 12}, {"name": "江苏", "value": 10}, {"name": "四川", "value": 9}],
    "古风爱情": [{"name": "广东", "value": 11}, {"name": "江苏", "value": 10}, {"name": "浙江", "value": 9}],
    "default": [
        {"name": "广东", "value": 11},
        {"name": "山东", "value": 10},
        {"name": "河南", "value": 9},
        {"name": "四川", "value": 8},
        {"name": "河北", "value": 7},
    ],
}

# 受众特征标签
TRAITS_RULES = {
    "female": [
        "偏好强反转高密度剧情",
        "关注女性成长与逆袭补偿",
        "习惯碎片化连续追更",
        "对身份反差爽点敏感",
    ],
    "male": [
        "偏好权力升级与战斗爽感",
        "关注事业逆袭与财富积累",
        "习惯快速节奏不拖沓",
        "对打脸复仇情节敏感",
    ],
    "neutral": [
        "偏好悬疑推理与逻辑挑战",
        "关注社会现实与情感共鸣",
        "习惯高质量制作精良剧",
        "对剧情深度要求高",
    ],
}

# 内容偏好映射：标签 → 题材分类
CONTENT_PREFERENCE_MAP = {
    "都市爱情": "都市爱情",
    "甜宠": "甜宠萌宝",
    "高糖甜宠": "甜宠萌宝",
    "萌宝": "甜宠萌宝",
    "带球跑": "甜宠萌宝",
    "霸总": "霸总豪门",
    "总裁": "霸总豪门",
    "真假千金": "复仇逆袭",
    "打脸虐渣": "复仇逆袭",
    "复仇": "复仇逆袭",
    "复仇逆袭": "复仇逆袭",
    "重生": "穿越重生",
    "穿越": "穿越重生",
    "穿越重生": "穿越重生",
    "古风爱情": "古风爱情",
    "古装爱情": "古风爱情",
    "宫斗宅斗": "古装宫斗",
    "战神归来": "战神逆袭",
    "战神": "战神逆袭",
    "赘婿逆袭": "赘婿逆袭",
    "赘婿": "赘婿逆袭",
    "强者回归": "强者回归",
    "无敌神医": "无敌神医",
    "玄幻仙侠": "玄幻仙侠",
    "仙侠": "玄幻仙侠",
    "都市玄幻": "都市玄幻",
    "都市异能": "都市异能",
    "悬疑": "悬疑推理",
    "家庭伦理": "家庭伦理",
    "亲情": "家庭伦理",
    "喜剧": "轻松喜剧",
    "女性成长": "女性成长",
    "先婚后爱": "先婚后爱",
    "闪婚": "先婚后爱",
    "破镜重圆": "破镜重圆",
    "年下恋": "年下恋",
    "权谋": "权谋朝堂",
    "现实": "现实主义",
}

# 付费能力规则（按主导性别/题材）
SPENDING_RULES = {
    "female_premium": {"paid_ratio": 38, "arpu": "¥20", "willingness": "高"},
    "female_standard": {"paid_ratio": 34, "arpu": "¥18", "willingness": "中高"},
    "male_premium": {"paid_ratio": 32, "arpu": "¥16", "willingness": "中高"},
    "male_standard": {"paid_ratio": 28, "arpu": "¥15", "willingness": "中"},
    "neutral": {"paid_ratio": 32, "arpu": "¥17", "willingness": "中"},
}

# 用户分层规则
USER_SEGMENT_RULES = {
    "female": [
        {"name": "核心追更党", "share": 30, "desc": "日更必追、愿意为爆款付费解锁"},
        {"name": "碎片路人", "share": 42, "desc": "通勤/睡前刷剧，免费内容为主"},
        {"name": "高消费用户", "share": 20, "desc": "对优质内容付费意愿强，关注主演"},
        {"name": "尝鲜猎奇党", "share": 8, "desc": "热衷新题材和黑马剧，易流失"},
    ],
    "male": [
        {"name": "核心追更党", "share": 28, "desc": "日更必追、愿意为爆款付费解锁"},
        {"name": "碎片路人", "share": 46, "desc": "通勤/睡前刷剧，免费内容为主"},
        {"name": "高消费用户", "share": 18, "desc": "对优质内容付费意愿强，关注主演"},
        {"name": "尝鲜猎奇党", "share": 8, "desc": "热衷新题材和黑马剧，易流失"},
    ],
    "neutral": [
        {"name": "核心追更党", "share": 28, "desc": "日更必追、愿意为爆款付费解锁"},
        {"name": "碎片路人", "share": 45, "desc": "通勤/睡前刷剧，免费内容为主"},
        {"name": "高消费用户", "share": 18, "desc": "对优质内容付费意愿强，关注主演"},
        {"name": "尝鲜猎奇党", "share": 9, "desc": "热衷新题材和黑马剧，易流失"},
    ],
}

# 观看时段规则
VIEWING_TIME_RULES = {
    "female": [
        {"name": "睡前 22-24点", "value": 38},
        {"name": "晚间 20-22点", "value": 26},
        {"name": "通勤/午休", "value": 24},
        {"name": "周末白天", "value": 12},
    ],
    "male": [
        {"name": "晚间 20-22点", "value": 34},
        {"name": "睡前 22-24点", "value": 28},
        {"name": "通勤/午休", "value": 20},
        {"name": "周末白天", "value": 18},
    ],
    "neutral": [
        {"name": "睡前 22-24点", "value": 35},
        {"name": "晚间 20-22点", "value": 28},
        {"name": "通勤/午休", "value": 22},
        {"name": "周末白天", "value": 15},
    ],
}

# 默认兜底画像
DEFAULT_PROFILE = {
    "gender": {"female": 50, "male": 50},
    "age": {"18-24": 20, "25-34": 30, "35-44": 30, "45+": 20},
    "regions": REGION_RULES["default"],
    "traits": TRAITS_RULES["neutral"],
    "content_preferences": [
        {"name": "都市爱情", "value": 32},
        {"name": "穿越重生", "value": 24},
        {"name": "复仇逆袭", "value": 18},
        {"name": "古装宫斗", "value": 14},
        {"name": "甜宠萌宝", "value": 12},
    ],
    "viewing_time": VIEWING_TIME_RULES["neutral"],
    "spending_power": SPENDING_RULES["neutral"],
    "user_segments": USER_SEGMENT_RULES["neutral"],
}


# ==================== 辅助函数 ====================

def _drama_to_dict(drama: Any) -> Dict[str, Any]:
    """将 DramaRanking 对象或字典统一转换为字典"""
    if isinstance(drama, dict):
        return drama
    if hasattr(drama, "model_dump"):
        return drama.model_dump()
    return {}


def _collect_drama_tags(drama: Dict[str, Any]) -> List[str]:
    """收集一部剧的所有标签来源"""
    tags: List[str] = []
    for field in ("tags", "core_trope"):
        value = drama.get(field)
        if isinstance(value, list):
            tags.extend([str(t).strip() for t in value if t])
        elif isinstance(value, str) and value.strip():
            tags.extend([t.strip() for t in value.split(",") if t.strip()])

    genre = drama.get("genre")
    if isinstance(genre, str) and genre.strip():
        tags.append(genre.strip())

    category = drama.get("category")
    if category == "female":
        tags.append("女性向")
    elif category == "male":
        tags.append("男性向")

    return list(dict.fromkeys(tags))  # 去重并保持顺序


def _categorize_gender(female_pct: float, male_pct: float) -> str:
    """根据性别比例判断主导类别"""
    if female_pct >= 60:
        return "female"
    if male_pct >= 60:
        return "male"
    return "neutral"


def _merge_profiles(profiles: List[Dict[str, Any]], weights: List[float] = None) -> Dict[str, Any]:
    """合并多个标签的受众画像，加权平均"""
    if not profiles:
        return DEFAULT_PROFILE.copy()

    if weights is None or len(weights) != len(profiles):
        weights = [1.0] * len(profiles)

    total_weight = sum(weights)
    if total_weight <= 0:
        return DEFAULT_PROFILE.copy()

    gender_female = 0.0
    gender_male = 0.0
    age = {"18-24": 0.0, "25-34": 0.0, "35-44": 0.0, "45+": 0.0}
    regions: Dict[str, float] = {}
    traits: set = set()

    for p, w in zip(profiles, weights):
        # 性别加权
        g = p.get("gender", {})
        gender_female += g.get("female", 50) * w
        gender_male += g.get("male", 50) * w

        # 年龄加权
        a = p.get("age", {})
        for k in age:
            age[k] += a.get(k, 25) * w

        # 地域
        for r in p.get("regions", []):
            name = r.get("name")
            if name:
                regions[name] = regions.get(name, 0.0) + r.get("value", 0) * w

        # 特征
        for t in p.get("traits", []):
            traits.add(t)

    return {
        "gender": {
            "female": round(gender_female / total_weight),
            "male": round(gender_male / total_weight),
        },
        "age": {
            "18-24": round(age["18-24"] / total_weight),
            "25-34": round(age["25-34"] / total_weight),
            "35-44": round(age["35-44"] / total_weight),
            "45+": round(age["45+"] / total_weight),
        },
        "regions": sorted(
            [{"name": k, "value": round(v / total_weight, 1)} for k, v in regions.items()],
            key=lambda x: x["value"],
            reverse=True,
        )[:5],
        "traits": list(traits)[:4] if traits else TRAITS_RULES["neutral"],
    }


def _normalize_to_100(values: Dict[str, int], keys: List[str]) -> Dict[str, int]:
    """将数值归一化为总和约100"""
    raw = {k: max(0, values.get(k, 0)) for k in keys}
    total = sum(raw.values())
    if total == 0:
        return {k: round(100 / len(keys)) for k in keys}

    normalized = {k: round(v / total * 100) for k, v in raw.items()}
    # 修正四舍五入误差
    diff = 100 - sum(normalized.values())
    if diff != 0 and normalized:
        max_key = max(normalized, key=lambda k: normalized[k])
        normalized[max_key] += diff
    return normalized


def _build_content_preferences(dramas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """基于榜单标签频次统计内容偏好"""
    category_counts: Dict[str, float] = {}

    for drama in dramas:
        rank = drama.get("rank", 50)
        weight = max(1.0, 21 - rank)  # 排名越靠前权重越高
        tags = _collect_drama_tags(drama)

        for tag in tags:
            category = CONTENT_PREFERENCE_MAP.get(tag)
            if category:
                category_counts[category] = category_counts.get(category, 0.0) + weight

    if not category_counts:
        return DEFAULT_PROFILE["content_preferences"].copy()

    total = sum(category_counts.values())
    preferences = [
        {"name": name, "value": round(count / total * 100)}
        for name, count in category_counts.items()
    ]
    preferences.sort(key=lambda x: x["value"], reverse=True)

    # 归一化并限制数量
    top = preferences[:6]
    total_top = sum(p["value"] for p in top)
    if total_top > 0:
        for p in top:
            p["value"] = round(p["value"] / total_top * 100)
        # 修正误差
        diff = 100 - sum(p["value"] for p in top)
        if diff != 0:
            top[0]["value"] += diff

    return top


def _build_viewing_time(gender_category: str) -> List[Dict[str, Any]]:
    """根据性别主导类别返回观看时段分布"""
    return [item.copy() for item in VIEWING_TIME_RULES.get(gender_category, VIEWING_TIME_RULES["neutral"])]


def _build_spending_power(
    gender_category: str, dramas: List[Dict[str, Any]], female_pct: float
) -> Dict[str, Any]:
    """基于性别和题材标签推断付费能力"""
    tags = set()
    for drama in dramas:
        tags.update(_collect_drama_tags(drama))

    premium_female_tags = {"霸总", "总裁", "甜宠", "高糖甜宠", "先婚后爱", "闪婚", "年下恋"}
    premium_male_tags = {"战神", "战神归来", "强者回归", "都市玄幻", "玄幻仙侠", "权谋"}

    if gender_category == "female":
        if any(t in premium_female_tags for t in tags):
            return SPENDING_RULES["female_premium"].copy()
        return SPENDING_RULES["female_standard"].copy()

    if gender_category == "male":
        if any(t in premium_male_tags for t in tags):
            return SPENDING_RULES["male_premium"].copy()
        return SPENDING_RULES["male_standard"].copy()

    # 中性但女性比例略高
    if female_pct >= 55:
        return SPENDING_RULES["female_standard"].copy()
    return SPENDING_RULES["neutral"].copy()


def _build_user_segments(gender_category: str) -> List[Dict[str, Any]]:
    """根据性别主导类别返回用户分层"""
    return [seg.copy() for seg in USER_SEGMENT_RULES.get(gender_category, USER_SEGMENT_RULES["neutral"])]


def _build_traits(gender_category: str, dramas: List[Dict[str, Any]]) -> List[str]:
    """构建受众特征标签，优先使用榜单实际标签"""
    tags = []
    for drama in dramas:
        tags.extend(_collect_drama_tags(drama))

    # 根据榜单高频词生成更具体的特征
    specific_traits = []
    tag_set = set(tags)

    if any(t in tag_set for t in ("甜宠", "高糖甜宠", "先婚后爱", "闪婚")):
        specific_traits.append("对高甜撒糖与情感代偿高度敏感")
    if any(t in tag_set for t in ("复仇", "复仇逆袭", "打脸虐渣", "真假千金")):
        specific_traits.append("热衷逆袭打脸与身份反转爽点")
    if any(t in tag_set for t in ("霸总", "总裁", "豪门")):
        specific_traits.append("偏好强权力差与玛丽苏情绪价值")
    if any(t in tag_set for t in ("战神", "战神归来", "强者回归", "赘婿逆袭")):
        specific_traits.append("偏好权力升级与战斗打脸爽感")
    if any(t in tag_set for t in ("穿越", "重生", "穿越重生")):
        specific_traits.append("习惯重生穿越带来的信息差爽感")
    if any(t in tag_set for t in ("悬疑", "推理")):
        specific_traits.append("偏好烧脑推理与逻辑反转")

    # 补充基础特征
    base_traits = TRAITS_RULES.get(gender_category, TRAITS_RULES["neutral"])
    result = specific_traits[:2]
    for trait in base_traits:
        if len(result) >= 4:
            break
        if trait not in result:
            result.append(trait)

    # 兜底
    while len(result) < 4:
        result.append("习惯碎片化连续追更")

    return result[:4]


def _build_regions(dramas: List[Dict[str, Any]], merged_regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """结合榜单题材与默认规则生成地域分布"""
    if merged_regions:
        return merged_regions

    # 尝试从榜单标签找地域偏好
    tag_region_scores: Dict[str, float] = {}
    for drama in dramas:
        tags = _collect_drama_tags(drama)
        for tag in tags:
            if tag in REGION_RULES:
                for region in REGION_RULES[tag]:
                    tag_region_scores[region["name"]] = tag_region_scores.get(region["name"], 0.0) + region["value"]

    if tag_region_scores:
        total = sum(tag_region_scores.values())
        regions = sorted(
            [{"name": k, "value": round(v / total * 100, 1)} for k, v in tag_region_scores.items()],
            key=lambda x: x["value"],
            reverse=True,
        )[:5]
        return regions

    return [r.copy() for r in REGION_RULES["default"]]


# ==================== 节点主函数 ====================

def audience_profile_node(
    state: AudienceProfileInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> AudienceProfileOutput:
    """
    title: 👥 受众画像分析
    desc: 基于榜单标签，纯本地推理受众画像（性别、年龄、地域、特征、偏好、时段、付费、分层）
    integrations: 无外部API调用，纯本地规则
    """
    try:
        data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
        enriched_rankings = state.enriched_rankings or []

        if not enriched_rankings:
            logger.warning("audience_profile_node: 输入榜单为空，返回默认画像")
            return AudienceProfileOutput(
                audience_profile=AudienceProfile(),
            )

        dramas = [_drama_to_dict(d) for d in enriched_rankings]

        # 收集每个匹配标签的画像及权重
        profiles = []
        weights = []

        for drama in dramas:
            rank = drama.get("rank", 50)
            weight = max(1.0, 21 - rank)  # TOP1权重20，TOP20权重1
            tags = _collect_drama_tags(drama)

            for tag in tags:
                if tag in TAG_AUDIENCE_RULES:
                    rule = TAG_AUDIENCE_RULES[tag]
                    category = _categorize_gender(
                        rule.get("gender", {}).get("female", 50),
                        rule.get("gender", {}).get("male", 50),
                    )
                    profile = {
                        "gender": rule.get("gender", DEFAULT_PROFILE["gender"]),
                        "age": rule.get("age", DEFAULT_PROFILE["age"]),
                        "regions": REGION_RULES.get(tag, REGION_RULES["default"]),
                        "traits": TRAITS_RULES.get(category, TRAITS_RULES["neutral"]),
                    }
                    profiles.append(profile)
                    weights.append(weight)

        # 合并基础画像
        merged = _merge_profiles(profiles, weights)

        # 性别/年龄归一化到约100
        gender = _normalize_to_100(merged["gender"], ["female", "male"])
        age = _normalize_to_100(merged["age"], ["18-24", "25-34", "35-44", "45+"])

        gender_category = _categorize_gender(gender["female"], gender["male"])

        # 地域分布
        regions = _build_regions(dramas, merged.get("regions", []))

        # 特征标签（基于榜单标签 + 性别类别）
        traits = _build_traits(gender_category, dramas)

        # 内容偏好
        content_preferences = _build_content_preferences(dramas)

        # 观看时段
        viewing_time = _build_viewing_time(gender_category)

        # 付费能力
        spending_power = _build_spending_power(gender_category, dramas, gender["female"])

        # 用户分层
        user_segments = _build_user_segments(gender_category)

        audience_profile = AudienceProfile(
            gender=gender,
            age=age,
            regions=regions,
            traits=traits,
            content_preferences=content_preferences,
            viewing_time=viewing_time,
            spending_power=spending_power,
            user_segments=user_segments,
        )

        logger.info(
            "✅ 受众画像分析完成：女性%d%%，男性%d%%，45+占比%d%%，TOP1地域%s",
            gender["female"],
            gender["male"],
            age["45+"],
            regions[0]["name"] if regions else "未知",
        )

        return AudienceProfileOutput(
            audience_profile=audience_profile,
        )

    except Exception as e:
        logger.error("audience_profile_node: 受众画像分析失败: %s", e, exc_info=True)
        return AudienceProfileOutput(
            audience_profile=AudienceProfile(),
            error_message=f"受众画像分析失败: {e}\n",
        )
