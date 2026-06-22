"""
观众画像相关数据模型
"""
from typing import Any, Dict, List
from pydantic import BaseModel, Field


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
        default_factory=list,
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
    data_source: str = Field(
        default="",
        description="数据来源说明，如'QuestMobile 2025Q1 报告'或'本地规则估算'",
    )
    update_frequency: str = Field(
        default="monthly",
        description="更新频率：monthly/weekly/daily",
    )
