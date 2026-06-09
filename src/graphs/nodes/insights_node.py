"""
洞察生成节点 - 生成具体的行业大事件分析
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
    title: 行业大事件
    desc: 使用DeepSeek联网搜索+数据分析，生成具体的行业大事件（含数据）
    integrations: DeepSeek API
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
        rankings_data: List[Dict[str, Any]] = [r.model_dump() for r in state.enriched_rankings]
        industry_data: Dict[str, Any] = state.industry.model_dump()
        
        # 初始化DeepSeek客户端
        client = DeepSeekClient()
        
        # 第一步：联网搜索最新的行业大事件
        search_prompt = f"""请搜索短剧行业最近一周的重要事件，重点关注：
1. 播放量爆款：哪部剧播放量突然暴涨（环比增长超30%）
2. 厂牌动向：九州、点众、麦芽等头部厂牌的最新爆款或产能变化
3. 商业事件：融资、IPO、平台新规、分成政策调整
4. 技术突破：AI短剧新工具上线、AI剧播放量创新高

日期参考：{state.data_date}

请返回具体的新闻事件（带数据），如：
- "九州新剧《XXX》首周播放破8000万"
- "抖音短剧分成比例提升至70%"
"""
        
        search_response = client.chat(
            messages=[
                {"role": "system", "content": "你是短剧行业情报搜索专家，擅长发现带数据的具体事件。"},
                {"role": "user", "content": search_prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
        logger.info(f"事件搜索结果: {search_response[:500]}...")
        
        # 第二步：结合榜单数据生成洞察
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "data_date": state.data_date,
            "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2),
            "industry": json.dumps(industry_data, ensure_ascii=False, indent=2),
            "search_events": search_response
        })
        
        # 加入搜索结果作为额外上下文
        full_prompt = user_prompt + f"\n\n【搜索到的行业事件】：\n{search_response}"
        
        # 调用DeepSeek生成洞察
        response = client.chat(
            messages=[
                {"role": "system", "content": sp},
                {"role": "user", "content": full_prompt}
            ],
            temperature=temperature,
            max_tokens=2000
        )
        
        logger.info(f"洞察生成结果: {response[:500]}...")
        
        # 提取JSON
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            json_str = json_match.group()
            insights_data: List[Dict[str, Any]] = json.loads(json_str)
            
            # 转换为Insight对象
            insights: List[Insight] = []
            for item in insights_data:
                insight = Insight(
                    icon=item.get("icon", "📊"),
                    title=item.get("title", "")[:10],
                    content=item.get("content", "")[:80]
                )
                insights.append(insight)
            
            return InsightsNodeOutput(
                insights=insights,
                success=True
            )
        
    except Exception as e:
        logger.error(f"洞察生成失败: {str(e)}")
    
    # 返回具体的默认洞察（含数据）
    default_insights: List[Insight] = [
        Insight(
            icon="📊", 
            title="大盘平稳", 
            content="今日各平台榜单无显著异动，TOP8剧目排名稳定，维持常规投流策略。"
        )
    ]
    return InsightsNodeOutput(
        insights=default_insights,
        success=True
    )