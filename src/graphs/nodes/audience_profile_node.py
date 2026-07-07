"""
受众画像节点 - 月度行业报告基准 + 周度榜单信号

核心策略：
1. 观众画像基于真实行业报告，报告发布周期为月度，因此以自然月为粒度缓存。
2. 每月/缓存缺失时，使用 Kimi 联网搜索最新行业报告并解析完整画像。
3. 每日从 TOP20 榜单加权统计「本周信号」：性别/题材/AI/新剧等实时指标。
4. 与昨日历史归档对比生成环比趋势与分析师洞察，让板块有动态分析价值。
5. 搜索失败或解析异常时，降级为本地规则推理画像。
"""
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import AudienceProfile, AudienceProfileInput, AudienceProfileOutput
from tools.audience_profile_cache import (
    get_default_profile,
    load_cache,
    save_cache,
)

# Fallback for test_run environment
try:
    from tools.moonshot_api import MoonshotClient, is_api_budget_error
except ImportError:  # pragma: no cover
    class MoonshotClient:  # type: ignore
        def search_json(self, *args, **kwargs):
            return {}

    def is_api_budget_error(exc: Exception) -> bool:
        return "API 调用次数过多，已熔断" in str(exc)


logger = logging.getLogger(__name__)


# ==================== 兜底规则：本地标签 → 受众画像映射 ====================
# 当 Kimi 搜索失败或缓存不可用时，仍基于榜单标签做规则推理，保证流程不中断。

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

DEFAULT_REGIONS = [
    {"name": "广东", "value": 12},
    {"name": "山东", "value": 10},
    {"name": "河南", "value": 9},
    {"name": "四川", "value": 8},
    {"name": "河北", "value": 7},
]

MALE_REGIONS = [
    {"name": "山东", "value": 14},
    {"name": "河北", "value": 11},
    {"name": "河南", "value": 10},
    {"name": "四川", "value": 8},
    {"name": "广东", "value": 7},
]

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


# ==================== 通用辅助函数 ====================

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


def _safe_int(value: Any, default: int = 0, min_value: int = 0, max_value: int = 100) -> int:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            number = int(round(value))
        elif isinstance(value, str):
            cleaned = value.strip().replace(",", "").replace("%", "")
            if not cleaned or cleaned.lower() in {"未知", "无", "暂无", "n/a", "null", "none", "-"}:
                return default
            match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
            number = int(round(float(match.group()))) if match else default
        else:
            return default
        return max(min_value, min(max_value, number))
    except Exception:
        return default


def _safe_percent_dict(raw: Any, keys: List[str]) -> Dict[str, int]:
    """安全解析百分比字典，并归一化为 100"""
    if not isinstance(raw, dict):
        raw = {}
    values = {k: _safe_int(raw.get(k), 0, 0, 100) for k in keys}
    return _normalize_to_100(values, keys)


