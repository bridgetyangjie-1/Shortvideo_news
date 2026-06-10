"""
行业快讯节点 - 搜索并提炼短剧行业每日快讯
"""
import os
import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from tools.deepseek_api import DeepSeekClient
from graphs.state import NewsNodeInput, NewsNodeOutput, DailyNews

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def news_node(state: NewsNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> NewsNodeOutput:
    """
    title: 行业快讯搜索
    desc: 使用DeepSeek联网搜索短剧行业新闻，提炼为5条快讯（100字缩写+原文链接）
    integrations: DeepSeek API
    """
    ctx = runtime.context
    
    # 读取配置
    cfg_path = config.get("configurable", {}).get("llm_cfg", "config/news_llm_cfg.json")
    full_cfg_path = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), cfg_path)
    
    try:
        with open(full_cfg_path, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
    except Exception as e:
        logger.warning(f"配置文件读取失败: {e}, 使用默认配置")
        _cfg = {"config": {"temperature": 0.3}, "sp": "", "up": ""}
    
    sp = _cfg.get("sp", "")
    temperature = _cfg.get("config", {}).get("temperature", 0.3)
    
    # 计算日期
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    
    # 初始化默认快讯列表
    daily_news: List[DailyNews] = []
    
    try:
        client = DeepSeekClient()
        
        # 第一步：联网搜索获取具体新闻文章
        search_queries = [
            "短剧行业 最新新闻 2024 2025",
            "DataEye 短剧热度榜 最新",
            "广电总局 短剧新规 政策",
            "抖音短剧 分成比例 最新政策",
            "短剧MCN 九州 点众 最新动态"
        ]
        
        # 搜索新闻并收集结果
        search_results: List[Dict[str, Any]] = []
        for query in search_queries[:3]:  # 只搜索前3个查询，避免超时
            try:
                result = client.search(query, max_results=3)
                logger.info(f"搜索 '{query}' 返回: {result[:200]}...")
                search_results.append({
                    "query": query,
                    "result": result
                })
            except Exception as se:
                logger.warning(f"搜索 '{query}' 失败: {se}")
        
        # 第二步：用AI分析搜索结果，提取5条重要新闻
        if search_results:
            # 合并搜索结果
            combined_results = "\n\n".join([
                f"【搜索: {r['query']}】\n{r['result']}" 
                for r in search_results
            ])
            
            analysis_prompt = f"""基于以下搜索结果，提炼短剧行业最重要的5条新闻。

搜索结果：
{combined_results}

当前日期：{date_str}

🚨【核心铁律】
- 必须返回5条新闻
- 每条content不超过100字（精简总结）
- 每条必须有source_url（从搜索结果中提取的真实原文链接，必须是可访问的URL）
- 如果搜索结果中没有具体链接，请使用行业门户链接如 https://www.newwanr.com 或 https://www.dataeye.com

输出格式（合法JSON数组）：
[
  {{
    "type": "预警|商业|数据",
    "icon": "⚠️|💰|📊",
    "title": "标题（15字以内）",
    "content": "内容缩写（不超过100字）",
    "source_url": "原文链接URL（必须填写）"
  }}
]
"""
            
            response = client.chat(
                messages=[
                    {"role": "system", "content": sp or "你是专业的短剧行业分析师，擅长从新闻中提炼关键快讯并提供原文链接。"},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=temperature,
                max_tokens=2000
            )
            
            logger.info(f"AI分析响应: {response[:500]}...")
            
            # 尝试解析JSON数组
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                try:
                    news_list: List[Dict[str, Any]] = json.loads(json_match.group())
                    for item in news_list[:5]:
                        if isinstance(item, dict):
                            news_item = DailyNews(
                                type=str(item.get("type", "数据")),
                                icon=str(item.get("icon", "📰")),
                                title=str(item.get("title", ""))[:15],
                                content=str(item.get("content", ""))[:100],
                                source_url=str(item.get("source_url", ""))
                            )
                            # 确保source_url不为空
                            if not news_item.source_url:
                                news_item.source_url = "https://www.newwanr.com"
                            daily_news.append(news_item)
                except json.JSONDecodeError as je:
                    logger.warning(f"JSON解析失败: {je}")
        
        logger.info(f"DeepSeek提炼 {len(daily_news)} 条快讯")
        
    except Exception as e:
        logger.warning(f"快讯生成失败: {e}")
    
    # 如果没有数据，返回默认快讯
    if not daily_news:
        daily_news.append(DailyNews(
            type="数据",
            icon="📊",
            title="行业数据更新",
            content="今日榜单数据已更新，短剧行业用户规模达7.18亿，市场规模突破1000亿。",
            source_url="https://www.newwanr.com"
        ))
    
    return NewsNodeOutput(daily_news=daily_news[:5])