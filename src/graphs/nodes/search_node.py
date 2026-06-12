"""
数据抓取节点 - 直接爬取红果官网 + Kimi搜索补充行业数据
优化版：删除冗余Kimi调用，只保留1次行业数据搜索
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.moonshot_api import MoonshotClient
from tools.hongguo_crawler import fetch_hongguo_data

# Fallback for test_run environment
try:
    from tools.moonshot_api import is_api_budget_error
except ImportError:
    def is_api_budget_error(exc: Exception) -> bool:
        return str(exc) == "API 调用次数过多，已熔断"

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
    desc: 直接爬取红果官网榜单（主要） + Kimi搜索行业数据（1次调用）
    integrations: 红果官网爬虫, Moonshot API
    """
    ctx = runtime.context
    
    # 处理默认日期
    data_date = state.data_date
    if not data_date:
        data_date = datetime.now().strftime("%Y-%m-%d")
    try:
        anchor_dt = datetime.strptime(data_date, "%Y-%m-%d")
    except ValueError:
        anchor_dt = datetime.now()
    current_month = f"{anchor_dt.year}年{anchor_dt.month}月"
    
    search_results: List[Dict[str, Any]] = []
    hongguo_data: List[Dict[str, Any]] = []
    
    try:
        # ========== 第一步：直接爬取红果官网（主要数据源）==========
        logger.info("=" * 50)
        logger.info("第一步：直接爬取红果官网榜单")
        logger.info("=" * 50)
        
        hongguo_data = fetch_hongguo_data(max_count=100)
        
        if hongguo_data:
            logger.info(f"✅ 红果官网爬取成功，获取 {len(hongguo_data)} 条数据")
            
            # 添加到搜索结果
            search_results.append({
                "keyword": "红果官网直接爬取",
                "title": f"红果短剧榜单 {data_date}",
                "url": "hongguo_direct_crawler",
                "snippet": f"直接从红果官网爬取 {len(hongguo_data)} 条实时榜单数据",
                "summary": json.dumps(hongguo_data, ensure_ascii=False),
                "site_name": "红果官网爬虫",
                "publish_time": data_date,
                "raw_content": json.dumps(hongguo_data, ensure_ascii=False),
                "type": "hongguo_direct",
                "data_count": len(hongguo_data)
            })
        else:
            logger.warning("⚠️ 红果官网爬取失败，将依赖Kimi搜索")
        
        # ========== 第二步：Kimi搜索行业宏观数据（仅1次调用）==========
        logger.info("=" * 50)
        logger.info("第二步：Kimi搜索补充行业数据（仅1次调用）")
        logger.info("=" * 50)
        
        client = MoonshotClient()
        
        # 行业数据搜索（唯一保留的Kimi搜索）
        industry_prompt = f"""当前系统时间为 {current_month}（数据日期：{data_date}）。
请联网搜索短剧行业最新宏观数据：
1. 用户规模（APP月活、大盘用户数）
2. 市场规模（GMV、充值收入）
3. AI短剧占比
4. 平台分布

数据源建议：
- DataEye短剧行业报告
- 新腕儿行业分析
- 艾媒咨询短剧行业报告

请返回JSON格式：
{{
  "user_scale": "用户规模数据",
  "market_size": "市场规模数据",
  "ai_ratio": "AI短剧占比",
  "platform_distribution": "平台分布数据"
}}
"""
        
        try:
            industry_response = client.search(query=industry_prompt, max_results=5)
            search_results.append({
                "keyword": "行业宏观数据",
                "title": f"短剧行业宏观数据 {data_date}",
                "url": "moonshot-web-search-industry",
                "snippet": industry_response[:500] if len(industry_response) > 500 else industry_response,
                "summary": industry_response,
                "site_name": "Kimi联网搜索",
                "publish_time": data_date,
                "raw_content": industry_response,
                "type": "industry_data"
            })
            logger.info("✅ 行业数据搜索完成")
        except Exception as e:
            logger.warning(f"行业数据搜索失败: {e}")
        
        logger.info("=" * 50)
        logger.info(f"数据抓取完成：红果直接爬取 {len(hongguo_data)} 条 + Kimi补充 1 类数据")
        logger.info("=" * 50)
        
        return SearchNodeOutput(
            data_date=data_date,
            search_results=search_results,
            success=True
        )
        
    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"search_node: 数据抓取失败: {e}"
        logger.error(error_message, exc_info=True)
        return SearchNodeOutput(
            data_date=data_date,
            search_results=search_results,
            success=False,
            error_message=error_message + "\n"
        )
