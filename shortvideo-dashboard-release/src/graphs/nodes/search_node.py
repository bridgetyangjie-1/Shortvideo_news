"""
数据抓取节点 - 抓取短剧行业数据
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import SearchClient
from graphs.state import SearchNodeInput, SearchNodeOutput


# 初始化日志
logger = logging.getLogger(__name__)


# 搜索关键词列表
SEARCH_KEYWORDS = [
    "DataEye短剧热力榜",
    "云合数据短剧报告", 
    "QuestMobile短剧用户分析",
    "红果短剧周榜排名",
    "短剧热度排行榜 2024"
]


def search_node(
    state: SearchNodeInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> SearchNodeOutput:
    """
    title: 📊 抓取短剧行业数据
    desc: 从多个公开数据源搜索短剧榜单信息，包括DataEye、云合数据等
    integrations: Web Search
    """
    ctx = runtime.context
    
    # 处理默认日期
    data_date = state.data_date
    if not data_date:
        data_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # 初始化搜索客户端
        client = SearchClient(ctx=ctx)
        
        all_results: List[Dict[str, Any]] = []
        
        # 遍历关键词进行搜索
        for keyword in SEARCH_KEYWORDS:
            try:
                # 使用 web_search_with_summary 获取带AI摘要的结果
                response = client.web_search_with_summary(
                    query=f"{keyword} {data_date}",
                    count=10
                )
                
                # 提取搜索结果
                if response.web_items:
                    for item in response.web_items:
                        result_item: Dict[str, Any] = {
                            "keyword": keyword,
                            "title": item.title or "",
                            "url": item.url or "",
                            "snippet": item.snippet or "",
                            "summary": item.summary or "",
                            "site_name": item.site_name or "",
                            "publish_time": item.publish_time or ""
                        }
                        all_results.append(result_item)
                
            except Exception as e:
                # 单个关键词失败不影响整体流程
                logger.warning(f"搜索关键词 '{keyword}' 失败: {str(e)}")
                continue
        
        # 检查是否有结果
        if not all_results:
            return SearchNodeOutput(
                data_date=data_date,
                search_results=[],
                success=False
            )
        
        return SearchNodeOutput(
            data_date=data_date,
            search_results=all_results,
            success=True
        )
        
    except Exception as e:
        return SearchNodeOutput(
            data_date=data_date,
            search_results=[],
            success=False
        )
