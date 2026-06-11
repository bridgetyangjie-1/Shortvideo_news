"""
观众画像节点 - 基于当日榜单动态反推核心受众画像
"""
import json
import logging
import re
from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.deepseek_api import DeepSeekClient

from graphs.state import (
    AudienceProfile,
    AudienceProfileInput,
    AudienceProfileOutput,
)

logger = logging.getLogger(__name__)


DEFAULT_TRAITS = [
    "偏好强反转高密度剧情",
    "关注女性逆袭与情绪补偿",
    "习惯通勤睡前碎片化追更",
    "对复仇打脸和身份揭晓爽点敏感",
]

DEFAULT_GENDER = {"female": 78, "male": 22}
DEFAULT_AGE = {"18-24": 22, "25-34": 43, "35-44": 25, "45+": 10}
DEFAULT_REGIONS = [
    {"name": "广东", "value": 15.5},
    {"name": "江苏", "value": 11.8},
    {"name": "浙江", "value": 9.6},
    {"name": "山东", "value": 8.4},
]


def _default_regions() -> List[Dict[str, Any]]:
    return [region.copy() for region in DEFAULT_REGIONS]


def _default_audience_profile() -> AudienceProfile:
    return AudienceProfile(
        gender=DEFAULT_GENDER.copy(),
        age=DEFAULT_AGE.copy(),
        regions=_default_regions(),
        traits=DEFAULT_TRAITS.copy(),
    )


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_number(value: Any, default: Any) -> Any:
    try:
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
        return round(number, 1)
    except Exception:
        return default


def _safe_text(value: Any, default: str) -> str:
    try:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default
    except Exception:
        return default


def _safe_traits(value: Any) -> List[str]:
    try:
        if not isinstance(value, list):
            return DEFAULT_TRAITS.copy()

        traits = []
        for item in value:
            if isinstance(item, str) and item.strip():
                traits.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("name") or item.get("label") or item.get("trait")
                if isinstance(text, str) and text.strip():
                    traits.append(text.strip())

        for default_trait in DEFAULT_TRAITS:
            if len(traits) >= 4:
                break
            if default_trait not in traits:
                traits.append(default_trait)

        return traits[:4]
    except Exception:
        return DEFAULT_TRAITS.copy()


def _extract_region_value(region: Dict[str, Any]) -> Any:
    try:
        for key in ("value", "占比", "ratio", "percent", "percentage"):
            if key in region:
                return region.get(key)
        return 0.0
    except Exception:
        return 0.0


def _build_top_regions(raw_regions: Any) -> List[Dict[str, Any]]:
    try:
        if not isinstance(raw_regions, list):
            return _default_regions()

        top_regions: List[Dict[str, Any]] = []
        for region in raw_regions[:5]:
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
            top_regions.append({"name": name, "value": value})

        return top_regions or _default_regions()
    except Exception:
        return _default_regions()


def _extract_json_from_response(response: Any) -> Dict[str, Any]:
    try:
        if isinstance(response, dict):
            return response

        text = str(response or "").strip()
        if not text:
            return {}

        fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        if fenced_match:
            text = fenced_match.group(1).strip()
        else:
            json_match = re.search(r"\{.*\}", text, re.S)
            if json_match:
                text = json_match.group(0).strip()

        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        logger.error(
            "audience_profile_node: DeepSeek JSON解析失败: %s, 原始响应: %s",
            exc,
            response,
            exc_info=True,
        )
        return {}


