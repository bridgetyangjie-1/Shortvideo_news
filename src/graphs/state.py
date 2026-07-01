"""
短剧行业研究数据自动更新工作流 - 状态定义入口

本文件仅保留全局状态与工作流输入输出，所有领域模型已拆分至 graphs/models/ 下。
为保持向后兼容，仍通过 re-export 暴露所有模型。
"""
import operator
from typing import Any, Dict, List, Optional, Annotated
from pydantic import BaseModel, Field

from graphs.models.ranking import DramaRanking, ActorRanking, ActorsData
from graphs.models.industry import IndustryData, PlatformData, PlatformApp
from graphs.models.audience import AudienceProfile, AgeDistribution, RegionDistribution
from graphs.models.genre import GenreDistribution, TagItem, TagCategory, TrendingTag, GenreStats
from graphs.models.emotion import (
    EmotionalAnalysis,
    EmotionWordCloudItem,
    EmotionRankingItem,
    EmotionTrendItem,
    ActionableInsight,
    default_emotional_analysis,
)
from graphs.models.history import (
    OverviewStats,
    WeeklyRankingItem,
    DailyPlayTrend,
    PlayTrend,
    HistoryData,
    DailyPlayData,
    WeeklyPlayData,
    RankChange,
    HistoryDataInput,
    HistoryDataOutput,
)
from graphs.models.news import Insight, Innovation, DailyNews
from graphs.models.alerts import AlertItem
from graphs.models.ai_drama import AIDramaDashboard
from graphs.models.node_io import (
    SearchNodeInput,
    SearchNodeOutput,
    ProcessNodeInput,
    ProcessNodeOutput,
    EnrichNodeInput,
    EnrichNodeOutput,
    ActorRankingNodeInput,
    ActorRankingNodeOutput,
    IndustryNodeInput,
    IndustryNodeOutput,
    InsightsNodeInput,
    InsightsNodeOutput,
    NewsNodeInput,
    NewsNodeOutput,
    AIDramaNodeInput,
    AIDramaNodeOutput,
    PushNodeInput,
    PushNodeOutput,
    ShouldPushInput,
    QualityGateInput,
    QualityGateOutput,
    AlertNodeInput,
    AlertNodeOutput,
    GenderDistribution,
    AudienceProfileInput,
    AudienceProfileOutput,
    GenreStat,
    GenreDistributionInput,
    GenreDistributionOutput,
    EmotionAnalysisNodeInput,
    EmotionAnalysisNodeOutput,
)


class GlobalState(BaseModel):
    """全局状态定义"""
    success: bool = Field(default=True, description="整体工作流是否成功")
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    search_results: List[Dict[str, Any]] = Field(default=[], description="搜索结果原始数据")
    basic_rankings: List[Dict[str, Any]] = Field(default=[], description="基础榜单数据（初步提取）")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    insights: List[Insight] = Field(default=[], description="异动点评列表（最多2条）")
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签")
    emotional_analysis: EmotionalAnalysis = Field(
        default_factory=default_emotional_analysis,
        description="核心情绪与动机拆解",
    )
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    weekly_rankings: List[WeeklyRankingItem] = Field(default=[], description="周榜历史")
    rank_changes: List[RankChange] = Field(default=[], description="排名变化分析")
    quality_report: Dict[str, Any] = Field(default_factory=dict, description="质量门禁详细报告")
    quality_score: float = Field(default=0.0, description="数据质量分数 (0-100)")
    alerts: List[AlertItem] = Field(default_factory=list, description="异常监测告警列表")
    alert_count: int = Field(default=0, description="告警数量")
    ai_drama_dashboard: AIDramaDashboard = Field(default_factory=AIDramaDashboard, description="AI 短剧/漫剧看板")
    error_message: Annotated[str, operator.add] = Field(default="", description="错误信息")


class GraphInput(BaseModel):
    """工作流输入"""
    data_date: Optional[str] = Field(
        default=None,
        description="数据日期 (YYYY-MM-DD)，不传则使用当前日期",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="周期开始日期 (YYYY-MM-DD)，用于周期统计",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="周期结束日期 (YYYY-MM-DD)，用于周期统计",
    )


class GraphOutput(BaseModel):
    """工作流输出"""
    success: Annotated[bool, "merge"] = Field(..., description="是否成功")
    generated_at: str = Field(..., description="生成时间")
    data_date: str = Field(..., description="数据日期")
    period: str = Field(default="", description="数据周期（如 2026-05-15_2026-05-21）")
    overview: OverviewStats = Field(default_factory=OverviewStats, description="概览统计数据")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签数据")
    emotional_analysis: EmotionalAnalysis = Field(
        default_factory=default_emotional_analysis,
        description="核心情绪与动机拆解",
    )
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    rankings: List[DramaRanking] = Field(default=[], description="榜单数据")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    weekly_rankings: List[WeeklyRankingItem] = Field(default=[], description="周榜历史")
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    insights: List[Insight] = Field(default=[], description="异动点评列表")
    quality_report: Dict[str, Any] = Field(default_factory=dict, description="质量门禁详细报告")
    quality_score: float = Field(default=0.0, description="数据质量分数")
    alerts: List[AlertItem] = Field(default_factory=list, description="异常监测告警列表")
    alert_count: int = Field(default=0, description="告警数量")
    ai_drama_dashboard: AIDramaDashboard = Field(default_factory=AIDramaDashboard, description="AI 短剧/漫剧看板")
    error_message: str = Field(default="", description="错误信息")
