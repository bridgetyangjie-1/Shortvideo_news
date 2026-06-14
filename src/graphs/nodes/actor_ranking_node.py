"""
演员榜单生成节点 - 生成女频/男频演员TOP10
优化版：减少Kimi调用，优先从榜单数据提取演员
"""
import os
import json
import re
import logging
import math
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
    从榜单数据中提取演员信息，综合排名、播放量与趋势计算差异化热度值。

    热度值规则：
    - 排名权重：排名越靠前基础分越高（第1名 200 分，第20名 10 分）。
    - 播放量权重：按 log1p(播放量) 给予额外加分，避免头部过度集中。
    - 趋势权重：up/new +10，same +5，down 0。
    - 多作品加成：每多一部上榜作品额外 +5，鼓励持续曝光。

    Returns:
        {"female": [演员信息], "male": [演员信息]}
    """
    INVALID_NAMES = {"", "未知", "待补充", "待定", "unknown", "none", "n/a"}

    def _is_valid_name(name: Any) -> bool:
        if not name:
            return False
        return str(name).strip().lower() not in {n.lower() for n in INVALID_NAMES}

    female_scores: Dict[str, Dict[str, Any]] = {}
    male_scores: Dict[str, Dict[str, Any]] = {}

    for ranking in rankings_data:
        title = ranking.get("title", "")
        try:
            rank = int(ranking.get("rank", 99) or 99)
        except (TypeError, ValueError):
            rank = 99

        views_num = ranking.get("views_num", 0) or 0
        heat = ranking.get("heat", 0) or 0
        try:
            views = int(views_num or heat or 0)
        except (TypeError, ValueError):
            views = 0

        trend_raw = ranking.get("trend_type", "") or ranking.get("trend", "")
        trend_type = str(trend_raw).lower()

        # 基础排名分 + 播放量分 + 趋势分
        rank_score = max(1, 21 - rank) * 10
        view_score = round(math.log1p(views) * 2) if views > 0 else 0
        if trend_type in ("up", "new"):
            trend_bonus = 10
        elif trend_type == "same":
            trend_bonus = 5
        else:
            trend_bonus = 0
        work_score = rank_score + view_score + trend_bonus

        female_lead = ranking.get("female_lead", "")
        male_lead = ranking.get("male_lead", "")

        def _add_actor(store: Dict[str, Dict[str, Any]], name: Any):
            if not _is_valid_name(name):
                return
            name = str(name).strip()
            if name not in store:
                store[name] = {"scores": [], "works": [], "trends": []}
            store[name]["scores"].append(work_score)
            store[name]["works"].append(title)
            store[name]["trends"].append(trend_type)

        _add_actor(female_scores, female_lead)
        _add_actor(male_scores, male_lead)

    def _build_actors(actor_store: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按综合得分排序并生成榜单结构。"""
        sorted_names = sorted(
            actor_store.keys(),
            key=lambda n: (sum(actor_store[n]["scores"]), len(actor_store[n]["works"])),
            reverse=True,
        )[:10]

        actors = []
        for rank, name in enumerate(sorted_names, 1):
            entry = actor_store[name]
            base_score = sum(entry["scores"])
            works_count = len(entry["works"])
            total_score = base_score + max(0, works_count - 1) * 5
            works = entry["works"][:3]
            trends = entry["trends"]

            if any(t in ("up", "new") for t in trends):
                trend = "up"
            elif "same" in trends:
                trend = "same"
            else:
                trend = "down"

            actors.append({
                "rank": rank,
                "name": name,
                "popularity": round(total_score),
                "platform_fans": 0.0,
                "platform": "红果",
                "badge": "热门演员" if works_count >= 2 else "",
                "works": "、".join(works),
                "trend": trend,
            })
        return actors

    return {
        "female": _build_actors(female_scores),
        "male": _build_actors(male_scores),
    }


def _ensure_top10(parsed_list: List[Dict[str, Any]], source_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将 DeepSeek 返回的演员榜补齐到 10 人，避免返回数量不足。
    优先使用 parsed_list，缺失部分从 source_list（本地提取结果）补充，去重。
    """
    if not isinstance(parsed_list, list):
        parsed_list = []
    if not isinstance(source_list, list):
        source_list = []

    seen = {a.get("name") for a in parsed_list if a.get("name")}
    merged = list(parsed_list)
    for item in source_list:
        name = item.get("name")
        if name and name not in seen:
            merged.append(item)
            seen.add(name)
        if len(merged) >= 10:
            break

    # 统一字段并重新编号
    result = []
    for rank, item in enumerate(merged[:10], 1):
        result.append({
            "rank": rank,
            "name": item.get("name", ""),
            "popularity": item.get("popularity", 0),
            "platform_fans": item.get("platform_fans", 0.0),
            "platform": item.get("platform", "红果"),
            "badge": item.get("badge", ""),
            "works": item.get("works", ""),
            "trend": item.get("trend", "same"),
        })
    return result


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
        
        extracted_actors = _extract_actors_from_rankings(rankings_data)
        actors_dict = extracted_actors

        # 检查是否需要推理补充（目标男女各 TOP10）
        female_count = len(actors_dict.get("female", []))
        male_count = len(actors_dict.get("male", []))

        if female_count < 10 or male_count < 10:
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

                # 解析JSON并补齐到 TOP10
                json_match = re.search(r'\{[\s\S]*\}', actors_response)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, dict):
                        actors_dict = {
                            "female": _ensure_top10(parsed.get("female", []), extracted_actors.get("female", [])),
                            "male": _ensure_top10(parsed.get("male", []), extracted_actors.get("male", [])),
                        }
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
