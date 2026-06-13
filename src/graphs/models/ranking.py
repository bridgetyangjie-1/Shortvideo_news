"""
榜单与演员相关数据模型
"""
from typing import List
from pydantic import BaseModel, Field, field_validator


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
    production_house: str = Field(default="", description="制作厂牌（如九州、点众、麦芽）")
    core_trope: List[str] = Field(default=[], description="核心爽点标签（如真假千金、打脸绿茶）")
    episodes_count: int = Field(default=80, description="总集数（通常60-100）")
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
