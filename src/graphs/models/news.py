"""
洞察与快讯相关数据模型
"""
from pydantic import BaseModel, Field


class Insight(BaseModel):
    """洞察"""
    icon: str = Field(default="", description="emoji图标")
    title: str = Field(default="", description="洞察标题（10字以内）")
    content: str = Field(default="", description="洞察详细描述（150-200字）")
    source: str = Field(default="", description="洞察来源说明")
    data_source: str = Field(
        default="",
        description="数据来源说明，如'Kimi 搜索 + DeepSeek 提炼'",
    )
    update_frequency: str = Field(
        default="daily",
        description="更新频率：daily/weekly/monthly",
    )


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
    data_source: str = Field(
        default="",
        description="数据来源说明，如'Kimi 搜索 + DeepSeek 提炼'",
    )
    update_frequency: str = Field(
        default="daily",
        description="更新频率：daily/weekly/monthly",
    )
