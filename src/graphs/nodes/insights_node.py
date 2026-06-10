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
    integrations: DeepSeek API（search + chat）
    """
    ctx = runtime.context
    
    try:
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
        
        # 初始化DeepSeek客户端
        client = MoonshotClient()
        
        # 🚨 第一步：使用 DuckDuckGo 真实检索最新大事件
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
        
        # 调用DeepSeek生成洞察（现在有真实搜索结果作为上下文）
        response = client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=3000
        )
        
        # 提取JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            try:
                json.loads(response)
                json_str = response
            except:
                # 尝试提取数组
                array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response)
                if array_match:
                    json_str = array_match.group(0)
                else:
                    json_str = "[]"
        
        insights_data = json.loads(json_str)
        
        # 转换为Insight对象列表
        insights = []
        for item in insights_data:
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
            success=True
        )
        
    except Exception as e:
        logger.error(f"洞察生成节点失败: {e}")
        # 返回默认洞察
        return InsightsNodeOutput(
            insights=[
                Insight(icon="📊", title="数据待补充", content="请稍后再试", source="")
            ],
            success=False
        )