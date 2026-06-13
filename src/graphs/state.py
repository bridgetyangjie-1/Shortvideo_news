"""
短剧行业研究数据自动更新工作流 - 状态定义
"""
import operator
from typing import Optional, List, Dict, Any, Annotated
from pydantic import BaseModel, Field, field_validator
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
    trend_tag: str = Field(default="", description="趋势标签，如飙升/新晋")
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
    # 🚨 新增数据质量与趋势分析字段（v1.8.2）
    confidence_score: float = Field(default=0.7, description="置信度评分 (0-1)，红果直爬0.7，交叉验证0.95")
    data_source: str = Field(default="hongguo", description="数据来源：hongguo/dataeye/kimi/deepseek")
    rank_change: int = Field(default=0, description="排名变化：正数上升，负数下降，0不变，-1新晋")
    previous_rank: int = Field(default=0, description="昨日排名，0表示昨日不在榜")
    cross_validated: bool = Field(default=False, description="是否经DataEye交叉验证")
    dataeye_rank: int = Field(default=0, description="DataEye排名（0表示无）")
    dataeye_heat: int = Field(default=0, description="DataEye热度值")
    series_id: str = Field(default="", description="红果剧目ID")
    cover: str = Field(default="", description="封面图URL")

    @field_validator("title", mode="before")
    @classmethod
    def _validate_title(cls, v):
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("rank", "views_num", "heat", "episodes_count", "dataeye_rank", "dataeye_heat", "previous_rank", mode="before")
    @classmethod
    def _validate_non_negative_int(cls, v):
        try:
            return max(0, int(v or 0))
        except (TypeError, ValueError):
            return 0

    @field_validator("confidence_score", mode="before")
    @classmethod
    def _validate_confidence_score(cls, v):
        try:
            return max(0.0, min(1.0, float(v if v is not None else 0.7)))
        except (TypeError, ValueError):
            return 0.7

    @field_validator("category", mode="before")
    @classmethod
    def _validate_category(cls, v):
        v = str(v or "female").strip().lower()
        return v if v in {"female", "male", "ai", "neutral"} else "female"

    @field_validator("trend_type", mode="before")
    @classmethod
    def _validate_trend_type(cls, v):
        v = str(v or "same").strip().lower()
        return v if v in {"new", "up", "down", "same"} else "same"


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

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v):
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("rank", "popularity", "platform_fans", mode="before")
    @classmethod
    def _validate_actor_numbers(cls, v):
        try:
            if isinstance(v, (int, float)):
                return max(0, v)
            return max(0, float(v or 0))
        except (TypeError, ValueError):
            return 0


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
    user_scale: Any = Field(default="", description="用户规模（支持字符串或字典格式）")
    market_size: Any = Field(default="", description="市场规模（支持字符串或字典格式）")
    drama_count: str = Field(default="", description="短剧数量")
    billion_dramas: int = Field(default=0, description="过亿短剧数")
    ai_ratio: int = Field(default=0, description="AI短剧占比(%)")
    female_ratio: int = Field(default=0, description="女频占比(%)")
    male_ratio: int = Field(default=0, description="男频占比(%)")
    app_mau: str = Field(default="", description="APP月活")
    app_mau_yoy: str = Field(default="", description="APP月活同比增长")

    @field_validator("ai_ratio", "female_ratio", "male_ratio", mode="before")
    @classmethod
    def _validate_ratio(cls, v):
        if v is None or v == "":
            return 0
        try:
            return max(0, min(100, int(float(v))))
        except (TypeError, ValueError):
            return 0

    @field_validator("billion_dramas", mode="before")
    @classmethod
    def _validate_billion_dramas(cls, v):
        if v is None or v == "":
            return 0
        try:
            return max(0, int(float(v)))
        except (TypeError, ValueError):
            return 0

    @field_validator("user_scale", "market_size", "app_mau", mode="before")
    @classmethod
    def _normalize_metric(cls, v):
        if v is None:
            return ""
        if isinstance(v, dict):
            value = v.get("value", "")
            unit = v.get("unit", "")
            yoy = v.get("yoy", "")
            s = f"{value}{unit}".strip()
            if yoy:
                s = f"{s}（{yoy}）"
            return s
        return str(v).strip()

    @field_validator("app_mau_yoy", "drama_count", mode="before")
    @classmethod
    def _normalize_text(cls, v):
        return "" if v is None else str(v).strip()


class Insight(BaseModel):
    """洞察"""
    icon: str = Field(default="", description="emoji图标")
    title: str = Field(default="", description="洞察标题（10字以内）")
    content: str = Field(default="", description="洞察详细描述（150-200字）")
    source: str = Field(default="", description="洞察来源说明")


