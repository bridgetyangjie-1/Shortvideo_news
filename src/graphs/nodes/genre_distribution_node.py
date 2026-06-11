"""
题材分布节点 - 统计题材分布和标签热度
"""
import os
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import (
    GenreDistributionInput,
    GenreDistributionOutput,
    GenreDistribution,
    GenreStat,
    GenreStats,
    TagHeat
)

logger = logging.getLogger(__name__)

# 标签分类定义
BACKGROUND_TAGS = ["现代", "都市", "古代", "乡村", "年代", "架空", "职场", "民国", "校园", "宫廷", "荒岛"]
THEME_TAGS = ["现言", "女性成长", "脑洞", "奇幻", "玄幻", "古言", "战神", "宫斗", "仙侠", "权谋", "年代爱情", "种田", "悬疑", "喜剧", "志怪", "民国爱情", "甜宠", "复仇", "逆袭", "爽剧"]
SETTING_TAGS = ["打脸虐渣", "大男主", "大女主", "马甲", "重生", "穿越", "系统", "先婚后爱", "家长里短", "小人物", "神豪", "破镜重圆", "豪门", "强者回归", "霸总", "真假千金", "逆袭", "复仇"]


def genre_distribution_node(
    state: GenreDistributionInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> GenreDistributionOutput:
    """
    title: 📊 统计题材分布与标签热度
    desc: 基于榜单数据和标签搜索数据，统计各题材/标签的数量、播放量和热度
    integrations: 无
    """
    ctx = runtime.context
    
    try:
        # 获取数据
        rankings = state.enriched_rankings if state.enriched_rankings else []
        search_results = state.search_results if state.search_results else []
        input_error_message = ""
        if not rankings:
            input_error_message = "genre_distribution_node: enriched_rankings 为空，题材分布无法统计；请检查 enrich_node。\n"
            logger.error(input_error_message.strip())
        
        logger.info(f"题材分布节点输入: 榜单数={len(rankings)}, 搜索结果数={len(search_results)}")
        
        # 1. 统计各题材数据（基于榜单）
        genre_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "views": 0,
            "trends": [],
            "ai_count": 0,
            "female_count": 0,
            "male_count": 0
        })
        
        total_views = 0
        
        for drama in rankings:
            genre = drama.genre if drama.genre else "其他"
            views = drama.views_num if drama.views_num else 0
            trend = drama.trend_type if drama.trend_type else "same"
            is_ai = drama.is_ai if drama.is_ai else False
            category = drama.category if drama.category else "female"
            
            genre_stats[genre]["count"] += 1
            genre_stats[genre]["views"] += views
            genre_stats[genre]["trends"].append(trend)
            
            if is_ai:
                genre_stats[genre]["ai_count"] += 1
            
            if category == "female":
                genre_stats[genre]["female_count"] += 1
            elif category == "male":
                genre_stats[genre]["male_count"] += 1
            
            total_views += views
        
        # 计算各题材的趋势
        result_genres: List[GenreStat] = []
        
        for genre_name, stats in genre_stats.items():
            trends = stats["trends"]
            up_count = trends.count("up")
            down_count = trends.count("down")
            
            if up_count > down_count and up_count > len(trends) / 2:
                trend = "up"
            elif down_count > up_count and down_count > len(trends) / 2:
                trend = "down"
            else:
                trend = "same"
            
            share = round(stats["views"] / total_views * 100, 1) if total_views > 0 else 0
            
            genre_stat = GenreStat(
                name=genre_name,
                count=stats["count"],
                views=stats["views"],
                share=share,
                trend=trend,
                ai_count=stats["ai_count"],
                female_count=stats["female_count"],
                male_count=stats["male_count"]
            )
            result_genres.append(genre_stat)
        
        result_genres.sort(key=lambda x: x.views, reverse=True)
        
        # 2. 分析标签数据（基于搜索结果）
        background_tag_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "views": 0})
        theme_tag_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "views": 0})
        setting_tag_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "views": 0})
        
        # 从搜索结果中提取标签数据
        tag_raw_content = ""
        for result in search_results:
            if isinstance(result, dict) and result.get("type") == "tag_data":
                tag_raw_content = result.get("raw_content", "")
                logger.info(f"找到标签数据，长度: {len(tag_raw_content)}")
                break
        
        if not tag_raw_content:
            # 如果没有专门的标签数据，尝试从第一个搜索结果中提取
            for result in search_results:
                if isinstance(result, dict) and result.get("raw_content"):
                    tag_raw_content = result.get("raw_content", "")
                    logger.info(f"使用综合搜索结果提取标签，长度: {len(tag_raw_content)}")
                    break
        
        if tag_raw_content:
            # 简化方法：直接统计标签关键词在文本中出现的次数
            # 统计背景标签
            for tag in BACKGROUND_TAGS:
                count = len(re.findall(rf'{tag}', tag_raw_content))
                if count > 0:
                    background_tag_stats[tag]["count"] = count
                    background_tag_stats[tag]["views"] = count * 100  # 估算
            
            # 统计主题标签
            for tag in THEME_TAGS:
                count = len(re.findall(rf'{tag}', tag_raw_content))
                if count > 0:
                    theme_tag_stats[tag]["count"] = count
                    theme_tag_stats[tag]["views"] = count * 100
            
            # 统计设定标签
            for tag in SETTING_TAGS:
                count = len(re.findall(rf'{tag}', tag_raw_content))
                if count > 0:
                    setting_tag_stats[tag]["count"] = count
                    setting_tag_stats[tag]["views"] = count * 100
            
            # 如果正则匹配失败，尝试从榜单的tags字段统计
            if not any(stats["count"] for stats in background_tag_stats.values()):
                for drama in rankings:
                    if hasattr(drama, 'tags') and drama.tags:
                        for tag in drama.tags:
                            if tag in BACKGROUND_TAGS:
                                background_tag_stats[tag]["count"] += 1
                                background_tag_stats[tag]["views"] += drama.views_num if drama.views_num else 0
                            elif tag in THEME_TAGS:
                                theme_tag_stats[tag]["count"] += 1
                                theme_tag_stats[tag]["views"] += drama.views_num if drama.views_num else 0
                            elif tag in SETTING_TAGS:
                                setting_tag_stats[tag]["count"] += 1
                                setting_tag_stats[tag]["views"] += drama.views_num if drama.views_num else 0
        
        # 如果榜单也没有标签，从core_trope字段统计
        if not any(stats["count"] for stats in setting_tag_stats.values()):
            for drama in rankings:
                if hasattr(drama, 'core_trope') and drama.core_trope:
                    for trope in drama.core_trope:
                        setting_tag_stats[trope]["count"] += 1
                        setting_tag_stats[trope]["views"] += drama.views_num if drama.views_num else 0
        
        # 构建标签热度列表
        background_tags: List[TagHeat] = []
        for tag_name, stats in background_tag_stats.items():
            if stats["count"] > 0:
                avg_views = stats["views"] // stats["count"] if stats["count"] > 0 else 0
                heat = stats["count"] * 10 + avg_views // 100  # 简化的热度计算
                background_tags.append(TagHeat(
                    name=tag_name,
                    category="背景",
                    count=stats["count"],
                    avg_views=avg_views,
                    heat=heat
                ))
        background_tags.sort(key=lambda x: x.heat, reverse=True)
        
        theme_tags: List[TagHeat] = []
        for tag_name, stats in theme_tag_stats.items():
            if stats["count"] > 0:
                avg_views = stats["views"] // stats["count"] if stats["count"] > 0 else 0
                heat = stats["count"] * 10 + avg_views // 100
                theme_tags.append(TagHeat(
                    name=tag_name,
                    category="主题",
                    count=stats["count"],
                    avg_views=avg_views,
                    heat=heat
                ))
        theme_tags.sort(key=lambda x: x.heat, reverse=True)
        
        setting_tags: List[TagHeat] = []
        for tag_name, stats in setting_tag_stats.items():
            if stats["count"] > 0:
                avg_views = stats["views"] // stats["count"] if stats["count"] > 0 else 0
                heat = stats["count"] * 10 + avg_views // 100
                setting_tags.append(TagHeat(
                    name=tag_name,
                    category="设定",
                    count=stats["count"],
                    avg_views=avg_views,
                    heat=heat
                ))
        setting_tags.sort(key=lambda x: x.heat, reverse=True)
        
        # 确定最热门和上升最快标签
        all_tags = background_tags + theme_tags + setting_tags
        top_tag = all_tags[0].name if all_tags else ""
        rising_tag = ""
        for tag in all_tags:
            if tag.heat > 0 and tag != all_tags[0]:
                rising_tag = tag.name
                break
        
        logger.info(f"题材分布统计完成: {len(result_genres)}个题材, {len(background_tags)}个背景标签, {len(theme_tags)}个主题标签, {len(setting_tags)}个设定标签")
        
        # 构建GenreDistribution对象返回
        genre_distribution = GenreDistribution(
            genres=[GenreStats(name=g.name, count=g.count, total_views=str(g.views), trend=g.trend) for g in result_genres[:10]],
            top_genre=result_genres[0].name if result_genres else "",
            rising_genre=result_genres[1].name if len(result_genres) > 1 else "",
            background_tags=background_tags[:10],  # TOP10
            theme_tags=theme_tags[:10],
            setting_tags=setting_tags[:10],
            top_tag=top_tag,
            rising_tag=rising_tag
        )
        
        return GenreDistributionOutput(
            genre_distribution=genre_distribution,
            total_count=len(rankings),
            total_views=total_views,
            error_message=input_error_message
        )
        
    except Exception as e:
        error_message = f"genre_distribution_node: 统计题材分布失败: {e}"
        logger.error(error_message, exc_info=True)
        return GenreDistributionOutput(
            genre_distribution=GenreDistribution(),
            total_count=0,
            total_views=0,
            error_message=error_message + "\n"
        )