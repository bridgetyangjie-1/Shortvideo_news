"""
数据补充节点 - 优化版：本地缓存 + 爬虫优先 + 多源融合

职责：
- 读取配置并初始化子模块
- 调用 ActorResolver 生成演员/元数据搜索上下文
- 调用 JsonRefiner 生成完整榜单 JSON
- 兜底填充演员并完成榜单数量补齐

具体实现已拆分到 enrich/ 子模块：
- cache_adapter.py    本地缓存读写
- metadata_fetcher.py 红果详情页爬虫
- actor_resolver.py   演员解析策略（缓存 → 爬虫 → 搜索）
- json_refiner.py     DeepSeek JSON 推理
- fallback.py         兜底填充逻辑
"""
import os
import json
import logging
from typing import List

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from tools.moonshot_api import MoonshotClient
from tools.deepseek_api import DeepSeekClient

from graphs.ranking_quality import RankingCountError, ensure_top_rankings
from graphs.state import EnrichNodeInput, EnrichNodeOutput, DramaRanking

from graphs.nodes.enrich.cache_adapter import DramaCache
from graphs.nodes.enrich.metadata_fetcher import HongguoDetailFetcher
from graphs.nodes.enrich.actor_resolver import ActorResolver
from graphs.nodes.enrich.json_refiner import JsonRefiner
from graphs.nodes.enrich.fallback import fill_unknown_actors

logger = logging.getLogger(__name__)


def _build_searcher(client: MoonshotClient) -> callable:
    """构造基于 Kimi 的批量搜索函数。"""
    def search(query: str) -> str:
        return client.search(query, max_results=5)
    return search


def enrich_node(
    state: EnrichNodeInput,
    config: RunnableConfig,
    runtime: Runtime,
) -> EnrichNodeOutput:
    """
    title: 数据补充（爬虫优先）
    desc: 红果详情页爬虫 → Kimi批量补充（最多1次） → DeepSeek推理生成JSON
    integrations: 红果爬虫 + Moonshot API + DeepSeek API
    """
    ctx = runtime.context

    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)

        sp = _cfg.get("sp", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.3)

        # 初始化客户端
        kimi_client = MoonshotClient()
        ds_client = DeepSeekClient()

        basic_rankings_list = list(state.basic_rankings) if hasattr(state.basic_rankings, "__iter__") else []
        if not basic_rankings_list:
            error_message = "enrich_node: 输入 basic_rankings 为空"
            logger.error(error_message)
            return EnrichNodeOutput(
                enriched_rankings=[],
                success=False,
                error_message=error_message + "\n",
            )

        # 第一步：解析演员/元数据
        resolver = ActorResolver(
            cache=DramaCache(),
            fetcher=HongguoDetailFetcher(),
            searcher=_build_searcher(kimi_client),
        )
        search_context, _missing_dramas, stats = resolver.resolve(basic_rankings_list)

        # 第二步：DeepSeek 推理生成完整榜单 JSON
        json_refiner = JsonRefiner(ds_client)
        rankings_data = json_refiner.refine(
            basic_rankings=basic_rankings_list,
            search_context=search_context,
            data_date=state.data_date,
            system_prompt=sp,
            temperature=temperature,
        )

        # 第三步：兜底填充演员
        rankings_data = fill_unknown_actors(rankings_data)

        # 第四步：榜单数量补齐
        rankings_json_list = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in basic_rankings_list
        ]
        try:
            rankings_data, count_warning = ensure_top_rankings(
                rankings_data,
                data_date=state.data_date,
                supplemental_rankings=rankings_json_list,
                workspace_path=os.getenv("COZE_WORKSPACE_PATH", ""),
            )
            if count_warning:
                logger.warning("enrich_node: %s", count_warning)
        except RankingCountError as count_error:
            error_message = f"enrich_node: {count_error}"
            logger.error(error_message)
            return EnrichNodeOutput(
                enriched_rankings=[],
                success=False,
                error_message=error_message + "\n",
            )

        # 转换为 DramaRanking 对象
        enriched_rankings: List[DramaRanking] = []
        for item in rankings_data:
            if not isinstance(item, dict):
                continue
            enriched_rankings.append(
                DramaRanking(
                    rank=item.get("rank", 0),
                    title=item.get("title", ""),
                    female_lead=item.get("female_lead", "未知"),
                    male_lead=item.get("male_lead", "未知"),
                    views=item.get("views", ""),
                    views_num=item.get("views_num", 0),
                    platform=item.get("platform", "红果"),
                    genre=item.get("genre", ""),
                    tags=item.get("tags", []),
                    trend=item.get("trend", ""),
                    trend_tag=item.get("trend_tag", ""),
                    trend_type=item.get("trend_type", "same"),
                    category=item.get("category", "female"),
                    is_ai=item.get("is_ai", False),
                    desc=item.get("desc", ""),
                    production_house=item.get("production_house", "独立厂牌"),
                    core_trope=item.get("core_trope", []),
                    episodes_count=item.get("episodes_count", 80),
                )
            )

        logger.info(
            "数据补充完成，共%s部剧 (缓存命中=%s, 爬虫补充=%s, 搜索补充=%s)",
            len(enriched_rankings),
            stats["cache_hits"],
            stats["crawler_hits"],
            stats["missing"],
        )

        return EnrichNodeOutput(
            enriched_rankings=enriched_rankings,
            success=True,
            error_message="",
        )

    except Exception as exc:
        error_message = f"enrich_node: 数据补充失败: {exc}"
        logger.error(error_message, exc_info=True)
        return EnrichNodeOutput(
            enriched_rankings=[],
            success=False,
            error_message=error_message + "\n",
        )
