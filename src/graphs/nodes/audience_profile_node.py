"""
观众画像节点 - 获取短剧观众画像数据
"""
import logging
import re
from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.moonshot_api import MoonshotClient, is_api_budget_error

from graphs.state import (
    AudienceProfileInput,
    AudienceProfileOutput,
    AudienceProfile,
    AgeDistribution,
    RegionDistribution
)

logger = logging.getLogger(__name__)


def _default_regions() -> List[RegionDistribution]:
    return [
        RegionDistribution(name="广东", value=12.0),
        RegionDistribution(name="江苏", value=9.0),
        RegionDistribution(name="浙江", value=8.0),
    ]


def _default_audience_profile() -> AudienceProfile:
    return AudienceProfile(
        gender_female=95,
        gender_male=5,
        age_distribution=AgeDistribution(
            age_18_24=35,
            age_25_34=40,
            age_35_44=18,
            age_45_plus=7,
        ),
        top_regions=_default_regions(),
        peak_viewing_hours="21:00-23:00",
        avg_watch_duration="45分钟",
        traits=["女性主导", "年轻群体", "下沉市场"],
    )


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_number(value: Any, default: Any) -> Any:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        if not match:
            return default
        number = float(match.group())
    else:
        return default

    if isinstance(default, int) and not isinstance(default, bool):
        return int(round(number))
    return number


def _safe_text(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _safe_traits(value: Any) -> List[str]:
    default_traits = ["女性主导", "年轻群体", "下沉市场", "碎片化观看"]
    if isinstance(value, list):
        traits = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return traits or default_traits
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return default_traits


def _extract_region_value(region: Dict[str, Any]) -> Any:
    for key in ("value", "占比", "ratio", "percent", "percentage"):
        if key in region:
            return region.get(key)
    return 0.0


def _build_top_regions(raw_regions: Any) -> List[RegionDistribution]:
    top_regions: List[RegionDistribution] = []
    if not isinstance(raw_regions, list):
        raw_regions = []

    for region in raw_regions[:10]:
        if not isinstance(region, dict):
            continue

        name = ""
        for key in ("name", "省份", "城市", "地区", "province", "city"):
            name = _safe_text(region.get(key), "")
            if name:
                break
        if not name:
            continue

        value = float(_safe_number(_extract_region_value(region), 0.0))
        top_regions.append(RegionDistribution(name=name, value=value))

    return top_regions or _default_regions()


def _build_audience_profile(profile_data: Any) -> AudienceProfile:
    safe_profile = _as_dict(profile_data)
    gender = _as_dict(safe_profile.get("gender"))
    age = _as_dict(safe_profile.get("age"))

    age_distribution = AgeDistribution(
        age_18_24=_safe_number(age.get("18-24"), 35),
        age_25_34=_safe_number(age.get("25-34"), 40),
        age_35_44=_safe_number(age.get("35-44"), 18),
        age_45_plus=_safe_number(age.get("45+"), 7),
    )

    return AudienceProfile(
        gender_female=_safe_number(gender.get("female"), 95),
        gender_male=_safe_number(gender.get("male"), 5),
        age_distribution=age_distribution,
        top_regions=_build_top_regions(safe_profile.get("regions")),
        peak_viewing_hours=_safe_text(safe_profile.get("peak_hours"), "21:00-23:00"),
        avg_watch_duration=_safe_text(safe_profile.get("avg_duration"), "45分钟"),
        traits=_safe_traits(safe_profile.get("traits")),
    )


def audience_profile_node(
    state: AudienceProfileInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> AudienceProfileOutput:
    """
    title: 📊 获取观众画像数据
    desc: 使用 Kimi 联网搜索QuestMobile、DataEye等报告，获取短剧观众画像数据
    integrations: Moonshot API
    """
    ctx = runtime.context
    response = ""
    
    try:
        # 初始化 Kimi 客户端
        client = MoonshotClient()
        
        # 使用 Kimi 联网搜索观众画像数据
        search_query = """请搜索互联网，获取短剧观众的画像数据，包括：
1. 性别分布（女性/男性占比）
2. 年龄分布（18-24岁、25-34岁、35-44岁、45岁以上各年龄段占比）
3. 地域分布（Top10省份/城市及占比）
4. 观看时段（高峰时段）
5. 平均观看时长

请搜索QuestMobile、DataEye、云合数据等权威报告的最新数据。

返回JSON格式：
{
  "gender": {"female": xx, "male": xx},
  "age": {"18-24": xx, "25-34": xx, "35-44": xx, "45+": xx},
  "regions": [{"name": "省份名", "value": 占比}],
  "peak_hours": "高峰时段",
  "avg_duration": "平均观看时长"
}
"""
        
        prompt = f"""请联网搜索并提取以下信息，最后只输出 JSON，不要省略字段。

查询：{search_query}

如果某字段找不到，请使用"未知"或合理的空数组，不要编造具体事实。"""

        # 先保留 Kimi 原始文本，再做本地解析，便于异常时定位模型幻觉输出。
        response = client._chat_with_web_search(
            messages=[
                {"role": "system", "content": "你是专业的用户研究分析师，擅长搜索和整理用户画像数据。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
        )

        profile_data = client.extract_json(response, expected_type=dict)
        audience_profile = _build_audience_profile(profile_data)
        
        return AudienceProfileOutput(audience_profile=audience_profile)
        
    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"audience_profile_node: 观众画像搜索或 JSON 解析失败: {e}"
        logger.error("%s, 原始模型文本为: %s", error_message, response, exc_info=True)
        return AudienceProfileOutput(
            audience_profile=_default_audience_profile(),
            error_message=error_message + "\n"
        )
