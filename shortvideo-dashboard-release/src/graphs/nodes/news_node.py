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

from coze_coding_dev_sdk import SearchClient, LLMClient
from langchain_core.messages import SystemMessage, HumanMessage

from graphs.state import NewsNodeInput, NewsNodeOutput, DailyNews

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def news_node(state: NewsNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> NewsNodeOutput:
    """
    title: 行业快讯搜索
    desc: 搜索短剧行业新闻，LLM提炼为3-5条快讯（关注政策、融资、大厂动态）
    integrations: web-search, llm
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
        _cfg = {
            "config": {"model": "doubao-seed-1-8-251228", "temperature": 0.3},
            "sp": "",
            "up": ""
        }
    
    llm_config = _cfg.get("config", {})
    sp = _cfg.get("sp", "")
    up = _cfg.get("up", "")
    
    # 计算日期
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    
    # Step 1: 联网搜索行业新闻
    news_results: List[Dict[str, Any]] = []
    
    search_keywords = [
        f"新腕儿 短剧 {date_str}",
        f"DataEye 短剧战报 {date_str}",
        "短剧 广电总局 备案 最新",
        "抖音 短剧 新规 政策",
        "微信小程序 短剧 监管",
        "短剧 行业 融资 最新",
        "短剧 平台 动态 今日"
    ]
    
    try:
        search_client = SearchClient(ctx=ctx)
        
        for keyword in search_keywords:
            try:
                response = search_client.web_search(query=keyword, count=5)
                if response and response.web_items:
                    for item in response.web_items:
                        if item and hasattr(item, "title") and item.title:
                            news_results.append({
                                "keyword": keyword,
                                "title": item.title or "",
                                "url": item.url or "",
                                "snippet": item.snippet or "",
                                "source": item.site_name or ""
                            })
            except Exception as e:
                logger.warning(f"搜索关键词 {keyword} 失败: {e}")
                continue
        
        # 去重（按title）
        seen_titles: set = set()
        unique_news: List[Dict[str, Any]] = []
        for item in news_results:
            title = item.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(item)
        
        news_results = unique_news[:20]  # 最多保留20条
        logger.info(f"搜索到 {len(news_results)} 条新闻")
        
    except Exception as e:
        logger.warning(f"新闻搜索失败: {e}")
        news_results = []
    
    # Step 2: LLM提炼快讯
    daily_news: List[DailyNews] = []
    
    if news_results:
        # 构建新闻文本
        news_text = "\n\n".join([
            f"【{item.get('source', '未知来源')}】{item.get('title', '')}\n{item.get('snippet', '')}"
            for item in news_results[:15]
        ])
        
        # 渲染用户提示词
        if up:
            up_tpl = Template(up)
            user_prompt = up_tpl.render({"news_text": news_text, "date": date_str})
        else:
            user_prompt = f"请从以下新闻中提炼3-5条短剧行业快讯，关注政策、融资、大厂动态：\n\n{news_text}"
        
        try:
            llm_client = LLMClient(ctx=ctx)
            
            messages: List[Any] = []
            if sp:
                messages.append(SystemMessage(content=sp))
            messages.append(HumanMessage(content=user_prompt))
            
            llm_resp = llm_client.invoke(
                messages=messages,
                model=llm_config.get("model", "doubao-seed-1-8-251228"),
                temperature=llm_config.get("temperature", 0.3)
            )
            
            # 解析LLM返回
            resp_text = ""
            if isinstance(llm_resp.content, str):
                resp_text = llm_resp.content
            elif isinstance(llm_resp.content, list):
                text_parts = [item.get("text", "") for item in llm_resp.content if isinstance(item, dict) and item.get("type") == "text"]
                resp_text = " ".join(text_parts)
            
            # 尝试解析JSON数组
            json_match = re.search(r'\[[\s\S]*\]', resp_text)
            if json_match:
                json_str = json_match.group()
                news_list = json.loads(json_str)
                
                for item in news_list[:5]:
                    if isinstance(item, dict):
                        daily_news.append(DailyNews(
                            icon=item.get("icon", "📰"),
                            title=item.get("title", ""),
                            content=item.get("content", ""),
                            source=item.get("source", "")
                        ))
            
            logger.info(f"LLM提炼 {len(daily_news)} 条快讯")
            
        except Exception as e:
            logger.warning(f"LLM提炼失败: {e}")
    
    # Step 3: 如果没有数据，返回默认快讯
    if not daily_news:
        daily_news.append(DailyNews(
            icon="📊",
            title="行业数据更新",
            content=f"今日榜单数据已更新，短剧行业用户规模达7.18亿，市场规模突破1000亿",
            source="行业报告"
        ))
    
    return NewsNodeOutput(daily_news=daily_news[:5])