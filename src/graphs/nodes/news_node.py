"""
行业快讯节点 - 双模型协同解耦架构
Kimi负责搜索，DeepSeek负责推理
"""
import os
import json
import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Any
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from tools.moonshot_api import MoonshotClient
from tools.deepseek_api import DeepSeekClient

from graphs.state import NewsNodeInput, NewsNodeOutput, DailyNews

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def news_node(state: NewsNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> NewsNodeOutput:
    """
    title: 行业快讯（双模型协同）
    desc: Kimi搜索新闻 → DeepSeek推理生成JSON快讯
    integrations: Moonshot API + DeepSeek API
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
    
    # 初始化双客户端
    kimi_client = MoonshotClient()
    ds_client = DeepSeekClient()
    
    # 初始化默认快讯列表
    daily_news: List[DailyNews] = []
    search_errors: List[str] = []
    
    try:
        # ========== 搜集阶段：Kimi搜索 ==========
        search_queries = [
            "短剧行业 最新新闻 2024 2025",
            "DataEye 短剧热度榜 最新",
            "广电总局 短剧新规 政策"
        ]
        
        search_results: List[str] = []
        for query in search_queries:
            try:
                result = kimi_client.search(query, max_results=3)
                logger.info(f"Kimi搜索 '{query}' 成功")
                search_results.append(f"【搜索: {query}】\n{result}")
                time.sleep(1)  # 🚨 节流阀（Tier 7配额充足）
            except Exception as se:
                search_error = f"news_node: Kimi搜索 '{query}' 失败: {se}"
                logger.warning(search_error)
                search_errors.append(search_error)
        
        # 合并搜索结果
        combined_results = "\n\n".join(search_results)
        
        # ========== 推理阶段：DeepSeek生成JSON ==========
        analysis_prompt = f"""基于以下搜索结果，提炼短剧行业最重要的5条新闻。

搜索结果：
{combined_results}

当前日期：{date_str}

🚨【核心铁律】
- 必须返回5条新闻，严格输出JSON数组格式
- 每条content不超过100字（精简总结）
- 每条必须有source_url（从搜索结果中提取的真实原文链接）

输出格式（合法JSON数组，不要加```json包裹）：
[
  {{
    "type": "预警|商业|数据",
    "icon": "⚠️|💰|📊",
    "title": "标题（15字以内）",
    "content": "内容缩写（不超过100字）",
    "source_url": "原文链接URL"
  }}
]
"""
        
        response = ds_client.chat(
            messages=[
                {"role": "system", "content": sp or "你是专业的短剧行业分析师，擅长从新闻中提炼关键快讯。必须输出纯JSON数组，不要加任何Markdown标记。"},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=temperature,
            max_tokens=2000
        )
        
        logger.info(f"DeepSeek响应: {response[:500]}...")
        
        # ========== 健壮性解析：正则提取JSON ==========
        try:
            # 去除Markdown代码块标记
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            # 正则提取JSON数组
            json_match = re.search(r'\[[\s\S]*\]', clean_response)
            if json_match:
                json_str = json_match.group(0)
                news_list = json.loads(json_str)
            else:
                raise ValueError("未找到有效JSON数组")
            
            for item in news_list[:5]:
                if isinstance(item, dict):
                    news_item = DailyNews(
                        type=str(item.get("type", "数据")),
                        icon=str(item.get("icon", "📊")),
                        title=str(item.get("title", ""))[:15],
                        content=str(item.get("content", ""))[:100],
                        source_url=str(item.get("source_url") or item.get("source", "") or "https://www.newwanr.com")
                    )
                    daily_news.append(news_item)
                    
        except Exception as parse_error:
            logger.error(f"news_node: JSON解析失败: {parse_error}")
            logger.error(f"原始响应: {response}")
            search_errors.append(f"JSON解析失败: {parse_error}")
        
        logger.info(f"生成 {len(daily_news)} 条快讯")
        
    except Exception as e:
        error_msg = f"news_node: 快讯生成失败: {e}"
        logger.warning(error_msg, exc_info=True)
        search_errors.append(error_msg)
    
    # 兜底：如果没有数据，返回默认快讯
    if not daily_news:
        logger.error("未生成有效快讯，使用默认兜底")
        daily_news.append(DailyNews(
            type="数据",
            icon="📊",
            title="行业数据更新",
            content="今日榜单数据已更新，短剧行业用户规模达7.18亿，市场规模突破1000亿。",
            source_url="https://www.newwanr.com"
        ))
    
    return NewsNodeOutput(
        daily_news=daily_news[:5],
        error_message=("\n".join(search_errors) + "\n") if search_errors else ""
    )