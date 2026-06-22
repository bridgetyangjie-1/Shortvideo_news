"""
情绪分析相关数据模型
"""
from typing import List
from pydantic import BaseModel, Field


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
        default="",
        description="一句话总览"
    )
    dominant_emotion: str = Field(default="", description="主导情绪")
    dominant_anxiety: str = Field(default="", description="主导现实焦虑")
    top_trigger: str = Field(default="", description="TOP1 剧情触发点")
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
    data_source: str = Field(
        default="",
        description="数据来源说明，如'当日榜单规则统计 + DeepSeek 提炼'或'本地规则兜底'",
    )
    update_frequency: str = Field(
        default="daily",
        description="更新频率：daily/weekly/monthly",
    )


def default_emotional_analysis() -> EmotionalAnalysis:
    """核心情绪与动机拆解默认空结构（方向A：缺失时留空，不回退到 mock 数据）"""
    return EmotionalAnalysis()
