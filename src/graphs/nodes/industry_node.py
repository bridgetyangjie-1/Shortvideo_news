"""
行业数据节点 - 获取行业宏观数据
"""
import os
import json
import re
import logging
from datetime import datetime
from typing import Any
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

from graphs.state import (
    IndustryNodeInput,
    IndustryNodeOutput,
    IndustryData,
    PlatformData,
    PlatformApp
)

CACHE_FILE = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "."), "assets", "industry_cache.json")

# 初始化日志
logger = logging.getLogger(__name__)


def _safe_int(value: Any, default: int, min_value: int = 0, max_value: int | None = None) -> int:
    """Normalize numeric LLM output before Pydantic validation."""
    try:
        if isinstance(value, bool):
            number = default
        elif isinstance(value, (int, float)):
            number = int(round(value))
        elif isinstance(value, str):
            cleaned = value.strip().replace(",", "")
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


def _safe_text(value: Any, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else default
    return str(value)


def _first_present(data: dict[str, Any], keys: tuple[str, ...], default: Any) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def industry_node(state: IndustryNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> IndustryNodeOutput:
    """
    title: 行业数据获取
    desc: 使用 Kimi 联网搜索获取最新的行业宏观数据（用户规模、市场规模、AI短剧占比等）
    integrations: Moonshot API
    """
    ctx = runtime.context
    
    try:
        date_str = state.data_date or datetime.now().strftime("%Y-%m-%d")
        try:
            current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            date_str = datetime.now().strftime("%Y-%m-%d")
            current_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as fd:
                    cache_data = json.load(fd)

                last_updated = cache_data.get("last_updated")
                industry_data = cache_data.get("industry")
                platform_data = cache_data.get("platform")
                if last_updated and isinstance(industry_data, dict) and isinstance(platform_data, dict):
                    cached_date = datetime.strptime(last_updated, "%Y-%m-%d").date()
                    if abs((current_date - cached_date).days) < 7:
                        logger.info("命中7天长效缓存，跳过大模型调用")
                        return IndustryNodeOutput(
                            industry=IndustryData(**industry_data),
                            platform=PlatformData(**platform_data),
                            success=True,
                            error_message=""
                        )
        except Exception as cache_exc:
            logger.warning(f"industry_node: 读取7天长效缓存失败，将重新调用大模型: {cache_exc}")

        input_error_message = ""
        if not state.enriched_rankings:
            input_error_message = "industry_node: enriched_rankings 为空，AI/女频比例只能使用默认或搜索兜底；请检查 enrich_node。\n"
            logger.error(input_error_message.strip())

        # 1. 统计榜单中的AI剧和女男频比例
        ai_count = sum(1 for r in state.enriched_rankings if r.is_ai)
        female_count = sum(1 for r in state.enriched_rankings if r.category == "female")
        male_count = sum(1 for r in state.enriched_rankings if r.category == "male")
        ranking_total = len(state.enriched_rankings)
        total = ranking_total if ranking_total else 1
        default_ai_ratio = int(ai_count / total * 100) if ranking_total else 38
        default_female_ratio = int(female_count / total * 100) if ranking_total else 95
        default_male_ratio = int(male_count / total * 100) if ranking_total else 5
        
        # 2. 读取LLM配置
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.2)
        
        # 3. 使用 Kimi 联网搜索行业数据（v1.7.11: 优化AI短剧渗透率搜索）
        client = MoonshotClient()
        
        # 第一轮搜索：AI短剧渗透率专项搜索
        ai_search_query = f"""请联网搜索短剧行业AI短剧占比最新数据。
参考日期：{date_str}

搜索关键词建议：
- "短剧行业 AI短剧占比 {date_str}"
- "短剧 AI生成 比例 趋势"
- "AI短剧 市场份额 数据"

请返回JSON格式，包含以下字段：
- ai_ratio: AI短剧占比百分比，如25
- ai_drama_count: AI短剧数量
- ai_trend: 趋势，值为"上升"、"持平"或"下降"

如果找不到确切数据，请根据行业趋势估算（建议15-25%）。
"""
        
        ai_data = {}
        try:
            ai_data = client.search_json(
                query=ai_search_query,
                system_prompt="你是短剧行业数据分析师，擅长搜索行业报告和统计数据。",
                temperature=0.2,
                max_tokens=1000,
                expected_type=dict
            )
            logger.info(f"AI短剧渗透率搜索结果: {ai_data}")
            if not isinstance(ai_data, dict):
                ai_data = {}
        except Exception as e:
            logger.warning(f"AI短剧渗透率搜索失败: {e}")
            ai_data = {}
        
        # 第二轮搜索：其他行业宏观数据
        search_query = f"""请搜索互联网，获取最新的短剧行业宏观数据，包括：
1. APP月活用户数（红果、抖音等）
2. 短剧数量（总剧目数）
3. 亿元播放量短剧数量
4. 主要平台的月活用户数和同比增长

参考日期：{date_str}

请返回JSON格式的数据。
"""
        
        # 执行 Kimi 官方 $web_search 并解析 JSON
        data = client.search_json(
            query=search_query,
            system_prompt=sp or "你是专业的行业数据分析师，擅长搜索和整理行业宏观统计数据。",
            temperature=temperature,
            max_tokens=3000,
            expected_type=dict
        )
        if not isinstance(data, dict):
            data = {}
        
        # 合并AI短剧数据（优先使用专项搜索结果）
        if ai_data.get("ai_ratio"):
            data["ai_ratio"] = ai_data.get("ai_ratio")

        ai_ratio = _safe_ratio(data.get("ai_ratio"), default_ai_ratio)
        female_ratio = _safe_ratio(data.get("female_ratio"), default_female_ratio)
        male_ratio = _safe_ratio(data.get("male_ratio"), default_male_ratio)
        if "male_ratio" not in data and female_ratio != default_female_ratio:
            male_ratio = max(0, 100 - female_ratio)
        elif "female_ratio" not in data and male_ratio != default_male_ratio:
            female_ratio = max(0, 100 - male_ratio)
        
        # 5. 构建行业数据（使用搜索结果或榜单统计）
        industry = IndustryData(
            user_scale=_first_present(data, ("user_scale", "userScale"), "7.18亿"),
            market_size=_first_present(data, ("market_size", "marketSize"), "1000亿+"),
            drama_count=_safe_text(_first_present(data, ("drama_count", "total_dramas", "drama_total"), "25万+"), "25万+"),
            billion_dramas=_safe_int(_first_present(data, ("billion_dramas", "billionDramaCount"), 20), 20),
            ai_ratio=ai_ratio,
            female_ratio=female_ratio,
            male_ratio=male_ratio,
            app_mau=_safe_text(_first_present(data, ("app_mau", "appMau"), "3.04亿"), "3.04亿"),
            app_mau_yoy=_safe_text(_first_present(data, ("app_mau_yoy", "appMauYoy"), "+1.4亿"), "+1.4亿")
        )
        
        # 6. 构建平台数据
        apps = []
        platform_apps = _first_present(data, ("platform_apps", "top_mau", "apps"), [])
        if not isinstance(platform_apps, list):
            platform_apps = []
        for app_data in platform_apps or [{"name": "红果免费短剧", "mau": 3.04, "mau_unit": "亿", "yoy": "+1.4亿", "share": 85, "trend": "up"}]:
            if not isinstance(app_data, dict):
                continue
            app = PlatformApp(
                name=_safe_text(_first_present(app_data, ("name", "app", "platform"), "红果免费短剧"), "红果免费短剧"),
                mau=_safe_float(app_data.get("mau"), 3.04),
                mau_unit=_safe_text(_first_present(app_data, ("mau_unit", "unit"), "亿"), "亿"),
                yoy=_safe_text(app_data.get("yoy"), "+1.4亿"),
                share=_safe_ratio(app_data.get("share"), 85),
                trend=_safe_text(app_data.get("trend"), "up")
            )
            apps.append(app)
        if not apps:
            apps.append(PlatformApp(
                name="红果免费短剧",
                mau=3.04,
                mau_unit="亿",
                yoy="+1.4亿",
                share=85,
                trend="up"
            ))
        
        mini_programs = data.get("mini_programs", [])
        if not isinstance(mini_programs, list):
            mini_programs = []
        platform = PlatformData(apps=apps, mini_programs=mini_programs)

        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as fd:
                json.dump(
                    {
                        "last_updated": date_str,
                        "industry": industry.model_dump(),
                        "platform": platform.model_dump()
                    },
                    fd,
                    ensure_ascii=False,
                    indent=2
                )
        except Exception as cache_exc:
            logger.warning(f"industry_node: 写入7天长效缓存失败: {cache_exc}")
        
        return IndustryNodeOutput(
            industry=industry,
            platform=platform,
            success=True,
            error_message=input_error_message
        )
        
    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"industry_node: 行业数据搜索或 JSON 解析失败: {e}"
        logger.error(error_message, exc_info=True)
        # 返回默认数据
        return IndustryNodeOutput(
            industry=IndustryData(
                user_scale="7.18亿",
                market_size="1000亿+",
                drama_count="25万+",
                billion_dramas=20,
                ai_ratio=38,
                female_ratio=95,
                male_ratio=5,
                app_mau="3.04亿",
                app_mau_yoy="+1.4亿"
            ),
            platform=PlatformData(
                apps=[PlatformApp(
                    name="红果免费短剧",
                    mau=3.04,
                    mau_unit="亿",
                    yoy="+1.4亿",
                    share=85,
                    trend="up"
                )]
            ),
            success=True,
            error_message=error_message + "\n"
        )