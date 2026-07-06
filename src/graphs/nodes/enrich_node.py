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
from typing import Any, Dict, List

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
from tools.actor_name_utils import sanitize_ranking_actors


def _backfill_basic_fields(
    refined: List[Dict[str, Any]],
    basic: List[Any],
) -> List[Dict[str, Any]]:
    """用红果直爬的原始可信字段回填 DeepSeek 输出中缺失的元数据。"""
    basic_by_title: Dict[str, Dict[str, Any]] = {}
    basic_by_rank: Dict[int, Dict[str, Any]] = {}
    for item in basic:
        if hasattr(item, "model_dump"):
            src = item.model_dump()
        elif isinstance(item, dict):
            src = dict(item)
        else:
            continue
        title = src.get("title", "")
        if title:
            basic_by_title[title] = src
        rank = src.get("rank")
        if rank is not None:
            basic_by_rank[int(rank)] = src

    for idx, item in enumerate(refined):
        if not isinstance(item, dict):
            continue
        # 优先按标题匹配，其次按 rank 字段，最后按列表下标兜底
        src = basic_by_title.get(item.get("title", ""))
        if not src:
            src = basic_by_rank.get(int(item.get("rank", 0) or 0))
        if not src and idx < len(basic):
            candidate = basic[idx]
            if hasattr(candidate, "model_dump"):
                src = candidate.model_dump()
            elif isinstance(candidate, dict):
                src = candidate
        if not src:
            continue
        # 判断来源可信度：短剧工程周榜为高质量数据源，优先保留其热度/指数
        is_high_confidence = src.get("data_source") == "duanjugongcheng" or (src.get("confidence_score") or 0) >= 0.85
        
        if is_high_confidence:
            # 高可信来源：覆盖 DeepSeek 可能丢失或改写的热度相关字段
            item["views"] = src.get("views", item.get("views", ""))
            item["views_num"] = src.get("views_num", item.get("views_num", 0))
            item["heat"] = src.get("heat", item.get("heat", 0))
            item["data_source"] = src.get("data_source", item.get("data_source", "unknown"))
            item["confidence_score"] = src.get("confidence_score", item.get("confidence_score", 0.7))
            if src.get("release_date"):
                item["release_date"] = src.get("release_date")
            if src.get("week_date"):
                item["week_date"] = src.get("week_date")
            if src.get("weekly_index"):
                item["weekly_index"] = src.get("weekly_index")
            if src.get("total_index"):
                item["total_index"] = src.get("total_index")
        else:
            # 低可信来源（如红果推荐页）：仅当 DeepSeek 未返回或返回空时回填
            if not item.get("views") and src.get("views"):
                item["views"] = src.get("views")
            if not item.get("views_num") and src.get("views_num"):
                item["views_num"] = src.get("views_num")
            if not item.get("heat") and src.get("heat"):
                item["heat"] = src.get("heat")
        
        # 通用元数据回填（适用于所有来源）
        if not item.get("series_id"):
            item["series_id"] = src.get("series_id", "")
        if not item.get("cover"):
            item["cover"] = src.get("cover", "")
        if not item.get("production_house"):
            item["production_house"] = src.get("production_house") or src.get("studio", "")
        if not item.get("platform"):
            item["platform"] = src.get("platform", "红果")
        if not item.get("tags"):
            item["tags"] = list(src.get("tags", []))
        if not item.get("episodes_count") and src.get("episodes_count"):
            item["episodes_count"] = src.get("episodes_count")
    return refined

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

        # 第三步：用原始红果数据回填 DeepSeek 可能丢失的可信字段（series_id/cover/厂牌等）
        rankings_data = _backfill_basic_fields(rankings_data, basic_rankings_list)

        # 第四步：兜底填充演员（过滤占位名）
        for item in rankings_data:
            if isinstance(item, dict):
                sanitize_ranking_actors(item)
        rankings_data = fill_unknown_actors(rankings_data)

        # 第五步：榜单数量补齐
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
                    change=item.get("change", ""),
                    heat=item.get("heat", 0),
                    production_house=item.get("production_house", ""),
                    core_trope=item.get("core_trope", []),
                    episodes_count=item.get("episodes_count", 80),
                    confidence_score=item.get("confidence_score", 0.7),
                    data_source=item.get("data_source", "hongguo"),
                    rank_change=item.get("rank_change", 0),
                    previous_rank=item.get("previous_rank", 0),
                    cross_validated=item.get("cross_validated", False),
                    dataeye_rank=item.get("dataeye_rank", 0),
                    dataeye_heat=item.get("dataeye_heat", 0),
                    total_index=item.get("total_index", 0),
                    is_new=item.get("is_new", False),
                    release_date=item.get("release_date", ""),
                    week_date=item.get("week_date", ""),
                    series_id=item.get("series_id", ""),
                    cover=item.get("cover", ""),
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
