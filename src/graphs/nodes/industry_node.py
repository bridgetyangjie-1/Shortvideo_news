"""
行业数据节点 - 获取行业宏观数据
"""
import os
import json
import re
import logging
from datetime import datetime
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

# 初始化日志
logger = logging.getLogger(__name__)


def industry_node(state: IndustryNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> IndustryNodeOutput:
    """
    title: 行业数据获取
    desc: 使用 Kimi 联网搜索获取最新的行业宏观数据（用户规模、市场规模、AI短剧占比等）
    integrations: Moonshot API
    """
    ctx = runtime.context
    
    try:
        input_error_message = ""
        if not state.enriched_rankings:
            input_error_message = "industry_node: enriched_rankings 为空，AI/女频比例只能使用默认或搜索兜底；请检查 enrich_node。\n"
            logger.error(input_error_message.strip())

        # 1. 统计榜单中的AI剧和女男频比例
        ai_count = sum(1 for r in state.enriched_rankings if r.is_ai)
        female_count = sum(1 for r in state.enriched_rankings if r.category == "female")
        male_count = sum(1 for r in state.enriched_rankings if r.category == "male")
        total = len(state.enriched_rankings) if state.enriched_rankings else 1
        
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
        ai_search_query = f"""请联网搜索2026年短剧行业AI短剧占比数据。
参考日期：{state.data_date}

搜索关键词建议：
- "短剧行业 AI短剧占比 2026"
- "短剧 AI生成 比例 趋势"
- "AI短剧 市场份额 数据"

请返回JSON格式：{"ai_ratio": 数值(百分比), "ai_drama_count": 数量, "ai_trend": "上升/持平/下降"}
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
        except Exception as e:
            logger.warning(f"AI短剧渗透率搜索失败: {e}")
            ai_data = {}
        
        # 第二轮搜索：其他行业宏观数据
        search_query = f"""请搜索互联网，获取最新的短剧行业宏观数据，包括：
1. APP月活用户数（红果、抖音等）
2. 短剧数量（总剧目数）
3. 亿元播放量短剧数量
4. 主要平台的月活用户数和同比增长

参考日期：{state.data_date}

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
        
        # 合并AI短剧数据（优先使用专项搜索结果）
        if ai_data.get("ai_ratio"):
            data["ai_ratio"] = ai_data.get("ai_ratio")
        
        # 5. 构建行业数据（使用搜索结果或榜单统计）
        industry = IndustryData(
            user_scale=data.get("user_scale", "7.18亿"),
            market_size=data.get("market_size", "1000亿+"),
            drama_count=data.get("drama_count", "25万+"),
            billion_dramas=data.get("billion_dramas", 20),
            ai_ratio=data.get("ai_ratio", int(ai_count / total * 100)),
            female_ratio=data.get("female_ratio", int(female_count / total * 100)),
            male_ratio=data.get("male_ratio", int(male_count / total * 100)),
            app_mau=data.get("app_mau", "3.04亿"),
            app_mau_yoy=data.get("app_mau_yoy", "+1.4亿")
        )
        
        # 6. 构建平台数据
        apps = []
        for app_data in data.get("platform_apps", [{"name": "红果免费短剧", "mau": 3.04, "mau_unit": "亿", "yoy": "+1.4亿", "share": 85, "trend": "up"}]):
            app = PlatformApp(
                name=app_data.get("name", "红果免费短剧"),
                mau=app_data.get("mau", 3.04),
                mau_unit=app_data.get("mau_unit", "亿"),
                yoy=app_data.get("yoy", "+1.4亿"),
                share=app_data.get("share", 85),
                trend=app_data.get("trend", "up")
            )
            apps.append(app)
        
        platform = PlatformData(apps=apps, mini_programs=data.get("mini_programs", []))
        
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