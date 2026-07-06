"""
行业数据节点 - 获取行业宏观数据

策略：
1. 行业宏观数据以自然月为粒度缓存，月初/缓存缺失时使用 Kimi 联网搜索最新行业报告。
2. 日常运行直接读取缓存，不重复调用 API。
3. 方向 A：搜索失败或字段缺失时留空（不再返回固定默认值），并在 data_source 中标注来源。
"""
import os
import json
import re
import logging
from datetime import datetime
from typing import Any, Dict
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.moonshot_api import MoonshotClient

# Fallback for test_run environment
try:
    from tools.moonshot_api import is_api_budget_error
except ImportError:
    def is_api_budget_error(exc: Exception) -> bool:
        return str(exc) == "API \u8c03\u7528\u6b21\u6570\u8fc7\u591a\uff0c\u5df2\u718f\u65ad"

from tools.industry_cache import load_cache, save_cache, load_seed
from graphs.state import (
    IndustryNodeInput,
    IndustryNodeOutput,
    IndustryData,
    PlatformData,
    PlatformApp
)

logger = logging.getLogger(__name__)


def _safe_int(value: Any, default: int, min_value: int = 0, max_value: int | None = None) -> int:
    """Normalize numeric LLM output before Pydantic validation."""
    try:
        if isinstance(value, bool):
            number = default
        elif isinstance(value, (int, float)):
            number = int(round(value))
        elif isinstance(value, str):
            cleaned = value.strip().replace(",", "").replace("%", "")
            if not cleaned or cleaned in {"未知", "无", "暂无", "N/A", "n/a", "null", "None", "-"}:
                number = default
            else:
                range_match = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:-|~|至|到)\s*(-?\d+(?:\.\d+)?)", cleaned)
                if range_match:
                    first, second = float(range_match.group(1)), float(range_match.group(2))
                    number = int(round((first + second) / 2))
                else:
                    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
                    number = int(round(float(match.group()))) if match else default
        else:
            number = default

        number = max(min_value, number)
        if max_value is not None:
            number = min(max_value, number)
        return number
    except Exception:
        return default


def _safe_ratio(value: Any, default: int) -> int:
    return _safe_int(value, default, min_value=0, max_value=100)


def _safe_float(value: Any, default: float) -> float:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
            return float(match.group()) if match else default
        return default
    except Exception:
        return default


# 被 LLM 返回的占位/无效值集合，遇到时视为缺失
_PLACEHOLDER_VALUES = {
    "未知", "暂无", "无", "N/A", "n/a", "null", "None", "-", "—", "未提供",
    "not found", "not available", "unknown", "none",
}


def _is_meaningful_text(value: Any) -> bool:
    """判断文本字段是否为有效值（非空且非占位符）"""
    if value is None:
        return False
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    return bool(stripped) and stripped not in _PLACEHOLDER_VALUES