class Innovation(BaseModel):
    """创新点"""
    icon: str = Field(default="", description="emoji图标")
    title: str = Field(default="", description="创新标题（10字以内）")
    content: str = Field(default="", description="创新点详细描述（100-150字）")


class DailyNews(BaseModel):
    """每日行业快讯"""
    type: str = Field(default="数据", description="快讯类型：预警/商业/数据")
    icon: str = Field(default="📊", description="emoji图标")
    title: str = Field(default="", description="新闻标题（15字以内）")
    content: str = Field(default="", description="快讯内容缩写（不超过100字）")
    insight: str = Field(default="", description="深度洞察分析（100字左右）")
    source_url: str = Field(default="", description="原文地址链接")


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
    value: float = Field(default=0.0, description="占比百分比")


class AudienceProfile(BaseModel):
    """观众画像"""
    gender: Dict[str, float] = Field(
        default_factory=lambda: {"female": 0, "male": 0},
        description="性别分布百分比，包含female/male",
    )
    age: Dict[str, float] = Field(
        default_factory=lambda: {"18-24": 0, "25-34": 0, "35-44": 0, "45+": 0},
        description="年龄分布百分比，包含18-24/25-34/35-44/45+",
    )
    regions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="地域分布，元素包含name省份和value比例",
    )
    traits: List[str] = Field(
        default_factory=lambda: [
            "偏好强反转高密度剧情",
            "关注女性成长与逆袭补偿",
            "习惯碎片化连续追更",
            "对身份反差爽点敏感",
        ],
        description="4个具体受众特征标签",
    )
    content_preferences: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="题材/内容偏好分布，元素包含name题材和value占比",
    )
    viewing_time: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="观看时段分布，元素包含name时段和value占比",
    )
    spending_power: Dict[str, Any] = Field(
        default_factory=dict,
        description="付费能力与意愿，如{paid_ratio, arpu, willingness}",
    )
    user_segments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="用户分层，元素包含name、share占比、desc描述",
    )


class GenreStats(BaseModel):
    """题材统计"""
    name: str = Field(default="", description="题材名称")
    count: int = Field(default=0, description="短剧数量")
    total_views: str = Field(default="", description="总播放量")
    trend: str = Field(default="same", description="趋势：up/down/same")


class TagItem(BaseModel):
    """单个标签统计"""
    name: str = Field(default="", description="标签名")
    value: int = Field(default=0, description="出现次数或加权热度")


class TagCategory(BaseModel):
    """按类别聚合的标签"""
    category: str = Field(default="", description="类别名称，如题材/人设/爽点")
    tags: List[TagItem] = Field(default_factory=list, description="该类别下的标签列表")


class TrendingTag(BaseModel):
    """带环比趋势的热门标签"""
    name: str = Field(default="", description="标签名")
    value: int = Field(default=0, description="今日出现次数")
    change: int = Field(default=0, description="较昨日变化量")
    trend: str = Field(default="same", description="趋势：up/down/new/same")


class GenreDistribution(BaseModel):
    """近一周热门标签"""
    hot_tags: List[TagItem] = Field(
        default_factory=list,
        description="近一周热门标签TOP20，元素格式为 {'name': 标签名, 'value': 加权次数}",
    )
    categories: List[TagCategory] = Field(
        default_factory=list,
        description="按题材/人设/爽点/情感/时代等维度聚合的热门标签",
    )
    trending: List[TrendingTag] = Field(
        default_factory=list,
        description="较昨日变化明显的标签，含 change/trend",
    )


class EmotionWordCloudItem(BaseModel):
    """情绪词云条目"""
    name: str = Field(default="", description="情绪/焦虑/触发点/代偿场景关键词")
    value: int = Field(default=0, description="强度 0-100")
    category: str = Field(default="emotion", description="分类：emotion/anxiety/trigger/payoff/expectation/motivation")


class EmotionRankingItem(BaseModel):
    """带情绪标签的榜单剧目"""
    rank: int = Field(default=0, description="排名")
    title: str = Field(default="", description="剧名")
    primary_emotion: str = Field(default="", description="主导情绪")
    anxiety: str = Field(default="", description="对应现实焦虑")
    trigger: str = Field(default="", description="爽点触发点")
    one_line: str = Field(default="", description="一句话心理拆解")


class EmotionTrendItem(BaseModel):
    """情绪维度环比变化"""
    name: str = Field(default="", description="维度名称")
    change: int = Field(default=0, description="较昨日变化量")
    trend: str = Field(default="same", description="趋势：up/down/new/same")


