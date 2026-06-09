"""
短剧行业研究数据自动更新工作流 - 状态定义
"""
import operator
from typing import Optional, List, Dict, Any, Annotated
from pydantic import BaseModel, Field
from datetime import datetime


# ==================== 数据结构定义 ====================

class DramaRanking(BaseModel):
    """短剧榜单条目"""
    rank: int = Field(..., description="排名")
    title: str = Field(..., description="剧名")
    female_lead: str = Field(default="", description="女演员名")
    male_lead: str = Field(default="", description="男演员名")
    views: str = Field(default="", description="播放量（如'1.5亿'）")
    views_num: int = Field(default=0, description="播放量数字，单位万，方便排序")
    platform: str = Field(default="红果", description="平台")
    genre: str = Field(default="", description="题材类型")
    tags: List[str] = Field(default=[], description="标签列表")
    trend: str = Field(default="", description="趋势描述")
    trend_type: str = Field(default="same", description="趋势类型：new/up/down/same")
    category: str = Field(default="female", description="分类：female/male/ai")
    is_ai: bool = Field(default=False, description="是否为AI剧")
    desc: str = Field(default="", description="剧情描述")
    change: str = Field(default="", description="排名变化：new/up1/down2/same")
    heat: int = Field(default=0, description="热度值（播放量加权计算）")
    # 🚨 新增商业信息字段（enrich_node补全）
    production_house: str = Field(default="", description="制作厂牌（如九州、点众、麦芽）")
    core_trope: List[str] = Field(default=[], description="核心爽点标签（如真假千金、打脸绿茶）")
    episodes_count: int = Field(default=80, description="总集数（通常60-100）")


class ActorRanking(BaseModel):
    """演员榜单条目"""
    rank: int = Field(..., description="排名")
    name: str = Field(..., description="演员名")
    popularity: int = Field(default=0, description="人气指数")
    platform_fans: float = Field(default=0.0, description="平台粉丝数（万）")
    platform: str = Field(default="红果", description="平台")
    badge: str = Field(default="", description="徽章")
    works: str = Field(default="", description="代表作")
    trend: str = Field(default="", description="趋势描述")


class ActorsData(BaseModel):
    """演员数据"""
    female: List[ActorRanking] = Field(default=[], description="女频演员TOP10")
    male: List[ActorRanking] = Field(default=[], description="男频演员TOP10")


class PlatformApp(BaseModel):
    """平台APP数据"""
    name: str = Field(..., description="平台名称")
    mau: float = Field(default=0.0, description="月活用户数")
    mau_unit: str = Field(default="亿", description="单位")
    yoy: str = Field(default="", description="同比增长")
    share: int = Field(default=0, description="市场份额")
    trend: str = Field(default="same", description="趋势：up/down/same")


class PlatformData(BaseModel):
    """平台数据"""
    apps: List[PlatformApp] = Field(default=[], description="APP列表")
    mini_programs: List[Dict[str, Any]] = Field(default=[], description="小程序列表")


class IndustryData(BaseModel):
    """行业数据"""
    user_scale: str = Field(default="", description="用户规模")
    market_size: str = Field(default="", description="市场规模")
    drama_count: str = Field(default="", description="短剧数量")
    billion_dramas: int = Field(default=0, description="过亿短剧数")
    ai_ratio: int = Field(default=0, description="AI短剧占比(%)")
    female_ratio: int = Field(default=0, description="女频占比(%)")
    male_ratio: int = Field(default=0, description="男频占比(%)")
    app_mau: str = Field(default="", description="APP月活")
    app_mau_yoy: str = Field(default="", description="APP月活同比增长")


class Insight(BaseModel):
    """洞察"""
    icon: str = Field(default="", description="emoji图标")
    title: str = Field(default="", description="洞察标题（10字以内）")
    content: str = Field(default="", description="洞察详细描述（150-200字）")


class Innovation(BaseModel):
    """创新点"""
    icon: str = Field(default="", description="emoji图标")
    title: str = Field(default="", description="创新标题（10字以内）")
    content: str = Field(default="", description="创新点详细描述（100-150字）")


class DailyNews(BaseModel):
    """每日行业快讯"""
    type: str = Field(default="数据", description="快讯类型：预警/商业/数据")
    icon: str = Field(default="📊", description="emoji图标")
    content: str = Field(default="", description="快讯内容（不超过40字）")


