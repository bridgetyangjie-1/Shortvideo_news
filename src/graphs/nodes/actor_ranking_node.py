"""
演员榜单生成节点 - 生成女频/男频演员TOP10
"""
import os
import json
import re
import logging
import time
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.moonshot_api import MoonshotClient
from tools.deepseek_api import DeepSeekClient

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
        
        # 将榜单数据转换为普通字典，兼容 Pydantic 模型和历史 dict 输入。
        rankings_data = []
        for r in state.enriched_rankings:
            if hasattr(r, "model_dump"):
                rankings_data.append(r.model_dump())
            elif isinstance(r, dict):
                rankings_data.append(r)
            else:
                logger.warning(f"actor_ranking_node: 跳过无法序列化的榜单项: {type(r)}")

        if not rankings_data:
            error_message = "actor_ranking_node: enriched_rankings 无可用数据，无法生成演员榜。"
            logger.error(error_message)
            return ActorRankingNodeOutput(
                actors=ActorsData(),
                success=False,
                error_message=error_message + "\n"
            )
        
        # 渲染用户提示词
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2)
        })
        
        # 初始化双模型客户端
        kimi_client = MoonshotClient()
        ds_client = DeepSeekClient()
        
        # 先用Kimi搜索补充演员信息（多轮搜索+多来源）
        search_context = ""
        for ranking in rankings_data[:20]:
            title = ranking.get("title", "")
            female_lead = ranking.get("female_lead", "未知")
            male_lead = ranking.get("male_lead", "未知")
            
            # 如果任一演员未知，进行多轮搜索
            if female_lead == "未知" or male_lead == "未知":
                # 第一轮：精确搜索（剧目+演员+主演）
                search_queries = [
                    f"短剧《{title}》演员 主演 女主 男主",
                    f"《{title}》短剧 主演是谁 DataEye 红果",
                    f"短剧 {title} 演员表 cast 小红书 抖音"
                ]
                
                for query in search_queries:
                    logger.info(f"搜索《{title}》演员: {query}")
                    search_result = kimi_client.search(query)
                    if search_result and len(search_result) > 50:
                        search_context += f"\n【《{title}》演员搜索结果】:\n{search_result[:800]}\n"
                        break  # 找到结果就停止
                    time.sleep(1)  # 节流
                
                time.sleep(1)  # 每部剧搜索间隔
        
        # 构建消息（包含搜索补充信息）
        enhanced_prompt = user_prompt
        if search_context:
            enhanced_prompt += f"\n\n🚨以下是演员搜索补充资料（小红书/抖音等）：\n{search_context}"
        
        # 调用 DeepSeek 进行推理（生成演员榜JSON）
        messages = [
            {"role": "system", "content": sp},
            {"role": "user", "content": enhanced_prompt}
        ]
        actors_data = ds_client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=4000
        )

        # DeepSeek返回的是字符串，需要解析JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', actors_data)
        if json_match:
            actors_dict = json.loads(json_match.group())
        else:
            logger.error(f"actor_ranking_node: 无法解析JSON, 原始响应: {actors_data[:500]}")
            actors_dict = {"female": [], "male": []}
        
        if not isinstance(actors_dict, dict):
            logger.error(f"actor_ranking_node: 解析后类型错误: {type(actors_dict)}")
            actors_dict = {"female": [], "male": []}
        
        # 转换为ActorRanking对象
        female_actors = []
        for item in actors_dict.get("female", []):
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
        for item in actors_dict.get("male", []):
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