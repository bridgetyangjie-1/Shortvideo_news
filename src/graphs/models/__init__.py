"""
graphs.models - 按领域拆分的数据模型集合
"""
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

__all__ = [
    # ranking
    "DramaRanking",
    "ActorRanking",
    "ActorsData",
    # industry
    "IndustryData",
    "PlatformData",
    "PlatformApp",
    # audience
    "AudienceProfile",
    "AgeDistribution",
    "RegionDistribution",
    # genre
    "GenreDistribution",
    "TagItem",
    "TagCategory",
    "TrendingTag",
    "GenreStats",
    # emotion
    "EmotionalAnalysis",
    "EmotionWordCloudItem",
    "EmotionRankingItem",
    "EmotionTrendItem",
    "ActionableInsight",
    "default_emotional_analysis",
    # history
    "OverviewStats",
    "WeeklyRankingItem",
    "DailyPlayTrend",
    "PlayTrend",
    "HistoryData",
    "DailyPlayData",
    "WeeklyPlayData",
    "RankChange",
    "HistoryDataInput",
    "HistoryDataOutput",
    # news
    "Insight",
    "Innovation",
    "DailyNews",
    # alerts
    "AlertItem",
    # node io
    "SearchNodeInput",
    "SearchNodeOutput",
    "ProcessNodeInput",
    "ProcessNodeOutput",
    "EnrichNodeInput",
    "EnrichNodeOutput",
    "ActorRankingNodeInput",
    "ActorRankingNodeOutput",
    "IndustryNodeInput",
    "IndustryNodeOutput",
    "InsightsNodeInput",
    "InsightsNodeOutput",
    "NewsNodeInput",
    "NewsNodeOutput",
    "PushNodeInput",
    "PushNodeOutput",
    "ShouldPushInput",
    "QualityGateInput",
    "QualityGateOutput",
    "AlertNodeInput",
    "AlertNodeOutput",
    "GenderDistribution",
    "AudienceProfileInput",
    "AudienceProfileOutput",
    "GenreStat",
    "GenreDistributionInput",
    "GenreDistributionOutput",
    "EmotionAnalysisNodeInput",
    "EmotionAnalysisNodeOutput",
]
