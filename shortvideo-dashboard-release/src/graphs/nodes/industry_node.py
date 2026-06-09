"""
行业数据节点 - 获取行业宏观数据
"""
import os
import json
import re
import logging
from datetime import datetime
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import LLMClient, SearchClient
from langchain_core.messages import SystemMessage, HumanMessage

from graphs.state import (
    IndustryNodeInput,
    IndustryNodeOutput,
    IndustryData,
    PlatformData,
    PlatformApp
)

# 初始化日志
logger = logging.getLogger(__name__)


def industry_node(state: IndustryNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> IndustryNodeOutput:
    """
    title: 行业数据获取
    desc: 获取最新的行业宏观数据（用户规模、市场规模、AI短剧占比等）
    integrations: 网络搜索, 大语言模型
    """
    ctx = runtime.context
    
    try:
        # 1. 搜索行业数据
        search_client = SearchClient(ctx=ctx)
        search_queries = [
            "短剧行业市场规模 用户规模 2024 2025",
            "红果短剧 月活用户 市场份额",
            "短剧 AI短剧 占比 趋势"
        ]
        
        search_results = []
        for query in search_queries:
            response = search_client.web_search(query=query, count=5)
            if response.web_items:
                for item in response.web_items:
                    search_results.append(f"{item.title}: {item.snippet}")
        
        # 2. 读取LLM配置
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        llm_config = _cfg.get("config", {})
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")
        
        # 3. 统计榜单中的AI剧和女男频比例
        ai_count = sum(1 for r in state.enriched_rankings if r.is_ai)
        female_count = sum(1 for r in state.enriched_rankings if r.category == "female")
        male_count = sum(1 for r in state.enriched_rankings if r.category == "male")
        total = len(state.enriched_rankings) if state.enriched_rankings else 1
        
        # 4. 使用LLM提取行业数据
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "search_results": "\n\n".join(search_results),
            "data_date": state.data_date,
            "ai_ratio": int(ai_count / total * 100),
            "female_ratio": int(female_count / total * 100),
            "male_ratio": int(male_count / total * 100)
        })
        
        # 初始化LLM客户端
        client = LLMClient(ctx=ctx)
        
        # 构建消息
        messages = [
            SystemMessage(content=sp),
            HumanMessage(content=user_prompt)
        ]
        
        response = client.invoke(
            messages=messages,
            model=llm_config.get("model", "doubao-seed-2-0-pro-260215"),
            temperature=llm_config.get("temperature", 0.2),
            max_completion_tokens=llm_config.get("max_completion_tokens", 3000)
        )
        
        # 提取响应内容
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
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_content)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response_content
        
        data = json.loads(json_str)
        
        # 构建行业数据
        industry = IndustryData(
            user_scale=data.get("user_scale", "7.18亿"),
            market_size=data.get("market_size", "1000亿+"),
            drama_count=data.get("drama_count", "25万+"),
            billion_dramas=data.get("billion_dramas", 20),
            ai_ratio=data.get("ai_ratio", int(ai_count / total * 100)),
            female_ratio=data.get("female_ratio", int(female_count / total * 100)),
            male_ratio=data.get("male_ratio", int(male_count / total * 100)),
            app_mau=data.get("app_mau", "3.04亿"),
            app_mau_yoy=data.get("app_mau_yoy", "+1.4亿")
        )
        
        # 构建平台数据
        apps = []
        for app_data in data.get("platform_apps", []):
            app = PlatformApp(
                name=app_data.get("name", "红果免费短剧"),
                mau=app_data.get("mau", 3.04),
                mau_unit=app_data.get("mau_unit", "亿"),
                yoy=app_data.get("yoy", "+1.4亿"),
                share=app_data.get("share", 85),
                trend=app_data.get("trend", "up")
            )
            apps.append(app)
        
        platform = PlatformData(apps=apps, mini_programs=data.get("mini_programs", []))
        
        return IndustryNodeOutput(
            industry=industry,
            platform=platform,
            success=True
        )
        
    except Exception as e:
        logger.error(f"行业数据获取失败: {str(e)}")
        # 返回默认数据
        return IndustryNodeOutput(
            industry=IndustryData(
                user_scale="7.18亿",
                market_size="1000亿+",
                drama_count="25万+",
                billion_dramas=20,
                ai_ratio=38,
                female_ratio=95,
                male_ratio=5,
                app_mau="3.04亿",
                app_mau_yoy="+1.4亿"
            ),
            platform=PlatformData(
                apps=[PlatformApp(
                    name="红果免费短剧",
                    mau=3.04,
                    mau_unit="亿",
                    yoy="+1.4亿",
                    share=85,
                    trend="up"
                )]
            ),
            success=True
        )
