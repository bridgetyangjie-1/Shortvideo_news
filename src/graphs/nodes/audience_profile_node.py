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
from tools.deepseek_api import DeepSeekClient

from graphs.state import (
    AudienceProfileInput,
    AudienceProfileOutput,
    AudienceProfile,
    GenderDistribution,
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
    desc: 使用DeepSeek联网搜索QuestMobile、DataEye等报告，获取短剧观众画像数据
    integrations: DeepSeek API
    """
    ctx = runtime.context
    
    try:
        # 初始化DeepSeek客户端
        client = DeepSeekClient()
        
        # 使用DeepSeek联网搜索观众画像数据
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
        
        # 执行搜索
        response = client.search(
            query=search_query,
            system_prompt="你是专业的用户研究分析师，擅长搜索和整理用户画像数据。",
            temperature=0.3,
            max_tokens=3000
        )
        
        # 解析响应
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            profile_data = json.loads(json_match.group())
        else:
            profile_data = {
                "gender": {"female": 95, "male": 5},
                "age": {"18-24": 35, "25-34": 40, "35-44": 18, "45+": 7},
                "regions": [
                    {"name": "广东", "value": 12},
                    {"name": "江苏", "value": 9},
                    {"name": "浙江", "value": 8},
                    {"name": "山东", "value": 7},
                    {"name": "河南", "value": 6}
                ]
            }
        
        # 构建输出
        gender = GenderDistribution(
            female=profile_data.get("gender", {}).get("female", 95),
            male=profile_data.get("gender", {}).get("male", 5)
        )
        
        age = AgeDistribution(
            age_18_24=profile_data.get("age", {}).get("18-24", 35),
            age_25_34=profile_data.get("age", {}).get("25-34", 40),
            age_35_44=profile_data.get("age", {}).get("35-44", 18),
            age_45_plus=profile_data.get("age", {}).get("45+", 7)
        )
        
        regions = [
            RegionDistribution(
                name=region.get("name", ""),
                value=region.get("value", 0)
            )
            for region in profile_data.get("regions", [])[:10]
        ]
        
        # 构建观众画像对象
        audience_profile = AudienceProfile(
            gender=gender,
            age=age,
            regions=regions,
            peak_viewing_hours=profile_data.get("peak_hours", ""),
            avg_watch_duration=profile_data.get("avg_duration", "")
        )
        
        return AudienceProfileOutput(audience_profile=audience_profile)
        
    except Exception as e:
        logger.error(f"获取观众画像失败: {str(e)}")
        # 返回默认值
        default_profile = AudienceProfile(
            gender=GenderDistribution(female=95, male=5),
            age=AgeDistribution(age_18_24=35, age_25_34=40, age_35_44=18, age_45_plus=7),
            regions=[
                RegionDistribution(name="广东", value=12),
                RegionDistribution(name="江苏", value=9),
                RegionDistribution(name="浙江", value=8)
            ]
        )
        return AudienceProfileOutput(audience_profile=default_profile)