"""
各节点输入输出模型
"""
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from graphs.models.ranking import DramaRanking, ActorsData
from graphs.models.industry import IndustryData, PlatformData
from graphs.models.audience import AudienceProfile
from graphs.models.genre import GenreDistribution, GenreStat
from graphs.models.emotion import EmotionalAnalysis, default_emotional_analysis
from graphs.models.history import PlayTrend, WeeklyRankingItem, RankChange
from graphs.models.news import DailyNews, Insight
from graphs.models.alerts import AlertItem
from graphs.models.ai_drama import AIDramaDashboard


class SearchNodeInput(BaseModel):
    """数据抓取节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)，空则使用当前日期")


class SearchNodeOutput(BaseModel):
    """数据抓取节点输出"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    search_results: List[Dict[str, Any]] = Field(default=[], description="搜索结果列表")
    error_message: str = Field(default="", description="错误信息")


class ProcessNodeInput(BaseModel):
    """初步处理节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    search_results: List[Dict[str, Any]] = Field(default=[], description="搜索结果列表")


class ProcessNodeOutput(BaseModel):
    """初步处理节点输出"""
    basic_rankings: List[Dict[str, Any]] = Field(default=[], description="基础榜单数据")
    quality_score: float = Field(default=0.0, description="数据质量分数")
    error_message: str = Field(default="", description="错误信息")


class EnrichNodeInput(BaseModel):
    """数据补充节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    basic_rankings: List[Dict[str, Any]] = Field(default=[], description="基础榜单数据")
    search_results: List[Dict[str, Any]] = Field(default=[], description="search_node 原始结果（复用红果 catalog）")


class EnrichNodeOutput(BaseModel):
    """数据补充节点输出"""
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")
    error_message: str = Field(default="", description="错误信息")


class ActorRankingNodeInput(BaseModel):
    """演员榜单生成节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class ActorRankingNodeOutput(BaseModel):
    """演员榜单生成节点输出"""
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    error_message: str = Field(default="", description="错误信息")


class IndustryNodeInput(BaseModel):
    """行业数据节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class IndustryNodeOutput(BaseModel):
    """行业数据节点输出"""
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    error_message: str = Field(default="", description="错误信息")


class InsightsNodeInput(BaseModel):
    """洞察生成节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="榜单数据")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员数据")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")


class InsightsNodeOutput(BaseModel):
    """洞察生成节点输出"""
    insights: List[Insight] = Field(default=[], description="异动点评列表")
    error_message: str = Field(default="", description="错误信息")


class NewsNodeInput(BaseModel):
    """每日快讯节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")


class NewsNodeOutput(BaseModel):
    """每日快讯节点输出"""
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    error_message: str = Field(default="", description="错误信息")


class AIDramaNodeInput(BaseModel):
    """AI 短剧/漫剧看板节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")


class AIDramaNodeOutput(BaseModel):
    """AI 短剧/漫剧看板节点输出"""
    ai_drama_dashboard: AIDramaDashboard = Field(default_factory=AIDramaDashboard, description="AI 短剧/漫剧看板")
    error_message: str = Field(default="", description="错误信息")


class PushNodeInput(BaseModel):
    """数据推送节点输入"""
    success: bool = Field(default=True, description="是否通过质量门禁")
    generated_at: str = Field(default="", description="生成时间")
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="榜单数据")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    insights: List[Insight] = Field(default=[], description="异动点评列表")
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签")
    emotional_analysis: EmotionalAnalysis = Field(
        default_factory=default_emotional_analysis,
        description="核心情绪与动机拆解",
    )
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    rank_changes: List[RankChange] = Field(default=[], description="排名变化分析")
    alerts: List[AlertItem] = Field(default_factory=list, description="异常监测告警列表")
    alert_count: int = Field(default=0, description="告警数量")
    quality_report: Dict[str, Any] = Field(default_factory=dict, description="质量门禁详细报告")
    quality_score: float = Field(default=0.0, description="数据质量分数")
    ai_drama_dashboard: AIDramaDashboard = Field(default_factory=AIDramaDashboard, description="AI 短剧/漫剧看板")
    error_message: str = Field(default="", description="错误信息")


class PushNodeOutput(BaseModel):
    """数据推送节点输出"""
    success: bool = Field(default=True, description="是否成功")
    generated_at: str = Field(default="", description="生成时间")
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    rankings: List[DramaRanking] = Field(default=[], description="榜单数据")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    insights: List[Insight] = Field(default=[], description="异动点评列表")
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签")
    emotional_analysis: EmotionalAnalysis = Field(
        default_factory=default_emotional_analysis,
        description="核心情绪与动机拆解",
    )
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    alerts: List[AlertItem] = Field(default_factory=list, description="异常监测告警列表")
    alert_count: int = Field(default=0, description="告警数量")
    quality_report: Dict[str, Any] = Field(default_factory=dict, description="质量门禁详细报告")
    quality_score: float = Field(default=0.0, description="数据质量分数")
    ai_drama_dashboard: AIDramaDashboard = Field(default_factory=AIDramaDashboard, description="AI 短剧/漫剧看板")
    error_message: str = Field(default="", description="错误信息")
    storage_url: str = Field(default="", description="对象存储URL（用于GitHub同步）")
    storage_key: str = Field(default="", description="对象存储Key（持久化存储）")
    output_path: str = Field(default="", description="本地输出文件路径")


class QualityGateInput(BaseModel):
    """数据质量门禁节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default_factory=list, description="补充后的完整榜单")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    daily_news: List[DailyNews] = Field(default_factory=list, description="每日行业快讯")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    insights: List[Insight] = Field(default_factory=list, description="异动点评列表")
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签")
    emotional_analysis: EmotionalAnalysis = Field(
        default_factory=default_emotional_analysis,
        description="核心情绪与动机拆解",
    )
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    ai_drama_dashboard: AIDramaDashboard = Field(default_factory=AIDramaDashboard, description="AI 短剧/漫剧看板")
    quality_score: float = Field(default=0.0, description="当前数据质量分数")
    error_message: str = Field(default="", description="上游错误信息")