class ActionableInsight(BaseModel):
    """可执行洞察"""
    icon: str = Field(default="💡", description="emoji图标")
    title: str = Field(default="", description="短标题 15字以内")
    content: str = Field(default="", description="具体建议 80-120字")


class EmotionalAnalysis(BaseModel):
    """核心情绪与动机拆解"""
    summary: str = Field(
        default="今日榜单以都市复仇与甜宠逆袭为主，观众通过剧情实现情绪代偿。",
        description="一句话总览"
    )
    dominant_emotion: str = Field(default="心理补偿", description="主导情绪")
    dominant_anxiety: str = Field(default="亲密关系失衡", description="主导现实焦虑")
    top_trigger: str = Field(default="复仇打脸", description="TOP1 剧情触发点")
    wordcloud: List[EmotionWordCloudItem] = Field(
        default_factory=list,
        description="情绪关键词云"
    )
    emotion_rankings: List[EmotionRankingItem] = Field(
        default_factory=list,
        description="TOP3 情绪典型剧目"
    )
    trends: List[EmotionTrendItem] = Field(
        default_factory=list,
        description="情绪维度环比趋势"
    )
    actionable_insights: List[ActionableInsight] = Field(
        default_factory=list,
        description="3条创作者/投流行动建议"
    )


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


def default_emotional_analysis() -> EmotionalAnalysis:
    """核心情绪与动机拆解默认结构"""
    return EmotionalAnalysis(
        summary="今日榜单以都市复仇与甜宠逆袭为主，观众通过剧情实现情绪代偿。",
        dominant_emotion="心理补偿",
        dominant_anxiety="亲密关系失衡",
        top_trigger="复仇打脸",
        wordcloud=[
            EmotionWordCloudItem(name="复仇打脸", value=28, category="trigger"),
            EmotionWordCloudItem(name="甜宠撒糖", value=22, category="trigger"),
            EmotionWordCloudItem(name="身份逆袭", value=20, category="emotion"),
            EmotionWordCloudItem(name="亲密关系失衡", value=19, category="anxiety"),
            EmotionWordCloudItem(name="职场受挫", value=16, category="payoff"),
            EmotionWordCloudItem(name="解压放空", value=15, category="motivation"),
        ],
        emotion_rankings=[
            EmotionRankingItem(
                rank=1,
                title="示例剧目",
                primary_emotion="身份逆袭",
                anxiety="亲密关系失衡",
                trigger="复仇打脸",
                one_line="用逆袭打脸补偿亲密关系中的价值否定"
            )
        ],
        trends=[
            EmotionTrendItem(name="复仇打脸", change=0, trend="same"),
            EmotionTrendItem(name="甜宠撒糖", change=0, trend="same"),
        ],
        actionable_insights=[
            ActionableInsight(
                icon="💡",
                title="聚焦复仇逆袭情绪",
                content="今日'复仇打脸'情绪显著，新剧本前3秒建议直接展示冲突反转，提升素材CTR。"
            ),
            ActionableInsight(
                icon="📈",
                title="瞄准亲密关系焦虑",
                content="观众对'亲密关系失衡'代偿需求强，投流文案可直接点出情感痛点并展示反转爽点。"
            ),
            ActionableInsight(
                icon="🎯",
                title="复用高触发题材框架",
                content="TOP3剧目均命中'复仇打脸'触发点，后续创作可延续该爽点框架并做微创新。"
            ),
        ],
    )


# ==================== 全局状态 ====================

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
    # 新增字段
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签")
    emotional_analysis: EmotionalAnalysis = Field(
        default_factory=default_emotional_analysis,
        description="核心情绪与动机拆解",
    )
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    weekly_rankings: List[WeeklyRankingItem] = Field(default=[], description="周榜历史")
    quality_score: float = Field(default=0.0, description="数据质量分数 (0-100)")
    error_message: Annotated[str, operator.add] = Field(default="", description="错误信息")


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
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签数据")
    emotional_analysis: EmotionalAnalysis = Field(
        default_factory=default_emotional_analysis,
        description="核心情绪与动机拆解",
    )
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
    error_message: str = Field(default="", description="错误信息")


# ==================== 初步处理节点 ====================

class ProcessNodeInput(BaseModel):
    """初步处理节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    search_results: List[Dict[str, Any]] = Field(default=[], description="搜索结果列表")


class ProcessNodeOutput(BaseModel):
    """初步处理节点输出"""
    basic_rankings: List[Dict[str, Any]] = Field(default=[], description="基础榜单数据")
    quality_score: float = Field(default=0.0, description="数据质量分数")
    error_message: str = Field(default="", description="错误信息")


# ==================== 数据补充节点 ====================

class EnrichNodeInput(BaseModel):
    """数据补充节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    basic_rankings: List[Dict[str, Any]] = Field(default=[], description="基础榜单数据")


