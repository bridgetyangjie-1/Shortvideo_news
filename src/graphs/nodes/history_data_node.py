"""
历史数据生成节点
功能：生成周榜历史和播放量趋势数据
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import (
    HistoryDataInput,
    HistoryDataOutput,
    PlayTrend,
    DailyPlayTrend,
    WeeklyRankingItem
)


def history_data_node(
    state: HistoryDataInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> HistoryDataOutput:
    """
    title: 历史数据生成
    desc: 基于当前榜单数据生成周榜历史和播放量趋势
    integrations: 无
    """
    # 获取当前数据
    rankings = state.enriched_rankings
    data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
    
    # 历史数据文件路径
    history_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "."), "assets", "history_data.json")
    
    # 读取历史数据
    history_data: Dict[str, Any] = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            history_data = {}
    
    # 计算当日总播放量
    total_views = sum(r.views_num for r in rankings if r.views_num > 0)
    
    # 计算周信息
    date_obj = datetime.strptime(data_date, "%Y-%m-%d")
    week_start = date_obj - timedelta(days=date_obj.weekday())
    week_end = week_start + timedelta(days=6)
    week_str = date_obj.strftime("%Y-W%W")
    
    # ========== 1. 更新每日播放趋势 ==========
    daily_records: List[Dict[str, Any]] = history_data.get("daily_play_trend", [])
    
    # 更新或添加当日数据
    today_record = {"date": data_date, "total_views": total_views}
    daily_updated = False
    for i, record in enumerate(daily_records):
        if record.get("date") == data_date:
            daily_records[i] = today_record
            daily_updated = True
            break
    
    if not daily_updated:
        daily_records.append(today_record)
    
    # 只保留最近30天
    daily_records = sorted(daily_records, key=lambda x: x["date"], reverse=True)[:30]
    
    # ========== 2. 更新周榜数据 ==========
    weekly_records: List[Dict[str, Any]] = history_data.get("weekly_rankings", [])
    
    # 获取TOP1信息
    top1_title = rankings[0].title if rankings and len(rankings) > 0 else ""
    top1_views = rankings[0].views if rankings and len(rankings) > 0 else ""
    
    week_record: Dict[str, Any] = {
        "week": week_str,
        "start_date": week_start.strftime("%Y-%m-%d"),
        "end_date": week_end.strftime("%Y-%m-%d"),
        "top1_title": top1_title,
        "top1_views": top1_views,
        "total_views": total_views
    }
    
    # 检查本周是否已有记录
    week_exists = False
    for i, record in enumerate(weekly_records):
        if record.get("week") == week_str:
            weekly_records[i] = week_record
            week_exists = True
            break
    
    if not week_exists:
        weekly_records.append(week_record)
    
    # 只保留最近12周
    weekly_records = sorted(weekly_records, key=lambda x: x["week"], reverse=True)[:12]
    
    # ========== 3. 保存历史数据 ==========
    history_data["daily_play_trend"] = daily_records
    history_data["weekly_rankings"] = weekly_records
    history_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        pass  # 保存失败不影响返回
    
    # ========== 4. 构建输出数据 ==========
    # 构建每日播放趋势
    daily_trend: List[DailyPlayTrend] = []
    for record in daily_records:
        daily_trend.append(DailyPlayTrend(
            date=record.get("date", ""),
            total_views=record.get("total_views", 0)
        ))
    
    # 构建周榜数据
    weekly_trend: List[WeeklyRankingItem] = []
    for record in weekly_records:
        weekly_trend.append(WeeklyRankingItem(
            week=record.get("week", ""),
            start_date=record.get("start_date", ""),
            end_date=record.get("end_date", ""),
            top1_title=record.get("top1_title", ""),
            top1_views=record.get("top1_views", ""),
            total_views=record.get("total_views", 0)
        ))
    
    # 计算趋势方向
    trend_direction = "stable"
    if len(daily_trend) >= 14:
        recent_avg = sum(d.total_views for d in daily_trend[:7]) / 7
        older_avg = sum(d.total_views for d in daily_trend[7:14]) / 7
        if recent_avg > older_avg * 1.1:
            trend_direction = "up"
        elif recent_avg < older_avg * 0.9:
            trend_direction = "down"
    elif len(daily_trend) >= 2:
        # 数据不足14天时，简单比较前半段和后半段
        mid = len(daily_trend) // 2
        recent_avg = sum(d.total_views for d in daily_trend[:mid]) / max(1, mid)
        older_avg = sum(d.total_views for d in daily_trend[mid:]) / max(1, len(daily_trend) - mid)
        if recent_avg > older_avg * 1.1:
            trend_direction = "up"
        elif recent_avg < older_avg * 0.9:
            trend_direction = "down"
    
    play_trend = PlayTrend(
        daily=daily_trend,
        weekly=weekly_trend,
        trend_direction=trend_direction
    )
    
    return HistoryDataOutput(
        play_trend=play_trend,
        weekly_rankings=weekly_trend
    )
