"""
题材分布与标签相关数据模型
"""
from typing import List
from pydantic import BaseModel, Field


class GenreStats(BaseModel):
    """题材统计"""
    name: str = Field(default="", description="题材名称")
    count: int = Field(default=0, description="短剧数量")
    total_views: str = Field(default="", description="总播放量")
    trend: str = Field(default="same", description="趋势：up/down/same")


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