def _safe_named_list(raw: Any, top_n: int = 6, default_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """安全解析 [{name, value}] 列表，过滤非法项并归一化"""
    if not isinstance(raw, list):
        return []

    items = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            continue
        items.append({"name": name.strip(), "value": _safe_int(item.get("value"), 0, 0, 100)})

    if not items and default_names:
        items = [{"name": name, "value": round(100 / len(default_names))} for name in default_names]

    items = items[:top_n]
    if not items:
        return []

    total = sum(item["value"] for item in items)
    if total <= 0:
        return [{"name": item["name"], "value": round(100 / len(items))} for item in items]

    normalized = [{"name": item["name"], "value": round(item["value"] / total * 100)} for item in items]
    diff = 100 - sum(item["value"] for item in normalized)
    if diff != 0 and normalized:
        normalized[0]["value"] += diff
    return normalized


def _safe_segments(raw: Any) -> List[Dict[str, Any]]:
    """安全解析用户分层"""
    if not isinstance(raw, list):
        return []
    segments = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            continue
        segments.append({
            "name": name.strip(),
            "share": _safe_int(item.get("share"), 0, 0, 100),
            "desc": str(item.get("desc", "")).strip(),
        })
    return segments[:4]


def _safe_spending(raw: Any) -> Dict[str, Any]:
    """安全解析付费能力"""
    if not isinstance(raw, dict):
        return {"paid_ratio": 35, "arpu": "¥18", "willingness": "中高"}
    return {
        "paid_ratio": _safe_int(raw.get("paid_ratio"), 35, 0, 100),
        "arpu": str(raw.get("arpu", "¥18")).strip() or "¥18",
        "willingness": str(raw.get("willingness", "中高")).strip() or "中高",
    }


# ==================== 兜底规则推理 ====================

def _infer_profile(enriched_rankings: List[Any]) -> Dict[str, Any]:
    """基于榜单标签加权推理核心受众画像（gender / age）"""
    values_female: List[float] = []
    values_male: List[float] = []
    values_age: Dict[str, List[float]] = {k: [] for k in ("18-24", "25-34", "35-44", "45+")}
    weights: List[float] = []

    for drama in enriched_rankings:
        drama_dict = _drama_to_dict(drama)
        rank = drama_dict.get("rank", 50)
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


def _build_regions(gender_category: str, _enriched_rankings: List[Any]) -> List[Dict[str, Any]]:
    """根据主导性别生成地域分布"""
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

    fallback = "习惯碎片化连续追更"
    while len(result) < 4:
        result.append(fallback)

    return result[:4]


def _build_fallback_profile(enriched_rankings: List[Any]) -> Dict[str, Any]:
    """搜索失败时的兜底画像：基于榜单规则，其余字段留空"""
    profile = _infer_profile(enriched_rankings)
    gender_category = _dominant_gender(profile["gender"])

    return {
        "gender": profile["gender"],
        "age": profile["age"],
        "regions": _build_regions(gender_category, enriched_rankings),
        "traits": _build_traits(gender_category, enriched_rankings),
        "content_preferences": [],
        "viewing_time": [],
        "spending_power": {},
        "user_segments": [],
        "source_title": "基于当日榜单标签规则推理（行业报告搜索失败或缺失，部分字段留空）",
        "source_url": "",
        "report_date": "",
    }


# ==================== Kimi 搜索月度行业报告 ====================

def _load_llm_cfg(config: RunnableConfig) -> Dict[str, Any]:
    """读取 LLM 配置文件"""
    cfg_path = ""
    metadata = config.get("metadata", {}) if config else {}
    if metadata.get("llm_cfg"):
        cfg_path = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), metadata["llm_cfg"])

    if cfg_path and os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("audience_profile_node: 读取 LLM 配置失败: %s", e)

    return {}


