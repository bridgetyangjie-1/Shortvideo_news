"""
洞察生成节点 - Gemini架构重构：真实搜索+强制拆解
"""
import os
import json
import re
import logging
from typing import List, Dict, Any
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
    InsightsNodeInput,
    InsightsNodeOutput,
    Insight
)

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def insights_node(state: InsightsNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> InsightsNodeOutput:
    """
    title: 行业大事件（先搜后问架构）
    desc: Gemini重构 - 先真实搜索行业事件，再结合榜单数据生成爆款归因+买量建议
    integrations: Moonshot API（search + chat）
    """
    ctx = runtime.context
    
    try:
        input_error_message = ""
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.5)
        
        # 准备数据
        rankings_data: List[Dict[str, Any]] = []
        enriched_rankings_list = list(state.enriched_rankings) if hasattr(state.enriched_rankings, '__iter__') else []
        if not enriched_rankings_list:
            input_error_message = "insights_node: enriched_rankings 为空，洞察无法基于真实榜单生成；请检查 enrich_node。\n"
            logger.error(input_error_message.strip())

        for r in enriched_rankings_list:
            if hasattr(r, 'model_dump'):
                rankings_data.append(r.model_dump())
            elif isinstance(r, dict):
                rankings_data.append(r)
        
        industry_data: Dict[str, Any] = {}
        if hasattr(state.industry, 'model_dump'):
            industry_data = state.industry.model_dump()
        elif isinstance(state.industry, dict):
            industry_data = state.industry
        
        # 初始化 Kimi 客户端
        client = MoonshotClient()
        
        # 🚨 第一步：使用 Kimi $web_search 真实检索最新大事件
        search_query = f"短剧行业 最新爆款 融资 政策 动态 {state.data_date}"
        search_response = client.search(query=search_query, max_results=5)
        
        logger.info(f"事件真实搜索结果: {search_response[:500]}...")
        
        # 第二步：结合榜单数据和搜索结果，生成洞察
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "data_date": state.data_date,
            "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2),
            "industry": json.dumps(industry_data, ensure_ascii=False, indent=2),
            "search_results": search_response  # 🚨 喂入真实搜索结果
        })
        
        # 构建消息
        messages = [
            {"role": "system", "content": sp},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 Kimi 生成洞察（现在有真实搜索结果作为上下文）
        insights_data = client.structured_output(
            messages=messages,
            temperature=temperature,
            max_tokens=3000,
            expected_type=list
        )
        
        # 转换为Insight对象列表
        insights = []
        for item in insights_data:
            if not isinstance(item, dict):
                continue
            insight = Insight(
                icon=item.get("icon", "📊"),
                title=item.get("title", ""),
                content=item.get("content", ""),
                source=item.get("source", "")
            )
            insights.append(insight)
        
        # 确保至少有2条洞察（强制拆解）
        if len(insights) < 2:
            # 补充默认洞察
            if rankings_data:
                top_drama = rankings_data[0] if rankings_data else {}
                insights.append(Insight(
                    icon="🔥",
                    title=f"爆款归因：{top_drama.get('title', 'TOP1剧目')}",
                    content=f"受众定位25-35岁女性，爽点公式：{', '.join(top_drama.get('core_trope', ['逆袭', '甜宠']))}，建议优先投流抖音平台。",
                    source="榜单数据推演"
                ))
                insights.append(Insight(
                    icon="💰",
                    title="买量建议",
                    content=f"今日榜单头部题材CPA可能具有优势，建议关注{top_drama.get('genre', '甜宠')}题材的投流机会。",
                    source="数据分析"
                ))
        
        logger.info(f"洞察生成完成，共{len(insights)}条")
        
        return InsightsNodeOutput(
            insights=insights,
            success=True,
            error_message=input_error_message
        )
        
    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"insights_node: 洞察生成、搜索或 JSON 解析失败: {e}"
        logger.error(error_message, exc_info=True)
        # 返回默认洞察
        return InsightsNodeOutput(
            insights=[
                Insight(icon="📊", title="数据待补充", content="请稍后再试", source="")
            ],
            success=False,
            error_message=error_message + "\n"
        )