# ==================== 新增数据结构 ====================

class AgeDistribution(BaseModel):
    """年龄分布"""
    age_18_24: int = Field(default=0, description="18-24岁占比")
    age_25_34: int = Field(default=0, description="25-34岁占比")
    age_35_44: int = Field(default=0, description="35-44岁占比")
    age_45_plus: int = Field(default=0, description="45岁以上占比")


class RegionDistribution(BaseModel):
    """地域分布"""
    name: str = Field(default="", description="省份/城市名")
    value: int = Field(default=0, description="占比")


class AudienceProfile(BaseModel):
    """观众画像"""
    gender_female: int = Field(default=0, description="女性用户占比")
    gender_male: int = Field(default=0, description="男性用户占比")
    age_distribution: AgeDistribution = Field(default_factory=AgeDistribution, description="年龄分布")
    top_regions: List[RegionDistribution] = Field(default=[], description="TOP地域分布")
    peak_viewing_hours: str = Field(default="", description="高峰观看时段")
    avg_watch_duration: str = Field(default="", description="平均观看时长")
    # 新增字段
    device: Dict[str, int] = Field(default_factory=lambda: {"ios": 58, "android": 42}, description="设备分布")
    time: List[Dict[str, Any]] = Field(default_factory=list, description="观看时段分布")
    traits: List[str] = Field(default_factory=list, description="用户特征标签")


class GenreStats(BaseModel):
    """题材统计"""
    name: str = Field(default="", description="题材名称")
    count: int = Field(default=0, description="短剧数量")
    total_views: str = Field(default="", description="总播放量")
    trend: str = Field(default="same", description="趋势：up/down/same")


class GenreDistribution(BaseModel):
    """题材分布"""
    genres: List[GenreStats] = Field(default=[], description="各题材统计")
    top_genre: str = Field(default="", description="最热门题材")
    rising_genre: str = Field(default="", description="上升最快题材")


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


class PlatformShare(BaseModel):
    """平台份额"""
    name: str = Field(default="", description="平台名称")
    share: int = Field(default=0, description="市场份额(%)")
    trend: str = Field(default="same", description="趋势：up/down/same")


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


# ==================== 全局状态 ====================

class GlobalState(BaseModel):
    """全局状态定义"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    search_results: List[Dict[str, Any]] = Field(default=[], description="搜索结果原始数据")
    basic_rankings: List[Dict[str, Any]] = Field(default=[], description="基础榜单数据（初步提取）")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    insights: List[Insight] = Field(default=[], description="异动点评列表（最多2条）")
    # 新增字段
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="题材分布")
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    quality_score: float = Field(default=0.0, description="数据质量分数 (0-100)")
    error_message: str = Field(default="", description="错误信息")


# ==================== 工作流输入输出 ====================

class GraphInput(BaseModel):
    """工作流输入"""
    data_date: Optional[str] = Field(
        default=None, 
        description="数据日期 (YYYY-MM-DD)，不传则使用当前日期"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="周期开始日期 (YYYY-MM-DD)，用于周期统计"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="周期结束日期 (YYYY-MM-DD)，用于周期统计"
    )


class GraphOutput(BaseModel):
    """工作流输出"""
    success: Annotated[bool, "merge"] = Field(..., description="是否成功")
    generated_at: str = Field(..., description="生成时间")
    data_date: str = Field(..., description="数据日期")
    period: str = Field(default="", description="数据周期（如 2026-05-15_2026-05-21）")
    # 概览统计（Dashboard页面1）
    overview: OverviewStats = Field(default_factory=OverviewStats, description="概览统计数据")
    genre_distribution: Dict[str, int] = Field(default_factory=dict, description="题材分布百分比")
    platform_share: List[PlatformShare] = Field(default_factory=list, description="平台份额")
    # 详细数据
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    rankings: List[DramaRanking] = Field(default=[], description="榜单数据")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    weekly_rankings: List[WeeklyRankingItem] = Field(default=[], description="周榜历史")
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    insights: List[Insight] = Field(default=[], description="异动点评列表")
    quality_score: float = Field(default=0.0, description="数据质量分数")
    error_message: str = Field(default="", description="错误信息")


# ==================== 数据抓取节点 ====================

class SearchNodeInput(BaseModel):
    """数据抓取节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)，空则使用当前日期")


