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
            f"短剧行业 最新新闻 {date_str}",
            f"DataEye 短剧热度榜 {date_str}",
            f"短剧行业 融资 政策 {date_str}"
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
        analysis_prompt = f"""基于以下搜索结果，提炼短剧行业最重要的行业快讯。

搜索结果：
{combined_results}

当前日期：{date_str}

🚨【时间铁律 - 最高优先级】
⚠️ 只返回【今日：{date_str}】发布的新闻！
⚠️ 搜索结果中的旧新闻（2024年、2025年等往年数据）一律丢弃！
⚠️ 如果搜索结果中没有今日新闻，返回空数组[]

🚨【真实性铁律 - 最高优先级】
- 绝对忠实于上方真实搜索结果，严禁捏造新闻、数据、机构名称、发布时间和虚假链接。
- source_url 必须是搜索结果中明确出现过的真实原文URL；禁止填写门户首页、搜索页、空链接或臆造链接。
- 如果某条新闻没有可确认的真实 source_url，必须丢弃该条新闻。
- 如果搜索不到足够的高质量新闻，返回实际搜到的数量即可，宁缺毋滥；可以少于5条，甚至返回空数组[]。

🚨【内容结构铁律 - 必须逐条执行】
- 严格输出合法JSON数组格式，最多5条。
- 每条content必须是250-350字的高信息密度深度摘要，必须基于搜索结果和短剧行业认知进行推理与扩写。
- content字段必须严格按以下“四段式”输出，禁止合并段落，禁止删改段落标题，四段之间必须使用JSON字符串中的换行转义符\\n连接。
- 生成JSON时必须把换行写成\\n，不要输出未转义的真实换行，避免JSON解析失败。
- content必须严格使用以下四段结构：
  【事件核心】：详细陈述事件的来龙去脉、核心动作、发布时间、相关平台/公司/机构和关键细节。
  【数据支撑】：挖掘搜索结果中的金额、播放量、热度、份额、增速、榜单名次等核心数据；若无具体数字，必须明确说明可验证的定性趋势，不得编造数字。
  【商业洞察】：深度剖析该事件对短剧大盘走向、买量成本、内容供给、平台分发或行业竞争格局的长期影响。
  【决策价值】：明确指出该新闻对短剧制作方、投流团队、平台方或投资方的具体指导意义，例如“建议优先布局XX题材”或“需警惕XX合规风险”。
- title控制在15字以内，type只能为“预警”“商业”“数据”之一，icon需与type匹配。

输出格式（合法JSON数组，不要加```json包裹）：
[
  {{
    "type": "预警|商业|数据",
    "icon": "⚠️|💰|📊",
    "title": "标题（15字以内）",
    "content": "【事件核心】：...\\n【数据支撑】：...\\n【商业洞察】：...\\n【决策价值】：...",
    "source_url": "原文链接URL"
  }}
]
"""
        
        response = ds_client.chat(
            messages=[
                {"role": "system", "content": sp or "你是专业的短剧行业商业分析师，擅长从真实新闻中提炼高信息密度快讯，并输出具备产业判断、投放参考和投资决策价值的结构化内容。必须输出纯JSON数组，不要加任何Markdown标记；JSON字符串内的换行必须转义为\\n。"},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=temperature,
            max_tokens=4000
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
                    source_url = str(item.get("source_url") or item.get("source", "")).strip()
                    if not source_url.startswith(("http://", "https://")):
                        logger.warning(f"news_node: 丢弃缺少真实URL的快讯: {item.get('title', '')}")
                        continue
                    if source_url not in combined_results:
                        logger.warning(f"news_node: 丢弃搜索结果中未出现URL的快讯: {item.get('title', '')}")
                        continue
                    news_item = DailyNews(
                        type=str(item.get("type", "数据")),
                        icon=str(item.get("icon", "📊")),
                        title=str(item.get("title", ""))[:15],
                        content=str(item.get("content", ""))[:600],
                        insight=str(item.get("insight", ""))[:150],
                        source_url=source_url
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
    
    # 宁缺毋滥：没有真实搜索结果时返回空列表，避免发布兜底假新闻。
    if not daily_news:
        logger.warning("未生成带真实原文链接的有效快讯，返回空列表")
    
    return NewsNodeOutput(
        daily_news=daily_news[:5],
        error_message=("\n".join(search_errors) + "\n") if search_errors else ""
    )