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
from tools.moonshot_api import MoonshotClient

# Fallback for test_run environment
try:
    from tools.moonshot_api import is_api_budget_error
except ImportError:
    def is_api_budget_error(exc: Exception) -> bool:
        return str(exc) == "API \u8c03\u7528\u6b21\u6570\u8fc7\u591a\uff0c\u5df2\u718f\u65ad"

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
    desc: 使用 Kimi 根据TOP20榜单生成演员人气榜（女频TOP10、男频TOP10）
    integrations: Moonshot API
    """
    ctx = runtime.context
    
    try:
        if not state.enriched_rankings:
            error_message = "actor_ranking_node: enriched_rankings 为空，无法生成演员榜；请检查 enrich_node。"
            logger.error(error_message)
            return ActorRankingNodeOutput(
                actors=ActorsData(),
                success=False,
                error_message=error_message + "\n"
            )

        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.3)
        
        # 将榜单数据转换为JSON字符串
        rankings_data = [r.model_dump() for r in state.enriched_rankings]
        
        # 渲染用户提示词
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2)
        })
        
        # 初始化 Kimi 客户端
        client = MoonshotClient()
        
        # 构建消息
        messages = [
            {"role": "system", "content": sp},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 Kimi 并解析结构化输出
        actors_data = client.structured_output(
            messages=messages,
            temperature=temperature,
            max_tokens=4000
        )

        if not isinstance(actors_data, dict):
            raise ValueError(f"actor_ranking_node: Kimi 返回类型错误: {type(actors_data)}")
        
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
        if is_api_budget_error(e):
            raise
        error_message = f"actor_ranking_node: 演员榜单生成或 JSON 解析失败: {e}"
        logger.error(error_message, exc_info=True)
        return ActorRankingNodeOutput(
            actors=ActorsData(),
            success=False,
            error_message=error_message + "\n"
        )