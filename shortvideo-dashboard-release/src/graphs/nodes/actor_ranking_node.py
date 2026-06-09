"""
演员榜单生成节点 - 生成女频/男频演员TOP10
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

from graphs.state import (
    ActorRankingNodeInput, 
    ActorRankingNodeOutput, 
    ActorsData,
    ActorRanking
)

# 初始化日志
logger = logging.getLogger(__name__)


def actor_ranking_node(state: ActorRankingNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> ActorRankingNodeOutput:
    """
    title: 演员榜单生成
    desc: 根据TOP20榜单中出现最多的演员，生成演员人气榜（女频TOP10、男频TOP10）
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
        
        # 将榜单数据转换为JSON字符串
        rankings_data = [r.model_dump() for r in state.enriched_rankings]
        
        # 渲染用户提示词
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2)
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
            max_completion_tokens=llm_config.get("max_completion_tokens", 4000)
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
        
        actors_data = json.loads(json_str)
        
        # 转换为ActorRanking对象
        female_actors = []
        for item in actors_data.get("female", []):
            actor = ActorRanking(
                rank=item.get("rank", 0),
                name=item.get("name", ""),
                popularity=item.get("popularity", 0),
                platform_fans=item.get("platform_fans", 0.0),
                platform=item.get("platform", "红果"),
                badge=item.get("badge", ""),
                works=item.get("works", ""),
                trend=item.get("trend", "")
            )
            female_actors.append(actor)
        
        male_actors = []
        for item in actors_data.get("male", []):
            actor = ActorRanking(
                rank=item.get("rank", 0),
                name=item.get("name", ""),
                popularity=item.get("popularity", 0),
                platform_fans=item.get("platform_fans", 0.0),
                platform=item.get("platform", "红果"),
                badge=item.get("badge", ""),
                works=item.get("works", ""),
                trend=item.get("trend", "")
            )
            male_actors.append(actor)
        
        actors = ActorsData(
            female=female_actors,
            male=male_actors
        )
        
        return ActorRankingNodeOutput(
            actors=actors,
            success=True
        )
        
    except Exception as e:
        logger.error(f"演员榜单生成失败: {str(e)}")
        return ActorRankingNodeOutput(
            actors=ActorsData(),
            success=False
        )