class SearchNodeOutput(BaseModel):
    """数据抓取节点输出"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    search_results: List[Dict[str, Any]] = Field(default=[], description="搜索结果列表")


# ==================== 初步处理节点 ====================

class ProcessNodeInput(BaseModel):
    """初步处理节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    search_results: List[Dict[str, Any]] = Field(default=[], description="搜索结果列表")


class ProcessNodeOutput(BaseModel):
    """初步处理节点输出"""
    basic_rankings: List[Dict[str, Any]] = Field(default=[], description="基础榜单数据")
    quality_score: float = Field(default=0.0, description="数据质量分数")


# ==================== 数据补充节点 ====================

class EnrichNodeInput(BaseModel):
    """数据补充节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    basic_rankings: List[Dict[str, Any]] = Field(default=[], description="基础榜单数据")


class EnrichNodeOutput(BaseModel):
    """数据补充节点输出"""
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


# ==================== 演员榜单生成节点 ====================

class ActorRankingNodeInput(BaseModel):
    """演员榜单生成节点输入"""
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class ActorRankingNodeOutput(BaseModel):
    """演员榜单生成节点输出"""
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")


# ==================== 行业数据节点 ====================

class IndustryNodeInput(BaseModel):
    """行业数据节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class IndustryNodeOutput(BaseModel):
    """行业数据节点输出"""
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")


# ==================== 洞察生成节点 ====================

class InsightsNodeInput(BaseModel):
    """洞察生成节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="榜单数据")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员数据")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")


class InsightsNodeOutput(BaseModel):
    """洞察生成节点输出"""
    insights: List[Insight] = Field(default=[], description="异动点评列表")


# ==================== 每日快讯节点 ====================

class NewsNodeInput(BaseModel):
    """每日快讯节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")


class NewsNodeOutput(BaseModel):
    """每日快讯节点输出"""
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")


# ==================== 数据推送节点 ====================

class PushNodeInput(BaseModel):
    """数据推送节点输入"""
    generated_at: str = Field(default="", description="生成时间")
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="榜单数据")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    insights: List[Insight] = Field(default=[], description="异动点评列表")
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="题材分布")
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    quality_score: float = Field(default=0.0, description="数据质量分数")


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
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="题材分布")
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    quality_score: float = Field(default=0.0, description="数据质量分数")
    error_message: str = Field(default="", description="错误信息")
    storage_url: str = Field(default="", description="对象存储URL（用于GitHub同步）")
    storage_key: str = Field(default="", description="对象存储Key（持久化存储）")


# ==================== 条件判断 ====================

class ShouldPushInput(BaseModel):
    """是否推送数据判断输入"""
    quality_score: float = Field(..., description="数据质量分数")
    success: bool = Field(..., description="数据处理是否成功")


# ==================== 观众画像节点 ====================

class GenderDistribution(BaseModel):
    """性别分布"""
    female: int = Field(default=0, description="女性占比")
    male: int = Field(default=0, description="男性占比")


class AudienceProfileInput(BaseModel):
    """观众画像节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")


class AudienceProfileOutput(BaseModel):
    """观众画像节点输出"""
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")


# ==================== 题材分布节点 ====================

class GenreStat(BaseModel):
    """题材统计（节点内部使用）"""
    name: str = Field(default="", description="题材名称")
    count: int = Field(default=0, description="短剧数量")
    views: int = Field(default=0, description="总播放量(万)")
    share: float = Field(default=0.0, description="播放量占比(%)")
    trend: str = Field(default="same", description="趋势：up/down/same")
    ai_count: int = Field(default=0, description="AI短剧数量")
    female_count: int = Field(default=0, description="女频数量")
    male_count: int = Field(default=0, description="男频数量")


class GenreDistributionInput(BaseModel):
    """题材分布节点输入"""
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class GenreDistributionOutput(BaseModel):
    """题材分布节点输出"""
    genres: List[GenreStat] = Field(default=[], description="各题材统计")
    total_count: int = Field(default=0, description="总短剧数")
    total_views: int = Field(default=0, description="总播放量(万)")


# ==================== 历史数据节点 ====================

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


class HistoryDataInput(BaseModel):
    """历史数据节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class HistoryDataOutput(BaseModel):
    """历史数据节点输出"""
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
