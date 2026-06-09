import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from utils.runtime import Context

from graphs.state import (
    GenreDistributionInput,
    GenreDistributionOutput,
    GenreStat
)

logger = logging.getLogger(__name__)


def genre_distribution_node(
    state: GenreDistributionInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> GenreDistributionOutput:
    """
    title: 📊 统计题材分布
    desc: 基于榜单数据统计各题材的数量、播放量和趋势
    integrations: 无
    """
    ctx = runtime.context
    
    try:
        # 获取榜单数据
        rankings = state.enriched_rankings if state.enriched_rankings else []
        
        if not rankings:
            return GenreDistributionOutput(
                genres=[],
                total_count=0,
                total_views=0
            )
        
        # 统计各题材数据
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
            # 使用属性访问而非 .get()
            genre = drama.genre if drama.genre else "其他"
            views = drama.views_num if drama.views_num else 0
            trend = drama.trend_type if drama.trend_type else "same"
            is_ai = drama.is_ai if drama.is_ai else False
            category = drama.category if drama.category else "female"
            
            # 更新统计
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
            # 计算主要趋势
            trends = stats["trends"]
            up_count = trends.count("up")
            down_count = trends.count("down")
            
            if up_count > down_count and up_count > len(trends) / 2:
                trend = "up"
            elif down_count > up_count and down_count > len(trends) / 2:
                trend = "down"
            else:
                trend = "same"
            
            # 计算播放量占比
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
        
        # 按播放量排序
        result_genres.sort(key=lambda x: x.views, reverse=True)
        
        return GenreDistributionOutput(
            genres=result_genres,
            total_count=len(rankings),
            total_views=total_views
        )
        
    except Exception as e:
        logger.error(f"统计题材分布失败: {str(e)}")
        return GenreDistributionOutput(
            genres=[],
            total_count=0,
            total_views=0
        )