def _search_monthly_profile(client: MoonshotClient, date_str: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """使用 Kimi 搜索最新行业报告并解析为观众画像"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        year, month = dt.year, dt.month
    except ValueError:
        now = datetime.now()
        year, month = now.year, now.month

    sp = cfg.get(
        "sp",
        "你是专业的短剧行业研究分析师，擅长从互联网搜索并提取结构化行业报告数据。"
        "你必须联网搜索，优先使用有具体数字的权威来源，不要编造数据。",
    )

    up_template = cfg.get("up")
    if up_template:
        try:
            prompt = Template(up_template).render(year=year, month=month, date=date_str)
        except Exception as e:
            logger.warning("audience_profile_node: Jinja2 渲染 prompt 失败，使用内置 prompt: %s", e)
            prompt = _build_inline_search_prompt(year, month)
    else:
        prompt = _build_inline_search_prompt(year, month)

    config_model = cfg.get("config", {})
    result = client.search_json(
        query=prompt,
        system_prompt=sp,
        temperature=float(config_model.get("temperature", 0.2)),
        max_tokens=int(config_model.get("max_completion_tokens", 2500) or 2500),
        expected_type=dict,
    )

    if not isinstance(result, dict):
        raise ValueError(f"Kimi 返回非字典结果: {type(result)}")

    return result


def _build_inline_search_prompt(year: int, month: int) -> str:
    """内置搜索 prompt，当配置文件缺失时使用"""
    return f"""请联网搜索 {year}年{month}月 国内短剧行业观众画像/用户研究报告，
优先查找 QuestMobile、DataEye、蝉妈妈、勾正数据、艾瑞咨询等机构发布的报告。
需要提取：性别比例、年龄分布、地域分布、内容题材偏好、观看时段、付费率/ARPU、用户分层。

请严格返回以下 JSON 格式（不要省略字段），所有百分比类字段数值范围 0-100：
{{
  "source_title": "报告标题",
  "source_url": "报告原始链接",
  "report_date": "报告发布日期，格式 YYYY-MM-DD",
  "gender": {{"female": 70, "male": 30}},
  "age": {{"18-24": 20, "25-34": 42, "35-44": 28, "45+": 10}},
  "regions": [{{"name": "广东", "value": 15.5}}, {{"name": "江苏", "value": 11.8}}],
  "traits": ["特征1", "特征2", "特征3", "特征4"],
  "content_preferences": [{{"name": "都市爱情", "value": 32}}, {{"name": "穿越重生", "value": 24}}],
  "viewing_time": [{{"name": "睡前 22-24点", "value": 35}}, {{"name": "晚间 20-22点", "value": 28}}],
  "spending_power": {{"paid_ratio": 35, "arpu": "¥18", "willingness": "中高"}},
  "user_segments": [{{"name": "核心追更党", "share": 28, "desc": "日更必追、愿意为爆款付费解锁"}}]
}}

约束：
1. gender 两个字段之和必须等于 100，age 四个字段之和必须等于 100。
2. regions/content_preferences/viewing_time 如果有多个条目，value 之和尽量接近 100。
3. 如果某字段确实搜索不到，使用合理估算值填充，并在 source_title 中注明"估算"。
4. 不要返回任何 JSON 之外的解释文字。"""


def _validate_profile(raw: Dict[str, Any]) -> bool:
    """校验搜索返回的画像是否可用"""
    if not isinstance(raw, dict):
        return False

    gender = raw.get("gender")
    age = raw.get("age")
    if not isinstance(gender, dict) or not isinstance(age, dict):
        return False

    # 读取原始值，要求模型返回的数据自身已经平衡
    g_female = _safe_int(gender.get("female"), -1, 0, 100)
    g_male = _safe_int(gender.get("male"), -1, 0, 100)
    a_18_24 = _safe_int(age.get("18-24"), -1, 0, 100)
    a_25_34 = _safe_int(age.get("25-34"), -1, 0, 100)
    a_35_44 = _safe_int(age.get("35-44"), -1, 0, 100)
    a_45_plus = _safe_int(age.get("45+"), -1, 0, 100)

    if -1 in (g_female, g_male, a_18_24, a_25_34, a_35_44, a_45_plus):
        return False

    if abs(g_female + g_male - 100) > 1 or abs(a_18_24 + a_25_34 + a_35_44 + a_45_plus - 100) > 2:
        return False

    # 基本合理性校验
    if not (20 <= g_female <= 90):
        return False
    if not (20 <= a_25_34 <= 70):
        return False

    return True


def _parse_profile(raw: Dict[str, Any]) -> Dict[str, Any]:
    """将 Kimi 返回解析为标准画像字典（方向 A：缺失时留空，不用固定默认值填充）"""
    profile = {
        "gender": _safe_percent_dict(raw.get("gender"), ["female", "male"]),
        "age": _safe_percent_dict(raw.get("age"), ["18-24", "25-34", "35-44", "45+"]),
        "regions": _safe_named_list(raw.get("regions"), top_n=5),
        "traits": _safe_traits(raw.get("traits")),
        "content_preferences": _safe_named_list(raw.get("content_preferences"), top_n=6),
        "viewing_time": _safe_named_list(raw.get("viewing_time"), top_n=6),
        "spending_power": _safe_spending(raw.get("spending_power")) if raw.get("spending_power") else {},
        "user_segments": _safe_segments(raw.get("user_segments")),
        "source_title": str(raw.get("source_title", "") or "行业报告").strip(),
        "source_url": str(raw.get("source_url", "") or "").strip(),
        "report_date": str(raw.get("report_date", "") or "").strip(),
    }
    return profile


def _safe_traits(raw: Any) -> List[str]:
    """安全解析特征标签"""
    if not isinstance(raw, list):
        return []
    traits = [str(t).strip() for t in raw if isinstance(t, str) and t.strip()]
    return traits[:4]


# ==================== 周度榜单微调 ====================

def _adjust_profile_by_rankings(
    profile: Dict[str, Any], enriched_rankings: List[Any]
) -> Dict[str, Any]:
    """
    根据当周榜单题材对月度基准画像做小幅修正。

    修正逻辑：
    - 男频剧占比高于 35% 时，男性占比上调（最多 +8%）。
    - 家庭伦理/萌宝/亲情标签占比高时，35-44 岁和 45+ 占比略上调。
    - 甜宠/高糖/年下恋占比高时，18-24 岁占比略上调。
    """
    if not enriched_rankings:
        return profile

    total = len(enriched_rankings)
    male_count = sum(1 for r in enriched_rankings if _drama_to_dict(r).get("category") == "male")
    male_ratio = male_count / total

    all_tags: set = set()
    for drama in enriched_rankings:
        all_tags.update(_collect_tags(_drama_to_dict(drama)))

    gender = dict(profile["gender"])
    age = dict(profile["age"])

    # 性别微调
    if male_ratio > 0.35:
        delta = min(8, int((male_ratio - 0.35) * 20))
        gender["male"] = min(90, gender["male"] + delta)
        gender["female"] = 100 - gender["male"]
    elif male_ratio < 0.15 and gender["male"] > 30:
        delta = min(5, int((0.15 - male_ratio) * 20))
        gender["female"] = min(90, gender["female"] + delta)
        gender["male"] = 100 - gender["female"]

    # 年龄微调
    family_tags = {"家庭伦理", "亲情", "萌宝", "带球跑"}
    sweet_tags = {"甜宠", "高糖甜宠", "年下恋", "校园", "青春"}

    family_score = sum(1 for t in family_tags if t in all_tags)
    sweet_score = sum(1 for t in sweet_tags if t in all_tags)

    if family_score >= 2:
        # 家庭题材增加 35-44 和 45+ 占比
        shift = min(5, family_score)
        age["35-44"] = min(50, age["35-44"] + shift)
        age["45+"] = min(40, age["45+"] + shift)
        # 从 18-24 扣除
        deduct = min(shift * 2, age["18-24"])
        age["18-24"] -= deduct
        remaining = shift * 2 - deduct
        if remaining > 0:
            age["25-34"] = max(10, age["25-34"] - remaining)

    if sweet_score >= 2:
        # 甜宠题材增加 18-24 占比
        shift = min(5, sweet_score)
        age["18-24"] = min(40, age["18-24"] + shift)
        # 从 35-44/45+ 扣除
        deduct = min(shift, age["35-44"])
        age["35-44"] -= deduct
        if deduct < shift:
            age["45+"] = max(5, age["45+"] - (shift - deduct))

    # 重新归一化
    profile["gender"] = _normalize_to_100(gender, ["female", "male"])
    profile["age"] = _normalize_to_100(age, ["18-24", "25-34", "35-44", "45+"])

    # 根据男频占比调整地域（男频主导时北方省份占比略高）
    if profile["gender"]["male"] >= 55:
        profile["regions"] = [r.copy() for r in MALE_REGIONS]

    return profile


# ==================== 周度榜单信号与趋势分析 ====================

def _rank_weight(rank: Any) -> float:
    """排名越靠前权重越高（TOP1=20, TOP20=1）"""
    try:
        r = int(rank)
    except (TypeError, ValueError):
        r = 20
    return float(max(1, 21 - r))


def _compute_weekly_signals(enriched_rankings: List[Any]) -> Dict[str, Any]:
    """
    从当日 TOP20 榜单加权统计本周观众信号。
    这些指标每日变化，是板块「有意义」的核心数据来源。
    """
    if not enriched_rankings:
        return {}

    total_weight = 0.0
    female_weight = 0.0
    male_weight = 0.0
    ai_weight = 0.0
    new_weight = 0.0
    genre_counter: Counter = Counter()
    tag_counter: Counter = Counter()

    for drama in enriched_rankings:
        d = _drama_to_dict(drama)
        w = _rank_weight(d.get("rank", 20))
        total_weight += w

        category = str(d.get("category", "")).lower()
        if category == "female":
            female_weight += w
        elif category == "male":
            male_weight += w
        else:
            # 未标注时按题材规则推断
            inferred = _infer_profile([drama])
            female_weight += w * inferred["gender"]["female"] / 100
            male_weight += w * inferred["gender"]["male"] / 100

        if d.get("is_ai"):
            ai_weight += w
        if d.get("is_new"):
            new_weight += w

        genre = str(d.get("genre", "")).strip()
        if genre:
            genre_counter[genre] += w

        for tag in _collect_tags(d):
            tag_counter[tag] += w

    if total_weight <= 0:
        return {}

    female_ratio = round(female_weight / total_weight * 100)
    male_ratio = 100 - female_ratio
    ai_ratio = round(ai_weight / total_weight * 100)
    new_ratio = round(new_weight / total_weight * 100)

    top_genres = [
        {"name": name, "share": round(count / total_weight * 100)}
        for name, count in genre_counter.most_common(5)
    ]
    top_tags = [
        {"name": name, "share": round(count / total_weight * 100)}
        for name, count in tag_counter.most_common(5)
    ]

    return {
        "female_ratio": female_ratio,
        "male_ratio": male_ratio,
        "ai_ratio": ai_ratio,
        "new_drama_ratio": new_ratio,
        "top_genres": top_genres,
        "top_tags": top_tags,
        "ranking_count": len(enriched_rankings),
        "basis": "TOP20排名加权",
    }


def _history_dir() -> Path:
    workspace = os.getenv("COZE_WORKSPACE_PATH", os.getcwd())
    return Path(workspace) / "assets" / "data" / "history"


def _load_previous_weekly_signals(data_date: str, lookback_days: int = 7) -> Optional[Dict[str, Any]]:
    """从历史归档加载最近一次有效的 weekly_signals，用于环比对比。"""
    try:
        current = datetime.strptime(data_date, "%Y-%m-%d")
    except ValueError:
        return None

    history_path = _history_dir()
    if not history_path.exists():
        return None

    for offset in range(1, lookback_days + 1):
        prev_date = (current - timedelta(days=offset)).strftime("%Y-%m-%d")
        file_path = history_path / f"{prev_date}.json"
        if not file_path.exists():
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            signals = (data.get("audience_profile") or {}).get("weekly_signals") or {}
            if signals.get("female_ratio") is not None:
                return {"date": prev_date, "signals": signals}
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _compute_weekly_trends(
    current: Dict[str, Any], previous: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """计算本周信号相对昨日的环比变化。"""
    if not current or not previous:
        return {}

    prev_signals = previous.get("signals", {})
    prev_date = previous.get("date", "")

    def _delta(key: str) -> int:
        cur = current.get(key, 0)
        prev = prev_signals.get(key, 0)
        if not isinstance(cur, (int, float)) or not isinstance(prev, (int, float)):
            return 0
        return int(round(cur - prev))

    def _trend(delta: int) -> str:
        if delta > 1:
            return "up"
        if delta < -1:
            return "down"
        return "same"

    female_delta = _delta("female_ratio")
    ai_delta = _delta("ai_ratio")
    new_delta = _delta("new_drama_ratio")

    # 题材轮动：找 share 变化最大的题材
    genre_shift = ""
    cur_genres = {g["name"]: g["share"] for g in current.get("top_genres", [])}
    prev_genres = {g["name"]: g["share"] for g in prev_signals.get("top_genres", [])}
    if cur_genres and prev_genres:
        shifts = []
        for name, share in cur_genres.items():
            prev_share = prev_genres.get(name, 0)
            shifts.append((name, share - prev_share))
        for name, prev_share in prev_genres.items():
            if name not in cur_genres:
                shifts.append((name, -prev_share))
        if shifts:
            best = max(shifts, key=lambda x: abs(x[1]))
            if abs(best[1]) >= 2:
                direction = "升温" if best[1] > 0 else "降温"
                genre_shift = f"{best[0]}{direction}{abs(best[1])}pp"

    return {
        "compared_to": prev_date,
        "female_ratio_delta": female_delta,
        "female_ratio_trend": _trend(female_delta),
        "ai_ratio_delta": ai_delta,
        "ai_ratio_trend": _trend(ai_delta),
        "new_drama_ratio_delta": new_delta,
        "new_drama_ratio_trend": _trend(new_delta),
        "genre_shift": genre_shift,
    }


def _generate_analyst_insights(
    baseline: Dict[str, Any],
    signals: Dict[str, Any],
    trends: Dict[str, Any],
) -> List[str]:
    """
    基于行业基准 vs 本周榜单信号，生成 2-4 条可执行分析师洞察。
    纯规则推理，不消耗 API token。
    """
    if not signals:
        return ["暂无榜单信号，待 TOP20 数据就绪后生成周度分析。"]

    insights: List[str] = []
    female_signal = signals.get("female_ratio", 0)
    female_baseline = baseline.get("gender", {}).get("female", 0)
    female_delta = trends.get("female_ratio_delta", 0)

    # 1. 性别浓度 vs 行业基准
    if female_baseline > 0:
        gap = female_signal - female_baseline
        if abs(gap) >= 8:
            direction = "高于" if gap > 0 else "低于"
            insights.append(
                f"本周爆款女频浓度 {female_signal}%，{direction}行业基准 {female_baseline}% "
                f"（差 {abs(gap)}pp），内容策略{'极致女频' if gap > 0 else '男频渗透'}"
            )
        else:
            insights.append(
                f"本周爆款女频占比 {female_signal}%，与行业基准 {female_baseline}% 基本吻合"
            )
    else:
        insights.append(f"本周榜单女频占比 {female_signal}%")

    # 2. 环比变化
    if female_delta != 0 and trends.get("compared_to"):
        arrow = "↑" if female_delta > 0 else "↓"
        insights.append(
            f"较 {trends['compared_to']} 女频占比 {arrow}{abs(female_delta)}pp"
        )

    # 3. 题材轮动
    top_genres = signals.get("top_genres", [])
    if top_genres:
        leader = top_genres[0]
        genre_line = f"题材领跑：{leader['name']}（权重 {leader['share']}%）"
        if trends.get("genre_shift"):
            genre_line += f"，{trends['genre_shift']}"
        insights.append(genre_line)

    # 4. 新剧/AI 信号
    new_ratio = signals.get("new_drama_ratio", 0)
    ai_ratio = signals.get("ai_ratio", 0)
    extras = []
    if new_ratio >= 20:
        extras.append(f"新剧占比 {new_ratio}%，黑马频出")
    elif new_ratio <= 5:
        extras.append(f"新剧占比仅 {new_ratio}%，老剧续航力强")
    if ai_ratio >= 15:
        extras.append(f"AI 剧占 {ai_ratio}%，高于行业均值")
    elif ai_ratio > 0:
        extras.append(f"AI 剧占 {ai_ratio}%")
    if extras:
        insights.append("；".join(extras))

    return insights[:4]


# ==================== 节点主函数 ====================

def audience_profile_node(
    state: AudienceProfileInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> AudienceProfileOutput:
    """
    title: 👥 受众画像分析
    desc: 基于月度行业报告基准 + 当周榜单题材微调，输出观众画像
    integrations: Moonshot API（仅月度缓存缺失时调用一次）
    """
    try:
        data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
        enriched_rankings = state.enriched_rankings or []

        cache = load_cache(today=data_date)
        source_note = ""

        if cache:
            # 命中本月缓存，直接作为基准
            profile = _parse_profile(cache.get("profile", {}))
            source_note = (
                f"数据来源：{cache.get('source_title', '行业报告')} "
                f"（报告日期：{cache.get('report_date', '未知')}）"
            )
            logger.info("audience_profile_node: 使用本月缓存基准，%s", source_note)
        else:
            # 缓存缺失，尝试 Kimi 搜索
            cfg = _load_llm_cfg(config)
            client = MoonshotClient()
            try:
                raw_profile = _search_monthly_profile(client, data_date, cfg)
                if _validate_profile(raw_profile):
                    profile = _parse_profile(raw_profile)
                    save_cache(
                        profile=profile,
                        source_url=profile.get("source_url", ""),
                        source_title=profile.get("source_title", "行业报告"),
                        report_date=profile.get("report_date", ""),
                        today=data_date,
                    )
                    source_note = (
                        f"数据来源：{profile.get('source_title', '行业报告')} "
                        f"（报告日期：{profile.get('report_date', '未知')}）"
                    )
                    logger.info("audience_profile_node: 搜索并保存月度基准，%s", source_note)
                else:
                    raise ValueError("Kimi 返回画像未通过校验")
            except Exception as e:
                if is_api_budget_error(e):
                    raise
                logger.warning("audience_profile_node: 月度报告搜索失败，降级为本地规则: %s", e)
                profile = _build_fallback_profile(enriched_rankings)
                source_note = (
                    f"数据来源：{profile.get('source_title', '本地规则兜底')} "
                    f"（报告日期：{profile.get('report_date', '未知')}）"
                )

        # 周度微调：基于当周榜单题材对基准做小幅修正
        profile = _adjust_profile_by_rankings(profile, enriched_rankings)

        # 周度榜单信号 + 趋势 + 分析师洞察
        weekly_signals = _compute_weekly_signals(enriched_rankings)
        previous = _load_previous_weekly_signals(data_date)
        weekly_trends = _compute_weekly_trends(weekly_signals, previous)
        analyst_insights = _generate_analyst_insights(profile, weekly_signals, weekly_trends)

        # data_source 是“来源说明”，不应把完整 URL 拼进来（尤其搜索 URL 非常长，
        # 会撑破前端卡片布局）。URL 如需展示可单独放到 source_url，但当前模型未启用。
        data_source = profile.get("source_title", "") or "本地规则估算"

        audience_profile = AudienceProfile(
            gender=profile["gender"],
            age=profile["age"],
            regions=profile["regions"],
            traits=profile["traits"],
            content_preferences=profile.get("content_preferences", []),
            viewing_time=profile.get("viewing_time", []),
            spending_power=profile.get("spending_power", {}),
            user_segments=profile.get("user_segments", []),
            data_source=data_source,
            update_frequency="monthly",
            weekly_signals=weekly_signals,
            weekly_trends=weekly_trends,
            analyst_insights=analyst_insights,
        )

        logger.info(
            "受众画像完成：女性%d%%，25-34岁占比%d%%。%s",
            audience_profile.gender["female"],
            audience_profile.age["25-34"],
            source_note,
        )

        return AudienceProfileOutput(audience_profile=audience_profile)

    except Exception as e:
        logger.error("audience_profile_node: 受众画像分析失败: %s", e, exc_info=True)
        empty_profile = get_default_profile()
        return AudienceProfileOutput(
            audience_profile=AudienceProfile(
                gender=empty_profile["gender"],
                age=empty_profile["age"],
                regions=empty_profile["regions"],
                traits=empty_profile["traits"],
                content_preferences=empty_profile["content_preferences"],
                viewing_time=empty_profile["viewing_time"],
                spending_power=empty_profile["spending_power"],
                user_segments=empty_profile["user_segments"],
                data_source="受众画像分析失败，暂无真实来源",
                update_frequency="monthly",
                weekly_signals={},
                weekly_trends={},
                analyst_insights=[],
            ),
            error_message=f"受众画像分析失败: {e}\n",
        )
