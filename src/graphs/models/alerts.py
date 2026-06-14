"""
异常告警数据模型
"""
from typing import Any, Optional
from pydantic import BaseModel, Field


class AlertItem(BaseModel):
    """单条异常告警"""

    severity: str = Field(
        default="info",
        description="告警级别：critical / warning / info",
    )
    category: str = Field(
        default="",
        description="告警分类：ranking / actor / news / industry / platform / genre / emotion / api / quality",
    )
    title: str = Field(default="", description="告警标题（20字以内）")
    message: str = Field(default="", description="告警详情")
    metric: Optional[str] = Field(default=None, description="关联指标名")
    value: Optional[Any] = Field(default=None, description="当前指标值")
    threshold: Optional[Any] = Field(default=None, description="阈值")
    suggestion: Optional[str] = Field(default=None, description="建议处理方式")
