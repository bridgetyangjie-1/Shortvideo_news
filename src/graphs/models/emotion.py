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
