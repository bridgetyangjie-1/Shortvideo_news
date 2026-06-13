"""
历史数据与趋势相关模型
"""
from typing import List, Optional
from pydantic import BaseModel, Field

from graphs.models.ranking import DramaRanking


class OverviewStats(BaseModel):
    """概览统计数据（Dashboard页面1所需）"""
    dramas: int = Field(default=0, description="周期内开播剧集数")
    heat: float = Field(default=0.0, description="平均热度指数")
    roi: float = Field(default=2.3, description="平均ROI（估算）")
    hitRate: int = Field(default=0, description="爆款率(%)")
    dramasChange: int = Field(default=0, description="剧集数环比变化(%)")
    heatChange: float = Field(default=0.0, description="热度环比变化(%)")
    roiChange: float = Field(default=0.0, description="ROI环比变化(%)")
    hitRateChange: int = Field(default=0, description="爆款率环比变化(%)")


class WeeklyRankingItem(BaseModel):
    """周榜条目"""
    week: str = Field(default="", description="周次（如2026-W21）")
    start_date: str = Field(default="", description="周开始日期")
    end_date: str = Field(default="", description="周结束日期")
    top1_title: str = Field(default="", description="周冠军剧名")
    top1_views: str = Field(default="", description="周冠军播放量")
    total_views: int = Field(default=0, description="本周总播放量")


class DailyPlayTrend(BaseModel):
    """每日播放趋势"""
    date: str = Field(default="", description="日期")
    total_views: int = Field(default=0, description="总播放量")


class PlayTrend(BaseModel):
    """播放量趋势"""
    daily: List[DailyPlayTrend] = Field(default=[], description="每日数据")
    weekly: List[WeeklyRankingItem] = Field(default=[], description="每周数据")
    trend_direction: str = Field(default="stable", description="整体趋势：up/down/stable")


class HistoryData(BaseModel):
    """历史数据"""
    weekly_rankings: List[WeeklyRankingItem] = Field(default=[], description="周榜历史")
    daily_play_trend: List[DailyPlayTrend] = Field(default=[], description="每日播放趋势")


class DailyPlayData(BaseModel):
    """每日播放数据"""
    date: str = Field(default="", description="日期")
    total_views: int = Field(default=0, description="总播放量")


class WeeklyPlayData(BaseModel):
    """每周播放数据"""
    week: str = Field(default="", description="周次")
    total_views: int = Field(default=0, description="总播放量")


class RankChange(BaseModel):
    """排名变化条目"""
    title: str = Field(default="", description="剧名")
    current_rank: int = Field(default=0, description="当前排名")
    previous_rank: Optional[int] = Field(default=None, description="昨日排名，None表示昨日不在榜")
    change_type: str = Field(default="new", description="变化类型：new/up/down/stable")
    change_value: int = Field(default=0, description="变化幅度")


class HistoryDataInput(BaseModel):
    """历史数据节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class HistoryDataOutput(BaseModel):
    """历史数据节点输出"""
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    weekly_rankings: List[WeeklyRankingItem] = Field(default=[], description="周榜历史")
    rank_changes: List[RankChange] = Field(default=[], description="排名变化分析")
    error_message: str = Field(default="", description="错误信息")
