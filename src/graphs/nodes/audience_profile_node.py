"""
受众画像节点 - 基于榜单标签纯本地规则推理受众特征
无需调用任何外部 API（Kimi / DeepSeek / DataEye），纯本地 Python 计算
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
# 每个规则包含性别与年龄分布；地域 / 特征由主导性别与高频标签二次推导

TAG_AUDIENCE_RULES: Dict[str, Dict[str, Dict[str, int]]] = {
    # 女频：都市爱情 / 甜宠
    "都市爱情": {"gender": {"female": 75, "male": 25}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "甜宠": {"gender": {"female": 80, "male": 20}, "age": {"18-24": 25, "25-34": 40, "35-44": 25, "45+": 10}},
    "高糖甜宠": {"gender": {"female": 82, "male": 18}, "age": {"18-24": 28, "25-34": 40, "35-44": 22, "45+": 10}},
    "萌宝": {"gender": {"female": 78, "male": 22}, "age": {"18-24": 15, "25-34": 38, "35-44": 35, "45+": 12}},
    "带球跑": {"gender": {"female": 80, "male": 20}, "age": {"18-24": 20, "25-34": 40, "35-44": 28, "45+": 12}},
    "先婚后爱": {"gender": {"female": 78, "male": 22}, "age": {"18-24": 20, "25-34": 38, "35-44": 30, "45+": 12}},
    "闪婚": {"gender": {"female": 72, "male": 28}, "age": {"18-24": 22, "25-34": 36, "35-44": 28, "45+": 14}},
    "破镜重圆": {"gender": {"female": 76, "male": 24}, "age": {"18-24": 18, "25-34": 38, "35-44": 30, "45+": 14}},
    "年下恋": {"gender": {"female": 82, "male": 18}, "age": {"18-24": 28, "25-34": 42, "35-44": 22, "45+": 8}},

    # 女频：霸总 / 豪门
    "霸总": {"gender": {"female": 82, "male": 18}, "age": {"18-24": 25, "25-34": 42, "35-44": 25, "45+": 8}},
    "总裁": {"gender": {"female": 80, "male": 20}, "age": {"18-24": 24, "25-34": 42, "35-44": 26, "45+": 8}},
    "豪门": {"gender": {"female": 78, "male": 22}, "age": {"18-24": 22, "25-34": 40, "35-44": 28, "45+": 10}},

    # 女频：复仇 / 逆袭 / 真假千金
    "打脸虐渣": {"gender": {"female": 75, "male": 25}, "age": {"18-24": 18, "25-34": 35, "35-44": 32, "45+": 15}},
    "真假千金": {"gender": {"female": 78, "male": 22}, "age": {"18-24": 20, "25-34": 35, "35-44": 32, "45+": 13}},
    "女性成长": {"gender": {"female": 85, "male": 15}, "age": {"18-24": 20, "25-34": 40, "35-44": 30, "45+": 10}},

    # 古风 / 穿越 / 重生
    "古风爱情": {"gender": {"female": 75, "male": 25}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "古装爱情": {"gender": {"female": 75, "male": 25}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "宫斗宅斗": {"gender": {"female": 70, "male": 30}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "重生": {"gender": {"female": 65, "male": 35}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "穿越": {"gender": {"female": 60, "male": 40}, "age": {"18-24": 25, "25-34": 35, "35-44": 25, "45+": 15}},
    "穿越重生": {"gender": {"female": 63, "male": 37}, "age": {"18-24": 22, "25-34": 35, "35-44": 28, "45+": 15}},

    # 复仇（中性偏女）
    "复仇": {"gender": {"female": 68, "male": 32}, "age": {"18-24": 18, "25-34": 35, "35-44": 32, "45+": 15}},
    "复仇逆袭": {"gender": {"female": 68, "male": 32}, "age": {"18-24": 18, "25-34": 35, "35-44": 32, "45+": 15}},
    "逆袭": {"gender": {"female": 40, "male": 60}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},

    # 男频
    "战神归来": {"gender": {"female": 20, "male": 80}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "战神": {"gender": {"female": 22, "male": 78}, "age": {"18-24": 16, "25-34": 32, "35-44": 34, "45+": 18}},
    "赘婿逆袭": {"gender": {"female": 25, "male": 75}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "赘婿": {"gender": {"female": 25, "male": 75}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "强者回归": {"gender": {"female": 25, "male": 75}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "无敌神医": {"gender": {"female": 28, "male": 72}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
    "大男主": {"gender": {"female": 22, "male": 78}, "age": {"18-24": 18, "25-34": 32, "35-44": 35, "45+": 15}},

    # 玄幻 / 仙侠 / 异能（偏男）
    "都市玄幻": {"gender": {"female": 30, "male": 70}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "玄幻仙侠": {"gender": {"female": 35, "male": 65}, "age": {"18-24": 25, "25-34": 35, "35-44": 25, "45+": 15}},
    "仙侠": {"gender": {"female": 35, "male": 65}, "age": {"18-24": 25, "25-34": 35, "35-44": 25, "45+": 15}},
    "都市异能": {"gender": {"female": 32, "male": 68}, "age": {"18-24": 22, "25-34": 36, "35-44": 28, "45+": 14}},
    "权谋": {"gender": {"female": 35, "male": 65}, "age": {"18-24": 18, "25-34": 32, "35-44": 32, "45+": 18}},

    # 中性 / 家庭 / 现实
    "悬疑": {"gender": {"female": 45, "male": 55}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "喜剧": {"gender": {"female": 50, "male": 50}, "age": {"18-24": 25, "25-34": 35, "35-44": 25, "45+": 15}},
    "家庭伦理": {"gender": {"female": 55, "male": 45}, "age": {"18-24": 10, "25-34": 25, "35-44": 40, "45+": 25}},
    "亲情": {"gender": {"female": 60, "male": 40}, "age": {"18-24": 10, "25-34": 25, "35-44": 35, "45+": 30}},
    "剧情": {"gender": {"female": 50, "male": 50}, "age": {"18-24": 20, "25-34": 35, "35-44": 30, "45+": 15}},
    "现实": {"gender": {"female": 52, "male": 48}, "age": {"18-24": 15, "25-34": 30, "35-44": 35, "45+": 20}},
}

# 地域默认分布（当榜单没有明显地域偏好时使用）
DEFAULT_REGIONS = [
    {"name": "广东", "value": 12},
    {"name": "山东", "value": 10},
    {"name": "河南", "value": 9},
    {"name": "四川", "value": 8},
    {"name": "河北", "value": 7},
]

# 男频榜单略有差异：山东 / 河北 / 河南占比更高
MALE_REGIONS = [
    {"name": "山东", "value": 14},
    {"name": "河北", "value": 11},
    {"name": "河南", "value": 10},
    {"name": "四川", "value": 8},
    {"name": "广东", "value": 7},
]

# 特征标签库，按性别主导分类
TRAITS_LIBRARY = {
    "female": [
        "偏好强反转高密度剧情",
        "关注女性成长与逆袭补偿",
        "习惯碎片化连续追更",
        "对身份反差爽点敏感",
        "对高甜撒糖与情感代偿高度敏感",
        "热衷逆袭打脸与身份反转爽点",
    ],
    "male": [
        "偏好权力升级与战斗爽感",
        "关注事业逆袭与财富积累",
        "习惯快速节奏不拖沓",
        "对打脸复仇情节敏感",
        "偏好强者回归带来的信息差爽感",
    ],
    "neutral": [
        "偏好强反转高密度剧情",
        "关注社会现实与情感共鸣",
        "习惯碎片化连续追更",
        "对剧情深度要求高",
    ],
}


# ==================== 辅助函数 ====================

def _drama_to_dict(drama: Any) -> Dict[str, Any]:
    """统一将 Pydantic 对象或字典转换为字典"""
    if isinstance(drama, dict):
        return drama
    if hasattr(drama, "model_dump"):
        return drama.model_dump()
    return {}


def _collect_tags(drama: Dict[str, Any]) -> List[str]:
    """从一部剧中提取所有标签"""
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

    return list(dict.fromkeys(tags))


def _weighted_average(values: List[int], weights: List[float]) -> float:
    """加权平均"""
    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_weight


def _normalize_to_100(values: Dict[str, int], keys: List[str]) -> Dict[str, int]:
    """将数值归一化为总和严格等于 100"""
    raw = {k: max(0, values.get(k, 0)) for k in keys}
    total = sum(raw.values())
    if total == 0:
        return {k: round(100 / len(keys)) for k in keys}

    normalized = {k: round(v / total * 100) for k, v in raw.items()}
    diff = 100 - sum(normalized.values())
    if diff != 0 and normalized:
        max_key = max(normalized, key=lambda k: normalized[k])
        normalized[max_key] += diff
    return normalized


def _infer_profile(enriched_rankings: List[Any]) -> Dict[str, Any]:
    """基于榜单标签加权推理核心受众画像（gender / age）"""
    # 收集所有命中规则的标签及其权重
    values_female: List[float] = []
    values_male: List[float] = []
    values_age: Dict[str, List[float]] = {k: [] for k in ("18-24", "25-34", "35-44", "45+")}
    weights: List[float] = []

    for drama in enriched_rankings:
        drama_dict = _drama_to_dict(drama)
        rank = drama_dict.get("rank", 50)
        # 排名越靠前权重越高：TOP1=20, TOP20=1
        weight = max(1.0, 21 - rank)

        for tag in _collect_tags(drama_dict):
            rule = TAG_AUDIENCE_RULES.get(tag)
            if not rule:
                continue

            gender = rule["gender"]
            age = rule["age"]
            values_female.append(float(gender["female"]))
            values_male.append(float(gender["male"]))
            for k in values_age:
                values_age[k].append(float(age[k]))
            weights.append(weight)

    # 没有任何标签命中时，返回中性默认画像
    if not weights:
        return {
            "gender": {"female": 52, "male": 48},
            "age": {"18-24": 18, "25-34": 35, "35-44": 30, "45+": 17},
        }

    gender_female = round(_weighted_average(values_female, weights))
    gender_male = round(_weighted_average(values_male, weights))
    age = {k: round(_weighted_average(values_age[k], weights)) for k in values_age}

    return {
        "gender": _normalize_to_100({"female": gender_female, "male": gender_male}, ["female", "male"]),
        "age": _normalize_to_100(age, ["18-24", "25-34", "35-44", "45+"]),
    }


def _dominant_gender(gender: Dict[str, int]) -> str:
    """判断主导性别类别"""
    female = gender.get("female", 50)
    male = gender.get("male", 50)
    if female >= 60:
        return "female"
    if male >= 60:
        return "male"
    return "neutral"


def _build_regions(gender_category: str, enriched_rankings: List[Any]) -> List[Dict[str, Any]]:
    """根据主导性别与榜单题材生成地域分布"""
    # 简单规则：男频主导时使用男频地域分布
    if gender_category == "male":
        return [r.copy() for r in MALE_REGIONS]
    return [r.copy() for r in DEFAULT_REGIONS]


def _build_traits(gender_category: str, enriched_rankings: List[Any]) -> List[str]:
    """基于榜单高频标签生成 4 条受众特征"""
    all_tags: set = set()
    for drama in enriched_rankings:
        all_tags.update(_collect_tags(_drama_to_dict(drama)))

    specific_traits: List[str] = []

    if any(t in all_tags for t in ("甜宠", "高糖甜宠", "先婚后爱", "闪婚", "年下恋")):
        specific_traits.append("对高甜撒糖与情感代偿高度敏感")
    if any(t in all_tags for t in ("复仇", "复仇逆袭", "打脸虐渣", "真假千金")):
        specific_traits.append("热衷逆袭打脸与身份反转爽点")
    if any(t in all_tags for t in ("霸总", "总裁", "豪门")):
        specific_traits.append("偏好强权力差与玛丽苏情绪价值")
    if any(t in all_tags for t in ("战神", "战神归来", "强者回归", "赘婿逆袭", "赘婿")):
        specific_traits.append("偏好权力升级与战斗打脸爽感")
    if any(t in all_tags for t in ("穿越", "重生", "穿越重生")):
        specific_traits.append("习惯重生穿越带来的信息差爽感")
    if any(t in all_tags for t in ("悬疑", "推理", "权谋")):
        specific_traits.append("偏好烧脑推理与逻辑反转")

    base_traits = TRAITS_LIBRARY.get(gender_category, TRAITS_LIBRARY["neutral"]).copy()

    result = specific_traits[:2]
    for trait in base_traits:
        if len(result) >= 4:
            break
        if trait not in result:
            result.append(trait)

    # 兜底补全
    fallback = "习惯碎片化连续追更"
    while len(result) < 4:
        result.append(fallback)

    return result[:4]


# ==================== 节点主函数 ====================

def audience_profile_node(
    state: AudienceProfileInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> AudienceProfileOutput:
    """
    title: 👥 受众画像分析
    desc: 基于榜单标签，纯本地规则推理受众画像（gender / age / regions / traits）
    integrations: 无外部 API 调用，纯本地 Python 计算
    """
    try:
        data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
        enriched_rankings = state.enriched_rankings or []

        if not enriched_rankings:
            logger.warning("audience_profile_node: 输入榜单为空，使用默认受众画像")

        # 1. 核心画像加权推理
        profile = _infer_profile(enriched_rankings)
        gender = profile["gender"]
        age = profile["age"]

        # 2. 地域与特征由主导性别二次推导
        gender_category = _dominant_gender(gender)
        regions = _build_regions(gender_category, enriched_rankings)
        traits = _build_traits(gender_category, enriched_rankings)

        audience_profile = AudienceProfile(
            gender=gender,
            age=age,
            regions=regions,
            traits=traits,
        )

        # 前端 H5 兼容日志：必须包含 "受众画像完成：女性XX%，25-34岁占比XX%"
        logger.info(
            "受众画像完成：女性%d%%，25-34岁占比%d%%",
            gender["female"],
            age["25-34"],
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
