"""
行业与平台相关数据模型
"""
from typing import Any, Dict, List
from pydantic import BaseModel, Field, field_validator


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
    data_source: str = Field(
        default="",
        description="数据来源说明，如'Kimi 搜索行业报告'",
    )
    update_frequency: str = Field(
        default="monthly",
        description="更新频率：monthly/weekly/daily",
    )


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
    market_spend: str = Field(default="", description="微短剧月大盘消耗（如22.62亿）")
    market_spend_yoy: str = Field(default="", description="大盘消耗环比变化（如+8%）")
    data_source: str = Field(
        default="",
        description="数据来源说明，如'Kimi 搜索行业报告'或'榜单统计'",
    )
    update_frequency: str = Field(
        default="monthly",
        description="更新频率：monthly/weekly/daily",
    )

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

    @field_validator("user_scale", "market_size", "app_mau", "market_spend", mode="before")
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