def _safe_text(value: Any, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in _PLACEHOLDER_VALUES:
            return default
        return stripped if stripped else default
    return str(value)


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


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
            logger.warning("industry_node: 读取 LLM 配置失败: %s", e)

    return {}


def _build_search_prompts(date_str: str, cfg: Dict[str, Any], generic: bool = False) -> tuple[str, str]:
    """构建 AI 渗透率和行业宏观数据搜索 prompt

    Args:
        generic: 为 True 时不限定具体年月，搜索最新/最近公布的行业数据。
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        year, month = dt.year, dt.month
    except ValueError:
        now = datetime.now()
        year, month = now.year, now.month

    sp = cfg.get(
        "sp",
        "你是短剧行业数据分析师，擅长搜索行业报告和统计数据。你必须联网搜索，优先使用有具体数字的权威来源。",
    )
    up_template = cfg.get("up", "")

    if generic:
        ai_query = """请联网搜索 国内短剧行业AI短剧占比 最新公开数据。
请返回JSON格式，包含以下字段：
- ai_ratio: AI短剧占比百分比，如25
- ai_drama_count: AI短剧数量（可选）
- ai_trend: 趋势，值为"上升"、"持平"或"下降"（可选）

如果找不到确切数据，请返回空字符串或省略字段，不要编造具体数字。"""

        macro_query = """请联网搜索 国内短剧行业 最新宏观数据，包括：
1. APP月活用户数（红果、抖音等）
2. 短剧数量（总剧目数）
3. 亿元播放量短剧数量
4. 主要平台的月活用户数和同比增长
5. 用户规模、市场规模

请返回JSON格式。如果某字段找不到，请使用空字符串或省略字段，不要编造具体数字。"""
    else:
        ai_query = f"""请联网搜索 {year}年{month}月 短剧行业AI短剧占比最新数据。
请返回JSON格式，包含以下字段：
- ai_ratio: AI短剧占比百分比，如25
- ai_drama_count: AI短剧数量（可选）
- ai_trend: 趋势，值为"上升"、"持平"或"下降"（可选）

如果找不到确切数据，请返回空字符串或省略字段，不要编造具体数字。"""

        macro_query = f"""请联网搜索 {year}年{month}月 国内短剧行业宏观数据，包括：
1. APP月活用户数（红果、抖音等）
2. 短剧数量（总剧目数）
3. 亿元播放量短剧数量
4. 主要平台的月活用户数和同比增长
5. 用户规模、市场规模

请返回JSON格式。如果某字段找不到，请使用空字符串或省略字段，不要编造具体数字。"""

    if up_template and not generic:
        try:
            macro_query = Template(up_template).render(year=year, month=month, date=date_str)
        except Exception as e:
            logger.warning("industry_node: Jinja2 渲染 prompt 失败，使用内置 prompt: %s", e)

    return sp, ai_query, macro_query


def _search_industry_data(
    client: MoonshotClient, date_str: str, cfg: Dict[str, Any], generic: bool = False
) -> Dict[str, Any]:
    """使用 Kimi 搜索行业宏观数据"""
    sp, ai_query, macro_query = _build_search_prompts(date_str, cfg, generic=generic)
    config_model = cfg.get("config", {})
    temperature = float(config_model.get("temperature", 0.2))
    max_tokens = int(config_model.get("max_completion_tokens", 3000) or 3000)

    # 第一轮搜索：AI 短剧渗透率
    ai_data: Dict[str, Any] = {}
    try:
        ai_data = client.search_json(
            query=ai_query,
            system_prompt=sp,
            temperature=temperature,
            max_tokens=1000,
            expected_type=dict
        )
        if not isinstance(ai_data, dict):
            ai_data = {}
        logger.info("AI短剧渗透率搜索结果: %s", ai_data)
    except Exception as e:
        logger.warning("AI短剧渗透率搜索失败: %s", e)
        ai_data = {}

    # 第二轮搜索：其他行业宏观数据
    data: Dict[str, Any] = {}
    try:
        data = client.search_json(
            query=macro_query,
            system_prompt=sp,
            temperature=temperature,
            max_tokens=max_tokens,
            expected_type=dict
        )
        if not isinstance(data, dict):
            data = {}
    except Exception as e:
        logger.warning("行业宏观数据搜索失败: %s", e)
        if is_api_budget_error(e):
            raise
        data = {}

    # 合并 AI 数据
    if ai_data.get("ai_ratio") not in (None, ""):
        data["ai_ratio"] = ai_data.get("ai_ratio")

    return data


def _parse_platform_apps(data: Dict[str, Any]) -> list:
    """解析平台 APP 数据"""
    platform_apps = _first_present(data, ("platform_apps", "top_mau", "apps"))
    if not isinstance(platform_apps, list):
        return []

    apps = []
    for app_data in platform_apps:
        if not isinstance(app_data, dict):
            continue
        app = PlatformApp(
            name=_safe_text(_first_present(app_data, ("name", "app", "platform")), ""),
            mau=_safe_float(app_data.get("mau"), 0.0),
            mau_unit=_safe_text(_first_present(app_data, ("mau_unit", "unit")), "亿"),
            yoy=_safe_text(app_data.get("yoy"), ""),
            share=_safe_ratio(app_data.get("share"), 0),
            trend=_safe_text(app_data.get("trend"), "same")
        )
        apps.append(app)
    return apps


def _build_empty_industry() -> IndustryData:
    """构建空的行业数据（方向 A：缺失时留空）"""
    return IndustryData(
        user_scale="",
        market_size="",
        drama_count="",
        billion_dramas=0,
        ai_ratio=0,
        female_ratio=0,
        male_ratio=0,
        app_mau="",
        app_mau_yoy="",
        data_source="行业数据获取失败，暂无真实来源",
        update_frequency="monthly",
    )


def _has_valid_industry_data(industry: IndustryData) -> bool:
    """判断行业数据是否包含质量门禁要求的关键字段"""
    if not industry:
        return False
    return _is_meaningful_text(getattr(industry, "app_mau", "")) and _is_meaningful_text(
        getattr(industry, "drama_count", "")
    )


def _build_empty_platform() -> PlatformData:
    """构建空的平台数据"""
    return PlatformData(
        apps=[],
        mini_programs=[],
        data_source="行业数据获取失败，暂无真实来源",
        update_frequency="monthly",
    )


def _get_previous_month_date(date_str: str) -> str:
    """返回 date_str 所在月份的上个月第一天，格式 YYYY-MM-DD"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        dt = datetime.now()
    year, month = dt.year, dt.month
    if month == 1:
        year -= 1
        month = 12
    else:
        month -= 1
    return f"{year}-{month:02d}-01"


def _extract_industry_and_platform(
    data: Dict[str, Any],
    data_date: str,
    ai_count: int,
    female_count: int,
    male_count: int,
    ranking_total: int,
    source_note_prefix: str = "",
) -> tuple[IndustryData, PlatformData]:
    """将 Kimi 返回的原始数据解析为 IndustryData + PlatformData"""
    source_title = str(data.get("source_title", "") or "Kimi 搜索行业报告").strip()
    source_note = f"{source_note_prefix}{source_title}".strip("；")

    ai_ratio = _safe_ratio(data.get("ai_ratio"), 0)
    female_ratio = _safe_ratio(data.get("female_ratio"), 0)
    male_ratio = _safe_ratio(data.get("male_ratio"), 0)

    # 如果搜索未返回性别比例，可用榜单统计作为参考，但标注来源
    if ("female_ratio" not in data or data.get("female_ratio") in (None, "")) and ranking_total > 0:
        female_ratio = int(female_count / ranking_total * 100)
        male_ratio = int(male_count / ranking_total * 100)
        source_note = f"{source_note}；性别比例来自当日榜单统计"

    industry = IndustryData(
        user_scale=_safe_text(_first_present(data, ("user_scale", "userScale")), ""),
        market_size=_safe_text(_first_present(data, ("market_size", "marketSize")), ""),
        drama_count=_safe_text(_first_present(data, ("drama_count", "total_dramas", "drama_total")), ""),
        billion_dramas=_safe_int(_first_present(data, ("billion_dramas", "billionDramaCount")), 0),
        ai_ratio=ai_ratio,
        female_ratio=female_ratio,
        male_ratio=male_ratio,
        app_mau=_safe_text(_first_present(data, ("app_mau", "appMau")), ""),
        app_mau_yoy=_safe_text(_first_present(data, ("app_mau_yoy", "appMauYoy")), ""),
        data_source=source_note,
        update_frequency="monthly",
    )

    apps = _parse_platform_apps(data)
    mini_programs = data.get("mini_programs", [])
    if not isinstance(mini_programs, list):
        mini_programs = []

    platform = PlatformData(
        apps=apps,
        mini_programs=mini_programs,
        data_source=source_note,
        update_frequency="monthly",
    )

    return industry, platform


def _build_fallback_industry(
    ai_count: int,
    female_count: int,
    male_count: int,
    ranking_total: int,
) -> IndustryData:
    """使用榜单统计构建兜底行业数据"""
    fallback_female_ratio = int(female_count / ranking_total * 100) if ranking_total > 0 else 0
    fallback_male_ratio = int(male_count / ranking_total * 100) if ranking_total > 0 else 0
    fallback_ai_ratio = int(ai_count / ranking_total * 100) if ranking_total > 0 else 0
    return IndustryData(
        user_scale="",
        market_size="",
        drama_count="暂无公开月报数据",
        billion_dramas=0,
        ai_ratio=fallback_ai_ratio,
        female_ratio=fallback_female_ratio,
        male_ratio=fallback_male_ratio,
        app_mau="暂无公开月报数据",
        app_mau_yoy="",
        data_source="连续两月未获取到公开行业月报；性别/AI占比来自当日榜单统计",
        update_frequency="monthly",
    )


def _has_valid_search_data(data: Dict[str, Any]) -> bool:
    """判断搜索返回的数据是否包含关键字段"""
    return (
        _is_meaningful_text(data.get("app_mau"))
        and _is_meaningful_text(data.get("drama_count"))
    )


def industry_node(state: IndustryNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> IndustryNodeOutput:
    """
    title: 行业数据获取
    desc: 使用 Kimi 联网搜索获取最新的行业宏观数据；当月数据缺失时回退到上月；仍缺失时用榜单统计兜底
    integrations: Moonshot API（每月最多 2-3 次）
    """
    try:
        data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")

        # 1. 尝试读取当月月度缓存
        cache = load_cache(today=data_date)
        if cache:
            industry_dict = cache.get("industry", {}) or {}
            platform_dict = cache.get("platform", {}) or {}
            industry_dict.setdefault("update_frequency", "monthly")
            platform_dict.setdefault("update_frequency", "monthly")
            industry = IndustryData(**industry_dict)
            platform = PlatformData(**platform_dict)
            if _has_valid_industry_data(industry):
                return IndustryNodeOutput(
                    industry=industry,
                    platform=platform,
                    success=True,
                    error_message="",
                )
            logger.warning(
                "industry_node: 本月缓存关键字段缺失（app_mau=%s, drama_count=%s），重新搜索",
                getattr(industry, "app_mau", ""),
                getattr(industry, "drama_count", ""),
            )

        # 2. 统计榜单中的 AI/女男频比例（作为参考，不强制覆盖搜索数据）
        ai_count = sum(1 for r in state.enriched_rankings if r.is_ai)
        female_count = sum(1 for r in state.enriched_rankings if r.category == "female")
        male_count = sum(1 for r in state.enriched_rankings if r.category == "male")
        ranking_total = len(state.enriched_rankings)

        # 3. 读取配置
        cfg = _load_llm_cfg(config)
        client = MoonshotClient()

        # 4. 先搜索当月数据
        try:
            data = _search_industry_data(client, data_date, cfg)
        except Exception as e:
            if is_api_budget_error(e):
                raise
            logger.error("industry_node: 当月行业数据搜索失败: %s", e)
            data = {}

        # 5. 当月数据有效：直接解析使用
        if _has_valid_search_data(data):
            industry, platform = _extract_industry_and_platform(
                data, data_date, ai_count, female_count, male_count, ranking_total
            )
            save_cache(
                industry=industry.model_dump(),
                platform=platform.model_dump(),
                today=data_date,
            )
            return IndustryNodeOutput(
                industry=industry,
                platform=platform,
                success=True,
                error_message="",
            )

        # 6. 当月数据无效：尝试回退到上个月
        logger.warning("industry_node: 当月行业数据关键字段缺失，尝试回退到上月")
        last_month_date = _get_previous_month_date(data_date)

        last_month_cache = load_cache(today=last_month_date)
        if last_month_cache:
            industry_dict = last_month_cache.get("industry", {}) or {}
            platform_dict = last_month_cache.get("platform", {}) or {}
            industry_dict.setdefault("update_frequency", "monthly")
            platform_dict.setdefault("update_frequency", "monthly")
            industry = IndustryData(**industry_dict)
            platform = PlatformData(**platform_dict)
            if _has_valid_industry_data(industry):
                logger.info("industry_node: 使用上月缓存行业数据")
                # 保存到当月缓存，避免后续每日重复搜索
                save_cache(
                    industry=industry.model_dump(),
                    platform=platform.model_dump(),
                    today=data_date,
                )
                return IndustryNodeOutput(
                    industry=industry,
                    platform=platform,
                    success=True,
                    error_message="",
                )

        try:
            last_month_data = _search_industry_data(client, last_month_date, cfg)
        except Exception as e:
            if is_api_budget_error(e):
                raise
            logger.error("industry_node: 上月行业数据搜索失败: %s", e)
            last_month_data = {}

        if _has_valid_search_data(last_month_data):
            logger.info("industry_node: 使用上月搜索结果作为当月数据")
            industry, platform = _extract_industry_and_platform(
                last_month_data,
                data_date,
                ai_count,
                female_count,
                male_count,
                ranking_total,
                source_note_prefix="当月月报尚未发布，使用上月月报；",
            )
            save_cache(
                industry=industry.model_dump(),
                platform=platform.model_dump(),
                today=data_date,
            )
            return IndustryNodeOutput(
                industry=industry,
                platform=platform,
                success=True,
                error_message="",
            )

        # 7. 当月和上月都无效：尝试不限定年月的通用搜索
        logger.warning("industry_node: 连续两月行业数据均缺失，尝试不限定年月的通用搜索")
        try:
            generic_data = _search_industry_data(client, data_date, cfg, generic=True)
        except Exception as e:
            if is_api_budget_error(e):
                raise
            logger.error("industry_node: 通用行业数据搜索失败: %s", e)
            generic_data = {}

        if _has_valid_search_data(generic_data):
            logger.info("industry_node: 使用通用搜索结果作为当月数据")
            industry, platform = _extract_industry_and_platform(
                generic_data,
                data_date,
                ai_count,
                female_count,
                male_count,
                ranking_total,
                source_note_prefix="当月/上月月报未发布，使用最新公开行业数据；",
            )
            save_cache(
                industry=industry.model_dump(),
                platform=platform.model_dump(),
                today=data_date,
            )
            return IndustryNodeOutput(
                industry=industry,
                platform=platform,
                success=True,
                error_message="",
            )

        # 8. 所有搜索均无效：尝试种子数据，再使用榜单统计兜底
        seed = load_seed()
        if seed:
            industry_dict = seed.get("industry", {}) or {}
            platform_dict = seed.get("platform", {}) or {}
            industry_dict.setdefault("update_frequency", "monthly")
            platform_dict.setdefault("update_frequency", "monthly")
            industry = IndustryData(**industry_dict)
            platform = PlatformData(**platform_dict)
            if _has_valid_industry_data(industry):
                logger.info("industry_node: 使用 config/industry_seed.json 种子数据")
                save_cache(
                    industry=industry.model_dump(),
                    platform=platform.model_dump(),
                    today=data_date,
                )
                return IndustryNodeOutput(
                    industry=industry,
                    platform=platform,
                    success=True,
                    error_message="industry_node: Kimi 搜索未获取有效数据，已使用行业种子数据\n",
                )

        logger.warning("industry_node: 所有搜索均未获取到有效行业数据，使用榜单统计兜底")
        industry = _build_fallback_industry(ai_count, female_count, male_count, ranking_total)
        return IndustryNodeOutput(
            industry=industry,
            platform=_build_empty_platform(),
            success=True,
            error_message="industry_node: 当月、上月及通用搜索均未获取到有效行业数据，已使用榜单统计兜底\n",
        )

        source_title = str(data.get("source_title", "") or "Kimi 搜索行业报告").strip()
        # data_source 是“来源说明”，不应把完整 URL 拼进来（尤其企查查等搜索 URL 非常长，
        # 会撑破前端 KPI 卡片布局）。URL 如需展示可单独放到 source_url，但当前模型未启用。
        source_note = source_title

        ai_ratio = _safe_ratio(data.get("ai_ratio"), 0)
        female_ratio = _safe_ratio(data.get("female_ratio"), 0)
        male_ratio = _safe_ratio(data.get("male_ratio"), 0)

        # 如果搜索未返回性别比例，可用榜单统计作为参考，但标注来源
        if ("female_ratio" not in data or data.get("female_ratio") in (None, "")) and ranking_total > 0:
            female_ratio = int(female_count / ranking_total * 100)
            male_ratio = int(male_count / ranking_total * 100)
            source_note = f"{source_note}；性别比例来自当日榜单统计"

        industry = IndustryData(
            user_scale=_safe_text(_first_present(data, ("user_scale", "userScale")), ""),
            market_size=_safe_text(_first_present(data, ("market_size", "marketSize")), ""),
            drama_count=_safe_text(_first_present(data, ("drama_count", "total_dramas", "drama_total")), ""),
            billion_dramas=_safe_int(_first_present(data, ("billion_dramas", "billionDramaCount")), 0),
            ai_ratio=ai_ratio,
            female_ratio=female_ratio,
            male_ratio=male_ratio,
            app_mau=_safe_text(_first_present(data, ("app_mau", "appMau")), ""),
            app_mau_yoy=_safe_text(_first_present(data, ("app_mau_yoy", "appMauYoy")), ""),
            data_source=source_note,
            update_frequency="monthly",
        )

        # 5. 解析平台数据
        apps = _parse_platform_apps(data)
        mini_programs = data.get("mini_programs", [])
        if not isinstance(mini_programs, list):
            mini_programs = []

        platform = PlatformData(
            apps=apps,
            mini_programs=mini_programs,
            data_source=source_note,
            update_frequency="monthly",
        )

        # 6. 保存月度缓存（仅当关键字段有效时才缓存，避免把空结果锁死一个月）
        if _has_valid_industry_data(industry):
            save_cache(
                industry=industry.model_dump(),
                platform=platform.model_dump(),
                today=data_date,
            )
        else:
            logger.warning("industry_node: 搜索返回的行业数据关键字段缺失，不写入月度缓存")

        return IndustryNodeOutput(
            industry=industry,
            platform=platform,
            success=True,
            error_message="",
        )

    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"industry_node: 行业数据搜索或 JSON 解析失败: {e}"
        logger.error(error_message, exc_info=True)
        return IndustryNodeOutput(
            industry=_build_empty_industry(),
            platform=_build_empty_platform(),
            success=True,
            error_message=error_message + "\n",
        )
