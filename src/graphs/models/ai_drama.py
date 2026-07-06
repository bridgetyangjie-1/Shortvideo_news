"""
AI 短剧/漫剧看板数据模型
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class AIDramaKPI(BaseModel):
    """AI 短剧/漫剧 KPI 指标卡片"""
    label: str = Field(default="", description="指标名称")
    value: str = Field(default="", description="指标数值")
    unit: str = Field(default="", description="单位")
    trend: str = Field(default="same", description="趋势：up/down/same")
    period: str = Field(default="环比", description="对比周期")
    note: str = Field(default="", description="补充说明")


class AIDramaRankingItem(BaseModel):
    """AI 剧/漫剧榜单条目"""
    rank: int = Field(default=0, description="排名 1-5")
    title: str = Field(default="", description="剧目名称")
    platform: str = Field(default="", description="主要播放平台")
    category: str = Field(default="", description="AI仿真人剧 / 3D AI漫剧 / 2D AI漫剧 / AIGC漫剧")
    heat: str = Field(default="", description="热度或月活/观看指标")
    is_new: bool = Field(default=False, description="是否本月新剧")
    plot: str = Field(default="", description="30-60 字剧情简介")
    tags: List[str] = Field(default_factory=list, description="题材/风格标签，最多 4 个")
    studio: str = Field(default="", description="制作方/工作室/版权方")
    url: str = Field(default="", description="平台搜索页或报道原文链接")
    episodes: str = Field(default="", description="集数")
    release_date: str = Field(default="", description="上线日期 YYYY-MM-DD")


class AIDramaTrend(BaseModel):
    """AI 短剧/漫剧趋势洞察"""
    title: str = Field(default="", description="趋势标题")
    summary: str = Field(default="", description="50-100 字摘要")
    source: str = Field(default="", description="来源媒体")
    source_url: str = Field(default="", description="原文链接")


class AIDramaNews(BaseModel):
    """AI 短剧/漫剧行业快讯"""
    title: str = Field(default="", description="标题")
    source: str = Field(default="", description="来源媒体")
    date: str = Field(default="", description="发布日期 YYYY-MM-DD")
    url: str = Field(default="", description="原文链接")
    summary: str = Field(default="", description="100 字左右摘要/缩写")


class AIDramaDashboard(BaseModel):
    """🤖 AI 短剧/漫剧看板"""
    report_month: str = Field(default="", description="报告月份 YYYY-MM")
    kpis: List[AIDramaKPI] = Field(default_factory=list)
    rankings: dict = Field(default_factory=dict, description="包含 ai_drama / ai_comic 两个榜单数组")
    trends: List[AIDramaTrend] = Field(default_factory=list)
    news: List[AIDramaNews] = Field(default_factory=list)
    data_source: str = Field(default="", description="数据来源说明")
    update_frequency: str = Field(default="monthly", description="更新频率")