class QualityGateOutput(BaseModel):
    """数据质量门禁节点输出"""
    success: bool = Field(default=True, description="是否通过质量门禁")
    quality_score: float = Field(default=0.0, description="重新计算后的数据质量分数 (0-100)")
    quality_report: Dict[str, Any] = Field(default_factory=dict, description="质量门禁详细报告")
    error_message: str = Field(default="", description="错误/告警信息")


class AlertNodeInput(BaseModel):
    """异常监测节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default_factory=list, description="补充后的完整榜单")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    daily_news: List[DailyNews] = Field(default_factory=list, description="每日行业快讯")
    insights: List[Insight] = Field(default_factory=list, description="异动点评列表")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签")
    emotional_analysis: EmotionalAnalysis = Field(
        default_factory=default_emotional_analysis,
        description="核心情绪与动机拆解",
    )
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    quality_score: float = Field(default=0.0, description="数据质量分数")
    quality_report: Dict[str, Any] = Field(default_factory=dict, description="质量门禁详细报告")
    error_message: str = Field(default="", description="上游错误信息")


class AlertNodeOutput(BaseModel):
    """异常监测节点输出"""
    alerts: List[AlertItem] = Field(default_factory=list, description="异常监测告警列表")
    alert_count: int = Field(default=0, description="告警数量")
    error_message: str = Field(default="", description="错误信息")


class ShouldPushInput(BaseModel):
    """是否推送数据判断输入"""
    quality_score: float = Field(..., description="数据质量分数")
    success: bool = Field(..., description="数据处理是否成功")


class GenderDistribution(BaseModel):
    """性别分布"""
    female: int = Field(default=0, description="女性占比")
    male: int = Field(default=0, description="男性占比")


class AudienceProfileInput(BaseModel):
    """观众画像节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default_factory=list, description="补充后的完整榜单")


class AudienceProfileOutput(BaseModel):
    """观众画像节点输出"""
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    error_message: str = Field(default="", description="错误信息")


class GenreDistributionInput(BaseModel):
    """热门标签节点输入"""
    data_date: str = Field(default="", description="数据日期 YYYY-MM-DD")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class GenreDistributionOutput(BaseModel):
    """热门标签节点输出"""
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签数据")
    total_count: int = Field(default=0, description="总短剧数")
    total_views: int = Field(default=0, description="总播放量(万)")
    error_message: str = Field(default="", description="错误信息")


class EmotionAnalysisNodeInput(BaseModel):
    """情绪分析节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default_factory=list, description="补充后的完整榜单")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签")


class EmotionAnalysisNodeOutput(BaseModel):
    """情绪分析节点输出"""
    emotional_analysis: EmotionalAnalysis = Field(default_factory=default_emotional_analysis, description="核心情绪与动机拆解")
    success: bool = Field(default=True, description="是否成功")
    error_message: str = Field(default="", description="错误信息")
