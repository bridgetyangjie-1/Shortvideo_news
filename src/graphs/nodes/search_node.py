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
from utils.runtime import Context
from tools.deepseek_api import DeepSeekClient
from graphs.state import SearchNodeInput, SearchNodeOutput


# 初始化日志
logger = logging.getLogger(__name__)


def search_node(
    state: SearchNodeInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> SearchNodeOutput:
    """
    title: 📊 抓取短剧行业数据
    desc: 使用DeepSeek联网搜索从多个公开数据源搜索短剧榜单信息
    integrations: DeepSeek API
    """
    ctx = runtime.context
    
    # 处理默认日期
    data_date = state.data_date
    if not data_date:
        data_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # 初始化DeepSeek客户端
        client = DeepSeekClient()
        
        # 构建搜索提示词
        search_prompt = f"""请搜索互联网，获取最新的短剧行业数据。重点关注以下数据源：

1. DataEye短剧热力榜 - 热播短剧排名、播放量数据
2. 云合数据短剧报告 - 有效播放、市占率分析
3. 红果短剧周榜 - 红果平台热门短剧排名
4. QuestMobile短剧用户分析 - 用户规模、画像数据
5. 其他公开的短剧榜单数据源

日期参考：{data_date}

请返回：
1. 今日/本周热播短剧TOP10榜单（包含剧名、播放量、平台）
2. 行业宏观数据（用户规模、市场规模、增长趋势）
3. 重点平台数据（红果、抖音等平台的MAU、活跃度）
4. 最新演员人气数据

格式要求：
- 返回具体的数值和事实
- 尝试标注数据来源
- 如果某些数据无法获取，标注"暂无数据"
"""
        
        # 执行搜索
        logger.info(f"开始搜索短剧行业数据，日期: {data_date}")
        response = client.search(
            query=search_prompt,
            system_prompt="你是一个专业的数据分析师，擅长从互联网搜索并整理行业数据。请搜索最新的公开数据源，返回具体的事实和数值。",
            temperature=0.3,
            max_tokens=8192
        )
        
        # 处理搜索结果
        # DeepSeek的搜索会返回整合后的文本，我们需要将其转换为结构化格式
        search_results: List[Dict[str, Any]] = []
        
        # 将搜索结果作为一条整合记录
        search_results.append({
            "keyword": "短剧行业综合数据",
            "title": f"短剧行业数据报告 {data_date}",
            "url": "deepseek-search",
            "snippet": response[:500] if len(response) > 500 else response,
            "summary": response,
            "site_name": "DeepSeek联网搜索",
            "publish_time": data_date,
            "raw_content": response  # 保留完整内容供后续节点处理
        })
        
        logger.info(f"搜索完成，获取到数据长度: {len(response)} 字符")
        
        return SearchNodeOutput(
            data_date=data_date,
            search_results=search_results,
            success=True
        )
        
    except Exception as e:
        logger.error(f"搜索失败: {str(e)}")
        return SearchNodeOutput(
            data_date=data_date,
            search_results=[],
            success=False
        )