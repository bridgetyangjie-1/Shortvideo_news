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
        # 初始化 Kimi 客户端
        client = MoonshotClient()
        
        # 构建搜索提示词 - 强调真实数据
        search_prompt = f"""你必须联网搜索，获取真实的短剧行业数据。禁止编造任何剧名或数据！

请搜索以下真实数据源：
1. DataEye短剧热力榜 (dataeye.cn) - 真实热播短剧排名
2. 新腕儿短剧榜单 - 眭剧热度排行
3. 红果短剧官方榜单 - 红果平台热门短剧
4. 抖音短剧热榜 - 抖音平台热播数据

日期参考：{data_date}

严格要求：
- 只返回你在网页上真实看到的剧名和数据
- 如果某平台无法搜索到，标注"该平台数据暂无法获取"
- 剧名必须是真实存在的短剧（如《我在八零年代当后妈》《重生之我在霸总身边当卧底》等）
- 播放量必须是真实数据，不要编造

请返回JSON格式：
{{
  "top10": [
    {{"rank": 1, "title": "真实剧名", "views": "真实播放量", "platform": "真实平台"}}
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
        tag_search_prompt = f"""红果短剧平台 最热分类 标签 都市 甜宠 重生 穿越 马甲 打脸
热门短剧剧名 标签统计 热度排行 {data_date}"""

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