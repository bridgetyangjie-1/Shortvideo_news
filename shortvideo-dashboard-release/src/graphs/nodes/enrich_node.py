"""
数据补充节点 - 补充演员信息、tags、desc、trend等字段
"""
import os
import json
import re
import logging
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import LLMClient
from langchain_core.messages import SystemMessage, HumanMessage

from graphs.state import EnrichNodeInput, EnrichNodeOutput, DramaRanking

# 初始化日志
logger = logging.getLogger(__name__)


def enrich_node(state: EnrichNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> EnrichNodeOutput:
    """
    title: 数据补充
    desc: 补充每部剧的演员信息、tags标签、desc剧情描述、trend趋势等字段
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        llm_config = _cfg.get("config", {})
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")
        
        # 渲染用户提示词
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "basic_rankings": json.dumps(state.basic_rankings, ensure_ascii=False, indent=2),
            "data_date": state.data_date
        })
        
        # 初始化LLM客户端
        client = LLMClient(ctx=ctx)
        
        # 构建消息
        messages = [
            SystemMessage(content=sp),
            HumanMessage(content=user_prompt)
        ]
        
        # 调用大模型
        response = client.invoke(
            messages=messages,
            model=llm_config.get("model", "doubao-seed-2-0-pro-260215"),
            temperature=llm_config.get("temperature", 0.3),
            max_completion_tokens=llm_config.get("max_completion_tokens", 8000)
        )
        
        # 提取响应内容
        response_content = response.content
        if not isinstance(response_content, str):
            if isinstance(response_content, list):
                text_parts = [
                    item.get("text", "") 
                    for item in response_content 
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                response_content = " ".join(text_parts)
            else:
                response_content = str(response_content)
        
        # 提取JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_content)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response_content
        
        rankings_data = json.loads(json_str)
        
        # 转换为DramaRanking对象列表
        enriched_rankings = []
        for item in rankings_data:
            ranking = DramaRanking(
                rank=item.get("rank", 0),
                title=item.get("title", ""),
                female_lead=item.get("female_lead", ""),
                male_lead=item.get("male_lead", ""),
                views=item.get("views", ""),
                views_num=item.get("views_num", 0),
                platform=item.get("platform", "红果"),
                genre=item.get("genre", ""),
                tags=item.get("tags", []),
                trend=item.get("trend", ""),
                trend_type=item.get("trend_type", "same"),
                category=item.get("category", "female"),
                is_ai=item.get("is_ai", False),
                desc=item.get("desc", "")
            )
            enriched_rankings.append(ranking)
        
        return EnrichNodeOutput(
            enriched_rankings=enriched_rankings,
            success=True
        )
        
    except Exception as e:
        logger.error(f"数据补充失败: {str(e)}")
        return EnrichNodeOutput(
            enriched_rankings=[],
            success=False
        )