class EnrichNodeOutput(BaseModel):
    """数据补充节点输出"""
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")
    error_message: str = Field(default="", description="错误信息")


# ==================== 演员榜单生成节点 ====================

class ActorRankingNodeInput(BaseModel):
    """演员榜单生成节点输入"""
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class ActorRankingNodeOutput(BaseModel):
    """演员榜单生成节点输出"""
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    error_message: str = Field(default="", description="错误信息")


# ==================== 行业数据节点 ====================

class IndustryNodeInput(BaseModel):
    """行业数据节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class IndustryNodeOutput(BaseModel):
    """行业数据节点输出"""
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    error_message: str = Field(default="", description="错误信息")


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
    error_message: str = Field(default="", description="错误信息")


# ==================== 每日快讯节点 ====================

class NewsNodeInput(BaseModel):
    """每日快讯节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")


class NewsNodeOutput(BaseModel):
    """每日快讯节点输出"""
    daily_news: List[DailyNews] = Field(default=[], description="每日行业快讯")
    error_message: str = Field(default="", description="错误信息")


# ==================== 数据推送节点 ====================

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
    quality_score: float = Field(default=0.0, description="数据质量分数")
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
    quality_score: float = Field(default=0.0, description="数据质量分数")
    error_message: str = Field(default="", description="错误信息")
    storage_url: str = Field(default="", description="对象存储URL（用于GitHub同步）")
    storage_key: str = Field(default="", description="对象存储Key（持久化存储）")
    output_path: str = Field(default="", description="本地输出文件路径")


# ==================== 条件判断 ====================

class QualityGateInput(BaseModel):
    """数据质量门禁节点输入"""
    data_date: str = Field(default="", description="数据日期 (YYYY-MM-DD)")
    enriched_rankings: List[DramaRanking] = Field(default_factory=list, description="补充后的完整榜单")
    actors: ActorsData = Field(default_factory=ActorsData, description="演员榜单")
    daily_news: List[DailyNews] = Field(default_factory=list, description="每日行业快讯")
    industry: IndustryData = Field(default_factory=IndustryData, description="行业数据")
    platform: PlatformData = Field(default_factory=PlatformData, description="平台数据")
    insights: List[Insight] = Field(default_factory=list, description="异动点评列表")
    quality_score: float = Field(default=0.0, description="当前数据质量分数")
    error_message: str = Field(default="", description="上游错误信息")


class QualityGateOutput(BaseModel):
    """数据质量门禁节点输出"""
    success: bool = Field(default=True, description="是否通过质量门禁")
    quality_score: float = Field(default=0.0, description="重新计算后的数据质量分数 (0-100)")
    quality_report: Dict[str, Any] = Field(default_factory=dict, description="质量门禁详细报告")
    error_message: str = Field(default="", description="错误/告警信息")


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
    enriched_rankings: List[DramaRanking] = Field(default_factory=list, description="补充后的完整榜单")


class AudienceProfileOutput(BaseModel):
    """观众画像节点输出"""
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile, description="观众画像")
    error_message: str = Field(default="", description="错误信息")


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
    """热门标签节点输入"""
    data_date: str = Field(default="", description="数据日期 YYYY-MM-DD")
    enriched_rankings: List[DramaRanking] = Field(default=[], description="补充后的完整榜单")


class GenreDistributionOutput(BaseModel):
    """热门标签节点输出"""
    genre_distribution: GenreDistribution = Field(default_factory=GenreDistribution, description="近一周热门标签数据")
    total_count: int = Field(default=0, description="总短剧数")
    total_views: int = Field(default=0, description="总播放量(万)")
    error_message: str = Field(default="", description="错误信息")


# ==================== 情绪分析节点 ====================

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


class RankChange(BaseModel):
    """排名变化条目"""
    title: str = Field(default="", description="剧名")
    current_rank: int = Field(default=0, description="当前排名")
    previous_rank: Optional[int] = Field(default=None, description="昨日排名，None表示昨日不在榜")
    change_type: str = Field(default="new", description="变化类型：new/up/down/stable")
    change_value: int = Field(default=0, description="变化幅度")


class HistoryDataOutput(BaseModel):
    """历史数据节点输出"""
    play_trend: PlayTrend = Field(default_factory=PlayTrend, description="播放量趋势")
    weekly_rankings: List[WeeklyRankingItem] = Field(default=[], description="周榜历史")
    rank_changes: List[RankChange] = Field(default=[], description="排名变化分析")
    error_message: str = Field(default="", description="错误信息")
