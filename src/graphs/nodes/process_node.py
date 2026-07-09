"""
数据处理节点 - 清洗和结构化数据
关键变更：主数据源改为短剧工程周榜，红果推荐页仅作辅助/元数据补充。
"""
import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.moonshot_api import MoonshotClient

# Fallback for test_run environment
try:
    from tools.moonshot_api import is_api_budget_error
except ImportError:
    def is_api_budget_error(exc: Exception) -> bool:
        return str(exc) == "API 调用次数过多，已熔断"

from jinja2 import Template
from graphs.ranking_quality import RankingCountError, ensure_top_rankings
from graphs.state import ProcessNodeInput, ProcessNodeOutput
from utils.title_matcher import build_title_metadata_indexes, lookup_hongguo_metadata
from tools.duanjugongcheng_crawler import backfill_rankings_from_detail_api
from tools.hongguo_series_search import resolve_series_id_from_catalog


# 初始化日志
logger = logging.getLogger(__name__)


def _parse_duanju_data(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从搜索结果中提取短剧工程周榜数据"""
    for item in search_results:
        if item.get("type") == "duanjugongcheng_ranking":
            raw_content = item.get("raw_content", "")
            if raw_content:
                try:
                    data = json.loads(raw_content)
                    if isinstance(data, list):
                        logger.info(f"✅ 从短剧工程数据中提取 {len(data)} 条榜单")
                        return data
                except json.JSONDecodeError as e:
                    logger.warning(f"解析短剧工程数据失败: {e}")
    return []


def _parse_hongguo_recommend_data(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从搜索结果中提取红果推荐页数据"""
    for item in search_results:
        item_type = item.get("type", "")
        if item_type in ("hongguo_direct", "merged_ranking", "hongguo_recommend"):
            raw_content = item.get("raw_content", "")
            if raw_content:
                try:
                    data = json.loads(raw_content)
                    if isinstance(data, list):
                        logger.info(f"✅ 从红果推荐数据中提取 {len(data)} 条")
                        return data
                except json.JSONDecodeError as e:
                    logger.warning(f"解析红果推荐数据失败: {e}")
    return []


def _convert_duanju_to_rankings(duanju_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将短剧工程周榜数据转换为标准榜单格式"""
    rankings = []
    
    for item in duanju_data:
        weekly_index = int(item.get("weekly_index", 0) or 0)
        total_index = int(item.get("total_index", 0) or 0)
        
        # 周热播指数（红果官方，非播放量）
        views_str = f"{weekly_index}" if weekly_index > 0 else "热度上榜"
        
        ranking = {
            "rank": item.get("rank", 0),
            "title": item.get("title", ""),
            "views": views_str,
            "views_num": weekly_index,
            "weekly_heat_index": weekly_index,
            "platform": item.get("platform", "红果"),
            "genre": item.get("genre", ""),
            "tags": [],  # 后续用红果数据回填
            "trend": "",
            "trend_tag": "新上架" if item.get("is_new") else "",
            "trend_type": "new" if item.get("is_new") else "same",
            "category": _infer_category(item.get("genre", "")),
            "is_ai": False,
            "desc": "",
            "change": "",
            "heat": weekly_index,
            "female_lead": "",
            "male_lead": "",
            "production_house": "",
            "series_id": "",
            "cover": "",
            "core_trope": [],
            "episodes_count": 0,
            "release_date": item.get("release_date", ""),
            "week_date": item.get("week_date", ""),
            "weekly_index": weekly_index,
            "total_index": total_index,
            "slug": item.get("slug", ""),
            "confidence_score": 0.9,
            "data_source": "duanjugongcheng",
        }
        rankings.append(ranking)
    
    return rankings


def _infer_category(genre: str) -> str:
    """根据题材推断分类：female/male/ai"""
    if not genre:
        return "female"
    
    genre_lower = str(genre).lower()
    male_keywords = ["玄幻", "武侠", "战神", "赘婿", "历史", "大男主", "男频", "系统", "修仙", "特种兵", "荒野求生"]
    ai_keywords = ["ai", "aigc", "漫剧", "动画", "动漫"]
    
    for kw in ai_keywords:
        if kw in genre_lower:
            return "ai"
    for kw in male_keywords:
        if kw in genre_lower:
            return "male"
    
    return "female"


def _convert_hongguo_to_rankings(hongguo_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将红果推荐页数据转换为标准榜单格式（降级备用）"""
    rankings = []
    
    for item in hongguo_data:
        ranking = {
            "rank": item.get("rank", 0),
            "title": item.get("title", ""),
            "views": "热度上榜",
            "views_num": 0,
            "platform": item.get("platform", "红果"),
            "genre": "",
            "tags": item.get("tags", []),
            "trend": "",
            "trend_tag": "",
            "trend_type": "same",
            "category": "female",
            "is_ai": False,
            "desc": "",
            "change": "",
            "heat": 0,
            "female_lead": item.get("female_lead", ""),
            "male_lead": item.get("male_lead", ""),
            "production_house": item.get("studio", ""),
            "series_id": item.get("series_id", ""),
            "cover": item.get("cover", ""),
            "core_trope": [],
            "episodes_count": _parse_episodes(item.get("episodes", "")),
            "confidence_score": 0.5,
            "data_source": "hongguo_recommend",
        }
        rankings.append(ranking)
    
    return rankings


def _parse_episodes(episodes_str: str) -> int:
    """解析集数字符串，如'全92集' -> 92"""
    if not episodes_str:
        return 80
    match = re.search(r'(\d+)', str(episodes_str))
    if match:
        return int(match.group(1))
    return 80


def _normalize_title_key(title: str) -> str:
    """剧名归一化（兼容旧测试路径）。"""
    from utils.title_matcher import normalize_title_for_match
    return normalize_title_for_match(title)


def _find_hongguo_metadata(
    title: str,
    metadata_index: Dict[str, Dict[str, Any]],
    normalized_index: Dict[str, Dict[str, Any]],
    fuzzy_candidates: Optional[List[Tuple[str, Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    """精确匹配 → 归一化匹配 → 子串 → 模糊相似度。"""
    return lookup_hongguo_metadata(
        title,
        metadata_index,
        normalized_index,
        fuzzy_candidates or [],
    )


def _backfill_hongguo_metadata(
    rankings: List[Dict[str, Any]],
    hongguo_data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """用红果推荐页数据补充短剧工程榜单的 series_id/cover/tags/episodes"""
    if not hongguo_data:
        return rankings

    metadata_index, normalized_index, fuzzy_candidates = build_title_metadata_indexes(hongguo_data)

    backfilled = 0
    series_id_hits = 0
    for item in rankings:
        title = item.get("title", "").strip()
        meta = _find_hongguo_metadata(title, metadata_index, normalized_index, fuzzy_candidates)
        if not meta:
            continue
        backfilled += 1

        if not item.get("series_id") and meta.get("series_id"):
            item["series_id"] = meta.get("series_id", "")
            series_id_hits += 1
        if not item.get("cover") and meta.get("cover"):
            item["cover"] = meta.get("cover", "")
        if not item.get("tags") and meta.get("tags"):
            item["tags"] = list(meta.get("tags", []))
        if not item.get("production_house") and meta.get("studio"):
            item["production_house"] = meta.get("studio", "")
        if not item.get("female_lead") and meta.get("female_lead"):
            item["female_lead"] = meta.get("female_lead", "")
        if not item.get("male_lead") and meta.get("male_lead"):
            item["male_lead"] = meta.get("male_lead", "")
        if item.get("episodes_count", 80) == 80 and meta.get("episodes"):
            item["episodes_count"] = _parse_episodes(meta.get("episodes", ""))
        if not item.get("desc") and meta.get("summary"):
            item["desc"] = meta.get("summary", "")

    if backfilled:
        logger.info(
            "红果元数据回填: %d/%d 条匹配成功，其中 series_id %d 条",
            backfilled,
            len(rankings),
            series_id_hits,
        )
    return rankings


def _backfill_duanju_detail_api(rankings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """短剧工程 slug → detail API 回填封面/标签/题材。"""
    backfill_rankings_from_detail_api(rankings, max_fetch=20)
    return rankings


def _backfill_series_id_by_title(
    rankings: List[Dict[str, Any]],
    hongguo_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """按剧名在红果 catalog 中搜索 series_id（精确/高相似）。"""
    if not hongguo_data:
        return rankings
    hits = 0
    for item in rankings:
        if item.get("series_id"):
            continue
        title = item.get("title", "")
        sid = resolve_series_id_from_catalog(title, hongguo_data)
        if sid:
            item["series_id"] = sid
            hits += 1
    if hits:
        logger.info("红果剧名搜索 series_id: %d/%d 条命中", hits, len(rankings))
    return rankings


def _extract_rankings_from_search(
    search_results: List[Dict[str, Any]],
    data_date: str,
    client: MoonshotClient,
    cfg: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """使用 Kimi 从搜索结果中提取榜单（兜底方案）"""
    sp = cfg.get("sp", "")
    up = cfg.get("up", "")
    temperature = cfg.get("config", {}).get("temperature", 0.3)
    max_completion_tokens = cfg.get("config", {}).get("max_completion_tokens", 2000)
    
    search_text = ""
    for idx, item in enumerate(search_results, 1):
        if item.get("type") in ("duanjugongcheng_ranking", "hongguo_recommend"):
            continue
        search_text += f"\n【来源 {idx}】\n"
        search_text += f"关键词: {item.get('keyword', '')}\n"
        search_text += f"标题: {item.get('title', '')}\n"
        search_text += f"来源网站: {item.get('site_name', '')}\n"
        search_text += f"摘要: {item.get('summary', '') or item.get('snippet', '')}\n"
        search_text += f"发布时间: {item.get('publish_time', '')}\n"
    
    up_tpl = Template(up)
    user_prompt = up_tpl.render({
        "data_date": data_date,
        "search_results": search_text
    })
    
    messages = [
        {"role": "system", "content": sp},
        {"role": "user", "content": user_prompt}
    ]
    
    result_data = client.structured_output(
        messages=messages,
        temperature=temperature,
        max_tokens=max_completion_tokens
    )
    
    rankings: List[Dict[str, Any]] = []
    if isinstance(result_data, list):
        rankings = [item for item in result_data if isinstance(item, dict)]
    elif isinstance(result_data, dict):
        raw_rankings = (
            result_data.get("rankings")
            or result_data.get("top20")
            or result_data.get("top10")
            or result_data.get("data")
            or []
        )
        if isinstance(raw_rankings, list):
            rankings = [item for item in raw_rankings if isinstance(item, dict)]
    else:
        raise ValueError(f"process_node 解析结果类型错误: {type(result_data)}")
    
    return rankings


def process_node(
    state: ProcessNodeInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> ProcessNodeOutput:
    """
    title: 🧹 数据清洗与结构化
    desc: 优先处理短剧工程周榜，红果推荐页补充元数据，均无数据时用Kimi搜索兜底
    integrations: 短剧工程爬虫, 红果官网爬虫, Moonshot API
    """
    ctx = runtime.context
    
    # 处理默认日期
    data_date = state.data_date
    if not data_date:
        data_date = datetime.now().strftime("%Y-%m-%d")
    
    # 生成时间戳
    generated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    
    try:
        if not state.search_results:
            error_message = "process_node: search_results 为空，无法抽取榜单；请先检查 search_node。"
            logger.error(error_message)
            return ProcessNodeOutput(
                basic_rankings=[],
                quality_score=0.0,
                success=False,
                error_message=error_message + "\n"
            )
        
        # 读取LLM配置（兜底方案会用到）
        cfg_file = os.path.join(
            os.getenv("COZE_WORKSPACE_PATH", "."), 
            config["metadata"]["llm_cfg"]
        )
        with open(cfg_file, 'r', encoding='utf-8') as fd:
            _cfg = json.load(fd)
        
        # 同时准备红果推荐页数据（用于元数据回填）
        hongguo_data = _parse_hongguo_recommend_data(state.search_results)
        if hongguo_data:
            logger.info(f"✅ 获取红果推荐页 {len(hongguo_data)} 条，用于补充元数据")
        
        # ========== 第一步：优先处理短剧工程周榜 ==========
        duanju_data = _parse_duanju_data(state.search_results)
        
        if duanju_data:
            logger.info("=" * 50)
            logger.info("使用短剧工程周榜作为主数据源")
            logger.info("=" * 50)
            
            rankings = _convert_duanju_to_rankings(duanju_data)
            
            if rankings:
                logger.info(f"✅ 成功转换 {len(rankings)} 条榜单数据")

                # 短剧工程 detail API 回填封面/标签/题材
                rankings = _backfill_duanju_detail_api(rankings)

                # 用红果数据回填元数据（series_id/封面/标签）
                if hongguo_data:
                    rankings = _backfill_series_id_by_title(rankings, hongguo_data)
                    rankings = _backfill_hongguo_metadata(rankings, hongguo_data)
                
                # 数据质量检查
                count_warning = ""
                try:
                    rankings, count_warning = ensure_top_rankings(
                        rankings,
                        data_date=data_date,
                        workspace_path=os.getenv("COZE_WORKSPACE_PATH", "."),
                    )
                except RankingCountError as count_error:
                    error_message = f"process_node: {count_error}"
                    logger.error(error_message)
                    return ProcessNodeOutput(
                        basic_rankings=[],
                        quality_score=0.0,
                        success=False,
                        error_message=error_message + "\n"
                    )
                
                if count_warning:
                    logger.warning("process_node: %s", count_warning)
                
                # 计算质量分：短剧工程有真实热度指数
                valid_count = sum(
                    1 for item in rankings
                    if item.get("rank", 0) > 0 and item.get("title")
                    and item.get("weekly_index", 0) > 0
                )
                quality_score = (valid_count / len(rankings)) * 100 if rankings else 0
                quality_score = max(quality_score, 85.0)  # 短剧工程保底85分
                
                return ProcessNodeOutput(
                    basic_rankings=rankings,
                    quality_score=quality_score,
                    success=True,
                    error_message=(count_warning + "\n") if count_warning else ""
                )
        
        # ========== 第二步：短剧工程不可用，使用红果推荐页兜底 ==========
        if hongguo_data:
            logger.info("=" * 50)
            logger.info("⚠️ 短剧工程数据不可用，使用红果推荐页兜底")
            logger.info("=" * 50)
            
            rankings = _convert_hongguo_to_rankings(hongguo_data)
            
            if rankings:
                logger.info(f"✅ 成功转换 {len(rankings)} 条榜单数据")
                
                count_warning = ""
                try:
                    rankings, count_warning = ensure_top_rankings(
                        rankings,
                        data_date=data_date,
                        workspace_path=os.getenv("COZE_WORKSPACE_PATH", "."),
                    )
                except RankingCountError as count_error:
                    error_message = f"process_node: {count_error}"
                    logger.error(error_message)
                    return ProcessNodeOutput(
                        basic_rankings=[],
                        quality_score=0.0,
                        success=False,
                        error_message=error_message + "\n"
                    )
                
                if count_warning:
                    logger.warning("process_node: %s", count_warning)
                
                return ProcessNodeOutput(
                    basic_rankings=rankings,
                    quality_score=50.0,
                    success=True,
                    error_message=(count_warning + "\n") if count_warning else ""
                )
        
        # ========== 第三步：都没有数据，使用Kimi搜索结果兜底 ==========
        logger.info("=" * 50)
        logger.info("使用 Kimi 搜索结果兜底")
        logger.info("=" * 50)
        
        client = MoonshotClient()
        rankings = _extract_rankings_from_search(
            state.search_results,
            data_date,
            client,
            _cfg
        )
        
        if not rankings:
            error_message = "process_node: 未从任何来源提取到榜单数据。"
            logger.error(error_message)
            return ProcessNodeOutput(
                basic_rankings=[],
                quality_score=0.0,
                success=False,
                error_message=error_message + "\n"
            )
        
        count_warning = ""
        try:
            rankings, count_warning = ensure_top_rankings(
                rankings,
                data_date=data_date,
                workspace_path=os.getenv("COZE_WORKSPACE_PATH", "."),
            )
        except RankingCountError as count_error:
            error_message = f"process_node: {count_error}"
            logger.error(error_message)
            return ProcessNodeOutput(
                basic_rankings=[],
                quality_score=0.0,
                success=False,
                error_message=error_message + "\n"
            )
        
        if count_warning:
            logger.warning("process_node: %s", count_warning)
        
        required_fields = ["rank", "title", "views"]
        valid_count = sum(
            1 for item in rankings
            if all(item.get(field) for field in required_fields)
        )
        quality_score = (valid_count / len(rankings)) * 100 if rankings else 0
        
        return ProcessNodeOutput(
            basic_rankings=rankings,
            quality_score=quality_score,
            success=True,
            error_message=(count_warning + "\n") if count_warning else ""
        )
        
    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"process_node: 数据清洗或 JSON 解析失败: {e}"
        logger.error(error_message, exc_info=True)
        return ProcessNodeOutput(
            data_date=data_date,
            basic_rankings=[],
            quality_score=0.0,
            success=False,
            error_message=error_message + "\n"
        )
