"""
演员榜单生成节点 - 生成女频/男频演员TOP10
优化版：减少Kimi调用，优先从榜单数据提取演员
"""
import os
import json
import re
import logging
from collections import Counter
from typing import Dict, Any, List
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.deepseek_api import DeepSeekClient

# Fallback for test_run environment
try:
    from tools.moonshot_api import is_api_budget_error
except ImportError:
    def is_api_budget_error(exc: Exception) -> bool:
        return str(exc) == "API 调用次数过多，已熔断"

from graphs.state import (
    ActorRankingNodeInput, 
    ActorRankingNodeOutput, 
    ActorsData,
    ActorRanking
)

# 初始化日志
logger = logging.getLogger(__name__)


def _extract_actors_from_rankings(rankings_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    从榜单数据中提取演员信息，统计出场次数
    
    Returns:
        {"female": [演员信息], "male": [演员信息]}
    """
    female_counter = Counter()
    male_counter = Counter()
    actor_works: Dict[str, List[str]] = {}  # 记录每个演员的作品
    
    for ranking in rankings_data:
        title = ranking.get("title", "")
        female_lead = ranking.get("female_lead", "")
        male_lead = ranking.get("male_lead", "")
        category = ranking.get("category", "female")  # 默认女频
        
        # 统计女演员
        if female_lead and female_lead not in ["未知", "", "待补充"]:
            female_counter[female_lead] += 1
            if female_lead not in actor_works:
                actor_works[female_lead] = []
            actor_works[female_lead].append(title)
        
        # 统计男演员
        if male_lead and male_lead not in ["未知", "", "待补充"]:
            male_counter[male_lead] += 1
            if male_lead not in actor_works:
                actor_works[male_lead] = []
            actor_works[male_lead].append(title)
    
    # 转换为榜单格式
    female_actors = []
    for rank, (name, count) in enumerate(female_counter.most_common(10), 1):
        female_actors.append({
            "rank": rank,
            "name": name,
            "popularity": count * 10,  # 简单热度计算
            "platform_fans": 0.0,
            "platform": "红果",
            "badge": "热门演员" if count >= 3 else "",
            "works": "、".join(actor_works.get(name, [])[:3]),
            "trend": "up" if count >= 3 else "same"
        })
    
    male_actors = []
    for rank, (name, count) in enumerate(male_counter.most_common(10), 1):
        male_actors.append({
            "rank": rank,
            "name": name,
            "popularity": count * 10,
            "platform_fans": 0.0,
            "platform": "红果",
            "badge": "热门演员" if count >= 3 else "",
            "works": "、".join(actor_works.get(name, [])[:3]),
            "trend": "up" if count >= 3 else "same"
        })
    
    return {"female": female_actors, "male": male_actors}


def actor_ranking_node(state: ActorRankingNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> ActorRankingNodeOutput:
    """
    title: 演员榜单生成
    desc: 从榜单数据中提取演员统计生成演员榜（女频TOP10、男频TOP10），无需Kimi搜索
    integrations: DeepSeek API（仅在数据不足时推理补充）
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

        # 将榜单数据转换为普通字典
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
        
        # ========== 优先从榜单数据提取演员（无需Kimi调用）==========
        logger.info("=" * 50)
        logger.info("从榜单数据中提取演员统计")
        logger.info("=" * 50)
        
        actors_dict = _extract_actors_from_rankings(rankings_data)
        
        # 检查是否需要推理补充
        female_count = len(actors_dict.get("female", []))
        male_count = len(actors_dict.get("male", []))
        
        if female_count < 5 or male_count < 5:
            logger.warning(f"榜单演员不足（女{female_count}男{male_count}），使用DeepSeek推理补充")
            
            # 读取配置文件
            cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
            with open(cfg_file, "r", encoding="utf-8") as fd:
                _cfg = json.load(fd)
            
            sp = _cfg.get("sp", "")
            up = _cfg.get("up", "")
            temperature = _cfg.get("config", {}).get("temperature", 0.3)
            
            # 渲染用户提示词
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            up_tpl = Template(up)
            user_prompt = up_tpl.render({
                "date": current_date,
                "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2)
            })
            
            # 只用DeepSeek推理（1次调用）
            ds_client = DeepSeekClient()
            messages = [
                {"role": "system", "content": sp},
                {"role": "user", "content": user_prompt}
            ]
            
            try:
                actors_response = ds_client.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4000
                )
                
                # 解析JSON
                json_match = re.search(r'\{[\s\S]*\}', actors_response)
                if json_match:
                    actors_dict = json.loads(json_match.group())
                    logger.info("✅ DeepSeek推理补充演员成功")
            except Exception as e:
                logger.warning(f"DeepSeek推理补充失败: {e}，使用原始提取结果")
        else:
            logger.info(f"✅ 从榜单提取演员成功：女频{female_count}人，男频{male_count}人")
        
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
