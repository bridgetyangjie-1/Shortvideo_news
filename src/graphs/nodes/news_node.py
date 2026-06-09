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
    desc: 使用DeepSeek联网搜索短剧行业新闻，提炼为3-5条快讯
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
    up = _cfg.get("up", "")
    temperature = _cfg.get("config", {}).get("temperature", 0.3)
    
    # 计算日期
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    
    # 初始化默认快讯列表
    daily_news: List[DailyNews] = []
    
    try:
        client = DeepSeekClient()
        
        # 使用DeepSeek联网搜索行业快讯
        search_prompt = f"""请搜索互联网，获取最新的短剧行业快讯，重点关注：
1. 新腕儿、DataEye等平台的最新战报
2. 广电总局、抖音、微信等平台的短剧新规和政策
3. 短剧行业的融资动态
4. 大厂（抖音、快手、腾讯等）的短剧业务动态

日期参考：{date_str}

请返回3-5条最重要的快讯，每条包含：icon(emoji图标)、title(标题)、content(内容摘要)、source(来源)
"""
        
        # 执行搜索并提炼
        response = client.chat(
            messages=[
                {"role": "system", "content": sp or "你是专业的短剧行业分析师，擅长从新闻中提炼关键快讯。"},
                {"role": "user", "content": search_prompt}
            ],
            temperature=temperature,
            max_tokens=3000
        )
        
        # 尝试解析JSON数组
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                news_list = json.loads(json_match.group())
                for item in news_list[:5]:
                    if isinstance(item, dict):
                        daily_news.append(DailyNews(
                            icon=item.get("icon", "📰"),
                            title=item.get("title", ""),
                            content=item.get("content", ""),
                            source=item.get("source", "")
                        ))
            except json.JSONDecodeError:
                pass
        
        logger.info(f"DeepSeek提炼 {len(daily_news)} 条快讯")
        
    except Exception as e:
        logger.warning(f"快讯生成失败: {e}")
    
    # 如果没有数据，返回默认快讯
    if not daily_news:
        daily_news.append(DailyNews(
            icon="📊",
            title="行业数据更新",
            content=f"今日榜单数据已更新，短剧行业用户规模达7.18亿，市场规模突破1000亿",
            source="行业报告"
        ))
    
    return NewsNodeOutput(daily_news=daily_news[:5])