"""
观众画像节点 - 获取短剧观众画像数据
"""
import os
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List
from jinja2 import Template

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.moonshot_api import MoonshotClient, is_api_budget_error

from graphs.state import (
    AudienceProfileInput,
    AudienceProfileOutput,
    AudienceProfile,
    AgeDistribution,
    RegionDistribution
)

logger = logging.getLogger(__name__)


def audience_profile_node(
    state: AudienceProfileInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> AudienceProfileOutput:
    """
    title: 📊 获取观众画像数据
    desc: 使用 Kimi 联网搜索QuestMobile、DataEye等报告，获取短剧观众画像数据
    integrations: Moonshot API
    """
    ctx = runtime.context
    
    try:
        # 初始化 Kimi 客户端
        client = MoonshotClient()
        
        # 使用 Kimi 联网搜索观众画像数据
        search_query = """请搜索互联网，获取短剧观众的画像数据，包括：
1. 性别分布（女性/男性占比）
2. 年龄分布（18-24岁、25-34岁、35-44岁、45岁以上各年龄段占比）
3. 地域分布（Top10省份/城市及占比）
4. 观看时段（高峰时段）
5. 平均观看时长

请搜索QuestMobile、DataEye、云合数据等权威报告的最新数据。

返回JSON格式：
{
  "gender": {"female": xx, "male": xx},
  "age": {"18-24": xx, "25-34": xx, "35-44": xx, "45+": xx},
  "regions": [{"name": "省份名", "value": 占比}],
  "peak_hours": "高峰时段",
  "avg_duration": "平均观看时长"
}
"""
        
        # 执行 Kimi 官方 $web_search 并解析响应
        profile_data = client.search_json(
            query=search_query,
            system_prompt="你是专业的用户研究分析师，擅长搜索和整理用户画像数据。",
            temperature=0.3,
            max_tokens=3000,
            expected_type=dict
        )
        
        # 构建输出 - 使用正确的字段名匹配state.py中的AudienceProfile定义
        age_distribution = AgeDistribution(
            age_18_24=profile_data.get("age", {}).get("18-24", 35),
            age_25_34=profile_data.get("age", {}).get("25-34", 40),
            age_35_44=profile_data.get("age", {}).get("35-44", 18),
            age_45_plus=profile_data.get("age", {}).get("45+", 7)
        )
        
        top_regions = [
            RegionDistribution(
                name=region.get("name", ""),
                value=float(region.get("value", 0))
            )
            for region in profile_data.get("regions", [])[:10]
        ]
        
        # 构建观众画像对象 - 使用state.py中定义的字段名
        audience_profile = AudienceProfile(
            gender_female=profile_data.get("gender", {}).get("female", 95),
            gender_male=profile_data.get("gender", {}).get("male", 5),
            age_distribution=age_distribution,
            top_regions=top_regions,
            peak_viewing_hours=profile_data.get("peak_hours", "21:00-23:00"),
            avg_watch_duration=profile_data.get("avg_duration", "45分钟"),
            traits=["女性主导", "年轻群体", "下沉市场", "碎片化观看"]
        )
        
        return AudienceProfileOutput(audience_profile=audience_profile)
        
    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"audience_profile_node: 观众画像搜索或 JSON 解析失败: {e}"
        logger.error(error_message, exc_info=True)
        # 返回默认值
        default_profile = AudienceProfile(
            gender_female=95,
            gender_male=5,
            age_distribution=AgeDistribution(age_18_24=35, age_25_34=40, age_35_44=18, age_45_plus=7),
            top_regions=[
                RegionDistribution(name="广东", value=12.0),
                RegionDistribution(name="江苏", value=9.0),
                RegionDistribution(name="浙江", value=8.0)
            ],
            peak_viewing_hours="21:00-23:00",
            avg_watch_duration="45分钟",
            traits=["女性主导", "年轻群体", "下沉市场"]
        )
        return AudienceProfileOutput(
            audience_profile=default_profile,
            error_message=error_message + "\n"
        )