def _get_field(item: Dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        try:
            if name in item:
                return item.get(name)
        except Exception:
            continue
    return default


def _ranking_to_dict(item: Any) -> Dict[str, Any]:
    try:
        if isinstance(item, dict):
            return item
        if hasattr(item, "model_dump"):
            dumped = item.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        if hasattr(item, "dict"):
            dumped = item.dict()
            return dumped if isinstance(dumped, dict) else {}
    except Exception:
        return {}
    return {}


def _format_list(value: Any, default: str) -> str:
    try:
        if isinstance(value, list):
            text = "、".join(str(item).strip() for item in value if str(item).strip())
            return text or default
        return _safe_text(value, default)
    except Exception:
        return default


def _build_rankings_context(state: AudienceProfileInput) -> str:
    try:
        rankings = getattr(state, "enriched_rankings", None) or []
        if not isinstance(rankings, list):
            return "今日榜单数据为空，请基于短剧行业常见爆款结构给出稳健推断。"

        lines = []
        for idx, raw_item in enumerate(rankings[:10], start=1):
            item = _ranking_to_dict(raw_item)
            title = _safe_text(
                _get_field(item, "title", "name", "drama_name", "剧名", default=""),
                f"短剧{idx}",
            )
            genre = _safe_text(
                _get_field(item, "genre", "category", "题材", default=""),
                "题材未知",
            )
            tags_text = _format_list(
                _get_field(item, "core_trope", "tags", "爽点", "hot_tags", default=[]),
                "暂无标签",
            )
            female_lead = _safe_text(
                _get_field(item, "female_lead", "女主", "女演员", default=""),
                "",
            )
            male_lead = _safe_text(
                _get_field(item, "male_lead", "男主", "男演员", default=""),
                "",
            )
            actors_text = _format_list(
                _get_field(item, "actors", "主演", default=[]),
                "暂无主演信息",
            )
            if female_lead or male_lead:
                actors_text = f"{female_lead or '女主待补'} / {male_lead or '男主待补'}"

            lines.append(
                f"{idx}. 《{title}》｜题材：{genre}｜爽点/标签：{tags_text}｜主演：{actors_text}"
            )

        return "\n".join(lines) if lines else "今日榜单数据为空，请基于短剧行业常见爆款结构给出稳健推断。"
    except Exception as exc:
        logger.error("audience_profile_node: 构建榜单上下文失败: %s", exc, exc_info=True)
        return "今日榜单数据解析失败，请基于短剧行业常见爆款结构给出稳健推断。"


def _build_prompt(rankings_context: str) -> str:
    return f"""你是资深短剧行业分析师。下面是今日最火的10部短剧及其题材、爽点和主演信息。
请不要联网搜索，不要输出宏观空话。请只基于这批具体剧目的题材结构、情绪爽点、人物关系和消费场景，反推出今日榜单的核心受众画像。

【今日榜单】
{rankings_context}

【输出要求】
只输出严格 JSON，不要 Markdown，不要解释，不要额外文本。
字段必须完整：
{{
  "gender": {{
    "male": 数字,
    "female": 数字
  }},
  "age": {{
    "18-24": 数字,
    "25-34": 数字,
    "35-44": 数字,
    "45+": 数字
  }},
  "regions": [
    {{"name": "广东", "value": 15.5}},
    {{"name": "江苏", "value": 11.8}},
    {{"name": "浙江", "value": 9.6}}
  ],
  "traits": [
    "4个非常具体且符合今日剧目的受众行为标签"
  ]
}}

【硬性规则】
1. gender 中 male + female 约等于 100。
2. age 四项总和约等于 100。
3. regions 返回 3-5 个排名前列的省份或城市，value 为数字百分比。
4. traits 必须正好 4 个，必须具体到今日榜单的题材爽点和观看行为，禁止使用“下沉市场”“年轻群体”“女性主导”等泛泛标签。
"""


def _build_gender(raw_gender: Any) -> Dict[str, float]:
    try:
        gender = _as_dict(raw_gender)
        female = float(_safe_number(gender.get("female"), DEFAULT_GENDER["female"]))
        male = float(_safe_number(gender.get("male"), DEFAULT_GENDER["male"]))
        if female <= 0 and male <= 0:
            return DEFAULT_GENDER.copy()
        return {"female": female, "male": male}
    except Exception:
        return DEFAULT_GENDER.copy()


def _build_age(raw_age: Any) -> Dict[str, float]:
    try:
        age = _as_dict(raw_age)
        result = {
            "18-24": float(_safe_number(age.get("18-24"), DEFAULT_AGE["18-24"])),
            "25-34": float(_safe_number(age.get("25-34"), DEFAULT_AGE["25-34"])),
            "35-44": float(_safe_number(age.get("35-44"), DEFAULT_AGE["35-44"])),
            "45+": float(_safe_number(age.get("45+"), DEFAULT_AGE["45+"])),
        }
        if sum(result.values()) <= 0:
            return DEFAULT_AGE.copy()
        return result
    except Exception:
        return DEFAULT_AGE.copy()


def _build_audience_profile(profile_data: Any) -> AudienceProfile:
    try:
        safe_profile = _as_dict(profile_data)
        if not safe_profile:
            return _default_audience_profile()

        return AudienceProfile(
            gender=_build_gender(safe_profile.get("gender")),
            age=_build_age(safe_profile.get("age")),
            regions=_build_top_regions(safe_profile.get("regions")),
            traits=_safe_traits(safe_profile.get("traits")),
        )
    except Exception as exc:
        logger.error("audience_profile_node: 构建观众画像对象失败: %s", exc, exc_info=True)
        return _default_audience_profile()


def audience_profile_node(
    state: AudienceProfileInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> AudienceProfileOutput:
    """
    title: 📊 获取观众画像数据
    desc: 使用 DeepSeek 基于当日榜单题材爽点动态反推核心受众画像
    integrations: DeepSeek API
    """
    response = ""

    try:
        rankings_context = _build_rankings_context(state)
        prompt = _build_prompt(rankings_context)

        client = DeepSeekClient()
        response = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是资深短剧行业分析师，擅长根据当日爆款内容结构反推受众画像，并严格输出 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
        )

        profile_data = _extract_json_from_response(response)
        audience_profile = _build_audience_profile(profile_data)

        return AudienceProfileOutput(audience_profile=audience_profile)

    except Exception as exc:
        error_message = f"audience_profile_node: DeepSeek 受众画像推理失败，已使用默认画像兜底: {exc}"
        logger.error("%s, 原始模型文本为: %s", error_message, response, exc_info=True)
        return AudienceProfileOutput(
            audience_profile=_default_audience_profile(),
            error_message=error_message + "\n",
        )
