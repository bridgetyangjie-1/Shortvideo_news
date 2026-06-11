"""
洞察生成节点 - 双模型协同解耦架构
Kimi负责搜索，DeepSeek负责推理
"""
import os
import json
import re
import logging
import time
from typing import List, Dict, Any
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from tools.moonshot_api import MoonshotClient
from tools.deepseek_api import DeepSeekClient

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
    title: 行业大事件（双模型协同）
    desc: Kimi搜索行业事件 → DeepSeek推理生成洞察JSON
    integrations: Moonshot API + DeepSeek API
    """
    ctx = runtime.context
    
    input_error_message = ""
    
    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.3)
        
        # 准备榜单数据
        rankings_data: List[Dict[str, Any]] = []
        enriched_rankings_list = list(state.enriched_rankings) if hasattr(state.enriched_rankings, '__iter__') else []
        
        if not enriched_rankings_list:
            input_error_message = "insights_node: enriched_rankings 为空\n"
            logger.error(input_error_message.strip())
        
        for r in enriched_rankings_list:
            if hasattr(r, 'model_dump'):
                rankings_data.append(r.model_dump())
            elif isinstance(r, dict):
                rankings_data.append(r)
        
        # 准备行业数据
        industry_data: Dict[str, Any] = {}
        if hasattr(state.industry, 'model_dump'):
            industry_data = state.industry.model_dump()
        elif isinstance(state.industry, dict):
            industry_data = state.industry
        
        # 初始化双客户端
        kimi_client = MoonshotClient()
        ds_client = DeepSeekClient()
        
        # ========== 搜集阶段：Kimi搜索 ==========
        search_query = f"短剧行业 最新爆款 融资 政策 动态 {state.data_date}"
        search_response = kimi_client.search(query=search_query, max_results=5)
        logger.info(f"Kimi搜索成功: {search_response[:300]}...")
        time.sleep(1)  # 🚨 节流阀（Tier 7配额充足）
        
        # ========== 推理阶段：DeepSeek生成JSON ==========
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "data_date": state.data_date,
            "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2),
            "industry": json.dumps(industry_data, ensure_ascii=False, indent=2),
            "search_results": search_response
        })
        
        full_prompt = f"""{user_prompt}

🚨【时间铁律 - 最高优先级】
⚠️ 只分析【今日：{state.data_date}】的行业大事件！
⚠️ 搜索结果中的往年数据一律丢弃，不作为今日洞察来源！
⚠️ 如果没有今日大事件，基于今日榜单数据进行分析。

🚨 必须输出合法JSON数组格式，不要加```json包裹：
[
  {{
    "icon": "🔥|💰|📊",
    "title": "洞察标题",
    "content": "具体分析内容（爆款归因/买量建议）",
    "source": "数据来源"
  }}
]
"""
        
        response = ds_client.chat(
            messages=[
                {"role": "system", "content": sp or "你是短剧行业分析师。必须输出纯JSON数组，爆款归因+买量建议。"},
                {"role": "user", "content": full_prompt}
            ],
            temperature=temperature,
            max_tokens=3000
        )
        
        logger.info(f"DeepSeek响应: {response[:500]}...")
        
        # ========== 健壮性解析 ==========
        insights: List[Insight] = []
        try:
            # 去除Markdown标记
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            # 正则提取JSON数组
            json_match = re.search(r'\[[\s\S]*\]', clean_response)
            if json_match:
                json_str = json_match.group(0)
                insights_data = json.loads(json_str)
                
                for item in insights_data:
                    if isinstance(item, dict):
                        insight = Insight(
                            icon=item.get("icon", "📊"),
                            title=item.get("title", ""),
                            content=item.get("content", ""),
                            source=item.get("source", "")
                        )
                        insights.append(insight)
            else:
                raise ValueError("未找到有效JSON数组")
                
        except Exception as parse_error:
            logger.error(f"insights_node: JSON解析失败: {parse_error}")
            logger.error(f"原始响应: {response}")
        
        # 确保至少有2条洞察
        if len(insights) < 2:
            if rankings_data:
                top_drama = rankings_data[0] if rankings_data else {}
                insights.append(Insight(
                    icon="🔥",
                    title=f"爆款归因：{top_drama.get('title', 'TOP1')}",
                    content=f"受众定位25-35岁女性，爽点公式：{', '.join(top_drama.get('core_trope', ['逆袭', '甜宠']))}",
                    source="榜单推演"
                ))
                insights.append(Insight(
                    icon="💰",
                    title="买量建议",
                    content=f"建议关注{top_drama.get('genre', '甜宠')}题材投流机会",
                    source="数据分析"
                ))
        
        logger.info(f"洞察生成完成，共{len(insights)}条")
        
        return InsightsNodeOutput(
            insights=insights,
            success=True,
            error_message=input_error_message
        )
        
    except Exception as e:
        error_message = f"insights_node: 洞察生成失败: {e}"
        logger.error(error_message, exc_info=True)
        return InsightsNodeOutput(
            insights=[
                Insight(icon="📊", title="数据待补充", content="请稍后再试", source="")
            ],
            success=False,
            error_message=error_message + "\n"
        )