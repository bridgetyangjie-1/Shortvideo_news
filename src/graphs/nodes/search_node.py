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
from tools.moonshot_api import MoonshotClient

# Fallback for test_run environment
try:
    from tools.moonshot_api import is_api_budget_error
except ImportError:
    def is_api_budget_error(exc: Exception) -> bool:
        return str(exc) == "API \u8c03\u7528\u6b21\u6570\u8fc7\u591a\uff0c\u5df2\u718f\u65ad"
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
    desc: 使用 Kimi 联网搜索从多个公开数据源搜索短剧榜单信息
    integrations: Moonshot API
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
    
    try:
        # 初始化 Kimi 客户端
        client = MoonshotClient()
        
        # 构建搜索提示词 - 强调实时在榜与真实数据
        search_prompt = f"""当前系统时间为 {current_month}（数据日期：{data_date}）。你必须联网搜索，并且只能搜索、提取最近 3-7 天内仍在实时榜单上活跃的最新短剧热度数据。禁止使用历史总榜、累计播放榜、年度榜或过期榜单替代今日/近期榜单。

你必须获取真实的短剧行业数据，禁止编造任何剧名或数据！

调用搜索工具时，必须优先使用带有强时效性的关键词组合，例如：
1. "{current_month} 短剧 日榜"
2. "{current_month} 短剧 热力榜 最新"
3. "DataEye 短剧热力榜 最新"
4. "抖音短剧 最热榜 今天"
5. "红果短剧 热播榜 今日"
6. "小红书 最新短剧推荐 {current_month}"
7. "短剧 新晋爆款 近7天 热度"

请搜索以下真实数据源，且只采纳最新日榜、周榜、实时热榜或近 3-7 天榜单：
1. DataEye短剧热力榜 (dataeye.cn) - 最新短剧日榜/热力榜
2. 新腕儿短剧榜单 - 最新短剧热度排行
3. 红果短剧官方榜单 - 红果平台今日/近期热门短剧
4. 抖音短剧热榜 - 抖音平台今日热播数据
5. 小红书最新短剧推荐 - 近期正在起量的新晋爆款线索

日期参考：{data_date}

严格要求：
- 只返回你在网页上真实看到的剧名和数据
- 如果某平台无法搜索到，标注"该平台数据暂无法获取"
- 剧名必须是真实存在且最近 3-7 天仍在榜、正在起量的短剧
- 严禁返回《我在八零年代当后妈》《无双》等早已完结、仅因历史累计播放量高而出现在总榜上的老剧
- 我需要的是目前正在起量的"新晋爆款"，不是历史经典、累计总播放量冠军或年度回顾榜单
- 播放量/热度必须尽量提取"单日新增播放量"、"今日热度"、"近7天热度"、"实时热度值"等近期指标；不要使用历史累计总播放量作为主要排序依据
- 如果网页只提供累计播放量，必须明确标注"累计指标，不作为优先排序依据"，并优先寻找其他近期热度来源
- 榜单至少返回8条；如果能获取TOP20，请完整返回TOP20

请返回JSON格式：
{{
  "top20": [
    {{"rank": 1, "title": "真实剧名", "views": "单日新增/近期热度/实时热度", "platform": "真实平台"}}
  ],
  "industry_data": {{
    "user_scale": "用户规模数据",
    "market_size": "市场规模数据"
  }}
}}

如果无法获取真实数据，请如实说明原因。"""

        # 执行 Kimi 官方 $web_search 联网搜索
        logger.info(f"开始搜索短剧行业数据，日期: {data_date}")
        response = client.search(query=search_prompt, max_results=5)
        
        # 🔍 新增：搜索红果平台标签数据
        tag_search_prompt = f"""当前系统时间为 {current_month}（数据日期：{data_date}）。
请联网搜索最近 3-7 天内红果短剧平台、抖音短剧、小红书最新短剧推荐中的实时热门分类和标签。
必须使用 "{current_month} 红果短剧 热门标签 最新"、"短剧 新晋爆款 标签 近7天"、"抖音短剧 最热榜 今天 题材" 等强时效关键词。
只提取当前正在起量短剧的标签分布，避免历史累计总榜老剧带来的题材偏差。
关注分类/标签：都市、甜宠、重生、穿越、马甲、打脸。
热门短剧剧名 标签统计 近期热度排行 {data_date}"""

        tag_response = client.search(query=tag_search_prompt, max_results=5)
        
        logger.info(f"标签数据搜索完成，长度: {len(tag_response)} 字符")
        
        # 处理搜索结果
        # Kimi 搜索会返回整合后的文本，我们需要将其转换为结构化格式
        search_results: List[Dict[str, Any]] = []
        
        # 将搜索结果作为一条整合记录
        search_results.append({
            "keyword": "短剧行业综合数据",
            "title": f"短剧行业数据报告 {data_date}",
            "url": "moonshot-web-search",
            "snippet": response[:500] if len(response) > 500 else response,
            "summary": response,
            "site_name": "Kimi联网搜索",
            "publish_time": data_date,
            "raw_content": response  # 保留完整内容供后续节点处理
        })
        
        # 🔍 新增：添加标签数据记录
        search_results.append({
            "keyword": "红果平台标签数据",
            "title": f"红果短剧标签分布 {data_date}",
            "url": "moonshot-web-search-tags",
            "snippet": tag_response[:500] if len(tag_response) > 500 else tag_response,
            "summary": tag_response,
            "site_name": "Kimi联网搜索",
            "publish_time": data_date,
            "raw_content": tag_response,  # 保留完整内容供标签分析节点处理
            "type": "tag_data"  # 标记为标签数据
        })
        
        logger.info(f"搜索完成，获取到数据长度: {len(response)} 字符，标签数据长度: {len(tag_response)} 字符")
        
        return SearchNodeOutput(
            data_date=data_date,
            search_results=search_results,
            success=True
        )
        
    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"search_node: Kimi 联网搜索失败: {e}"
        logger.error(error_message, exc_info=True)
        return SearchNodeOutput(
            data_date=data_date,
            search_results=[],
            success=False,
            error_message=error_message + "\n"
        )