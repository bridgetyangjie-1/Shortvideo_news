import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from jinja2 import Template

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import SearchClient, LLMClient

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
    desc: 搜索QuestMobile、DataEye等报告，获取短剧观众画像数据
    integrations: Web Search, 大语言模型
    """
    ctx = runtime.context
    
    try:
        # 初始化搜索客户端
        search_client = SearchClient(ctx=ctx)
        
        # 搜索关键词
        search_keywords = [
            "短剧用户画像 QuestMobile 2024",
            "短剧观众年龄性别分布 DataEye",
            "短剧用户地域分布 抖音红果",
            "短剧受众分析报告 2024"
        ]
        
        search_results: List[str] = []
        for keyword in search_keywords:
            try:
                response = search_client.web_search_with_summary(
                    query=keyword,
                    count=5
                )
                if response.web_items:
                    for item in response.web_items:
                        if item.summary:
                            search_results.append(item.summary)
                        elif item.snippet:
                            search_results.append(item.snippet)
            except Exception as e:
                logger.warning(f"搜索关键词 '{keyword}' 失败: {str(e)}")
                continue
        
        # 读取LLM配置
        cfg_file = os.path.join(
            os.getenv("COZE_WORKSPACE_PATH", "."), 
            config["metadata"]["llm_cfg"]
        )
        with open(cfg_file, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        
        llm_config = cfg.get("config", {})
        sp = cfg.get("sp", "")
        up = cfg.get("up", "")
        
        # 准备搜索上下文
        search_context = "\n\n".join(search_results[:8]) if search_results else "暂无搜索结果"
        
        # 渲染用户提示词
        up_tpl = Template(up)
        user_prompt = up_tpl.render({"search_context": search_context})
        
        # 使用大模型解析观众画像
        llm_client = LLMClient(ctx=ctx)
        
        messages = [
            SystemMessage(content=sp),
            HumanMessage(content=user_prompt)
        ]
        
        response = llm_client.invoke(
            messages=messages,
            model=llm_config.get("model", "doubao-seed-1-8-251228"),
            temperature=llm_config.get("temperature", 0.3),
            max_completion_tokens=llm_config.get("max_completion_tokens", 2000)
        )
        
        # 解析响应
        response_content = response.content
        if not isinstance(response_content, str):
            if isinstance(response_content, list):
                text_parts = [
                    item.get("text", "") 
                    for item in response_content 
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                response_content = " ".join(text_parts)
            else:
                response_content = str(response_content)
        
        # 提取JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_content)
        if json_match:
            profile_data = json.loads(json_match.group())
        else:
            # 使用默认值
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
            regions=regions
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
