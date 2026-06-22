"""
历史数据生成节点
功能：生成周榜历史、周榜热度趋势数据、排名变化分析

注意：当前主数据源为短剧工程周榜（每周一更新），因此“趋势”以周为粒度，
不再把同一周的热度重复写入每日记录，避免平线和 0 值噪音。
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import (
    HistoryDataInput,
    HistoryDataOutput,
    PlayTrend,
    DailyPlayTrend,
    WeeklyRankingItem,
    RankChange
)

logger = logging.getLogger(__name__)


def _week_start(date_obj: datetime) -> datetime:
    """返回 date_obj 所在周的周一"""
    return date_obj - timedelta(days=date_obj.weekday())


def _derive_daily_from_weekly(weekly_records: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    """从周榜记录派生趋势点：每个点代表一周，日期为周一，数值为当周总热度"""
    daily = []
    for record in weekly_records:
        start = record.get("start_date", "")
        total = record.get("total_views", 0)
        if start:
            daily.append({"date": start, "total_views": total})
    daily = sorted(daily, key=lambda x: x["date"], reverse=True)[:limit]
    return daily


def history_data_node(
    state: HistoryDataInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> HistoryDataOutput:
    """
    title: 历史数据生成
    desc: 基于当前榜单数据生成周榜历史和周榜热度趋势
    integrations: 无
    """
    rankings = state.enriched_rankings
    data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
    error_messages: List[str] = []
    if not rankings:
        error_messages.append("history_data_node: enriched_rankings 为空，当日周榜数据将记录为 0；请检查 enrich_node。")

    history_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "."), "assets", "history_data.json")

    history_data: Dict[str, Any] = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            history_data = {}

    date_obj = datetime.strptime(data_date, "%Y-%m-%d")
    week_start = _week_start(date_obj)
    week_end = week_start + timedelta(days=6)
    week_str = date_obj.strftime("%Y-W%W")
    week_start_str = week_start.strftime("%Y-%m-%d")

    # 计算本周总热度（取 weekly_index / views_num）
    total_views = sum(r.views_num for r in rankings if r.views_num > 0)

    # TOP1 信息
    top1_title = rankings[0].title if rankings and len(rankings) > 0 else ""
    top1_views = rankings[0].views if rankings and len(rankings) > 0 else ""

    # ========== 1. 更新周榜数据 ==========
    weekly_records: List[Dict[str, Any]] = history_data.get("weekly_rankings", [])

    week_record: Dict[str, Any] = {
        "week": week_str,
        "start_date": week_start_str,
        "end_date": week_end.strftime("%Y-%m-%d"),
        "top1_title": top1_title,
        "top1_views": top1_views,
        "total_views": total_views,
    }

    existing_index: Optional[int] = None
    for i, record in enumerate(weekly_records):
        if record.get("week") == week_str:
            existing_index = i
            break

    if existing_index is not None:
        existing = weekly_records[existing_index]
        # 仅当新数据有有效热度，或旧记录本身为 0 时才覆盖，避免可用数据被失败运行冲掉
        if total_views > 0 or existing.get("total_views", 0) == 0:
            weekly_records[existing_index] = week_record
        else:
            logger.info(f"本周 {week_str} 已有非零周榜记录，跳过 0 值覆盖")
    else:
        weekly_records.append(week_record)

    # 只保留最近 12 周
    weekly_records = sorted(weekly_records, key=lambda x: x["week"], reverse=True)[:12]

    # ========== 2. 派生每日趋势（实际是每周一个点） ==========
    daily_records = _derive_daily_from_weekly(weekly_records, limit=8)

    history_data["daily_play_trend"] = daily_records
    history_data["weekly_rankings"] = weekly_records
    history_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        error_messages.append(f"history_data_node: 保存历史趋势文件失败: {e}")

    # ========== 3. 构建输出数据 ==========
    daily_trend: List[DailyPlayTrend] = [
        DailyPlayTrend(date=r.get("date", ""), total_views=r.get("total_views", 0))
        for r in daily_records
    ]

    weekly_trend: List[WeeklyRankingItem] = []
    for record in weekly_records:
        weekly_trend.append(WeeklyRankingItem(
            week=record.get("week", ""),
            start_date=record.get("start_date", ""),
            end_date=record.get("end_date", ""),
            top1_title=record.get("top1_title", ""),
            top1_views=record.get("top1_views", ""),
            total_views=record.get("total_views", 0),
        ))

    # 趋势方向：近 4 周 vs 再往前 4 周
    trend_direction = "stable"
    if len(weekly_trend) >= 8:
        recent_avg = sum(w.total_views for w in weekly_trend[:4]) / 4
        older_avg = sum(w.total_views for w in weekly_trend[4:8]) / 4
        if older_avg > 0:
            if recent_avg > older_avg * 1.05:
                trend_direction = "up"
            elif recent_avg < older_avg * 0.95:
                trend_direction = "down"
    elif len(weekly_trend) >= 2:
        recent = weekly_trend[0].total_views
        older = weekly_trend[1].total_views
        if older > 0:
            if recent > older * 1.05:
                trend_direction = "up"
            elif recent < older * 0.95:
                trend_direction = "down"

    play_trend = PlayTrend(
        daily=daily_trend,
        weekly=weekly_trend,
        trend_direction=trend_direction,
    )

    # ========== 4. 计算排名变化 ==========
    rank_changes: List[RankChange] = []

    yesterday_date = (datetime.strptime(data_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "."), "assets", "data", "history", f"{yesterday_date}.json")

    yesterday_rankings: Dict[str, int] = {}
    if os.path.exists(yesterday_file):
        try:
            with open(yesterday_file, "r", encoding="utf-8") as f:
                yesterday_data = json.load(f)
                for i, item in enumerate(yesterday_data.get("rankings", [])[:20]):
                    title = item.get("title", "")
                    if title:
                        yesterday_rankings[title] = i + 1
        except Exception as e:
            error_messages.append(f"history_data_node: 读取昨日榜单失败: {e}")

    for i, r in enumerate(rankings[:20]):
        title = r.title if hasattr(r, "title") else ""
        current_rank = i + 1

        if title in yesterday_rankings:
            prev_rank = yesterday_rankings[title]
            if current_rank < prev_rank:
                change_type = "up"
                change_value = prev_rank - current_rank
            elif current_rank > prev_rank:
                change_type = "down"
                change_value = current_rank - prev_rank
            else:
                change_type = "stable"
                change_value = 0
        else:
            change_type = "new"
            change_value = 0

        rank_changes.append(RankChange(
            title=title,
            current_rank=current_rank,
            previous_rank=yesterday_rankings.get(title),
            change_type=change_type,
            change_value=change_value,
        ))

    new_count = sum(1 for rc in rank_changes if rc.change_type == "new")
    up_count = sum(1 for rc in rank_changes if rc.change_type == "up")
    down_count = sum(1 for rc in rank_changes if rc.change_type == "down")
    stable_count = sum(1 for rc in rank_changes if rc.change_type == "stable")

    logger.info(f"排名变化统计: 新上榜{new_count}部, 上升{up_count}部, 下降{down_count}部, 持平{stable_count}部")

    return HistoryDataOutput(
        play_trend=play_trend,
        weekly_rankings=weekly_trend,
        rank_changes=rank_changes,
        error_message=("\n".join(error_messages) + "\n") if error_messages else "",
    )
