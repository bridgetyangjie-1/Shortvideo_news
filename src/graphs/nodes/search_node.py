"""
数据抓取节点 - 短剧工程周榜为主 + 红果推荐页为辅 + Kimi搜索补充行业数据
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
from tools.duanjugongcheng_crawler import fetch_latest_full_ranking, fetch_homepage_top10
from tools.hongguo_crawler import fetch_hongguo_data
# DataEye 榜单当前不可用，已停用
# from tools.dataeye_crawler import fetch_dataeye_rankings

# Fallback for test_run environment
try:
    from tools.moonshot_api import is_api_budget_error
except ImportError:
    def is_api_budget_error(exc: Exception) -> bool:
        return str(exc) == "API 调用次数过多，已熔断"

from graphs.state import SearchNodeInput, SearchNodeOutput


# 初始化日志
logger = logging.getLogger(__name__)


def _merge_hongguo_dataeye(hongguo_data: List[Dict], dataeye_data: List[Dict]) -> List[Dict]:
    """
    处理红果推荐页数据（DataEye 当前不可用，dataeye_data 通常为空）。
    
    注意：红果网页端返回的是推荐列表，不是真实热榜，仅用于补充元数据和日变化追踪。
    """
    if not dataeye_data:
        for drama in hongguo_data:
            drama["confidence_score"] = 0.5
            drama["data_source"] = "hongguo_recommend"
            drama["cross_validated"] = False
        return hongguo_data
    
    dataeye_index = {}
    for d in dataeye_data:
        title = d.get("title", "").strip()
        if title:
            dataeye_index[title] = d
    
    merged = []
    for hg_drama in hongguo_data:
        hg_title = hg_drama.get("title", "").strip()
        
        matched_de = None
        for de_title, de_data in dataeye_index.items():
            if hg_title in de_title or de_title in hg_title:
                matched_de = de_data
                break
        
        if matched_de:
            merged_drama = hg_drama.copy()
            merged_drama["confidence_score"] = 0.6
            merged_drama["data_source"] = "hongguo+dataeye"
            merged_drama["cross_validated"] = True
            merged_drama["dataeye_rank"] = matched_de.get("rank", 0)
            merged_drama["dataeye_heat"] = matched_de.get("heat", 0)
            if matched_de.get("heat", 0) > 0:
                merged_drama["heat"] = matched_de.get("heat", 0)
            merged.append(merged_drama)
        else:
            merged_drama = hg_drama.copy()
            merged_drama["confidence_score"] = 0.5
            merged_drama["data_source"] = "hongguo_recommend"
            merged_drama["cross_validated"] = False
            merged_drama["dataeye_rank"] = 0
            merged_drama["dataeye_heat"] = 0
            merged.append(merged_drama)
    
    return merged


def search_node(
    state: SearchNodeInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> SearchNodeOutput:
    """
    title: 📊 抓取短剧行业数据
    desc: 短剧工程周榜为主 + 红果推荐页为辅 + Kimi搜索行业数据
    integrations: 短剧工程爬虫, 红果官网爬虫, Moonshot API
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
    
    try:
        # ========== 第一步：爬取短剧工程周榜（主数据源）==========
        logger.info("=" * 50)
        logger.info("第一步：爬取短剧工程周榜（主数据源）")
        logger.info("=" * 50)
        
        duanju_data: List[Dict[str, Any]] = []
        try:
            # 优先获取首页最新 TOP10，如果完整周榜未生成则自动降级
            duanju_data = fetch_latest_full_ranking(anchor_dt)
            if duanju_data:
                week_date = duanju_data[0].get("week_date", data_date)
                logger.info(f"✅ 短剧工程周榜获取成功，共 {len(duanju_data)} 条，周榜日期 {week_date}")
                search_results.append({
                    "keyword": "短剧工程周榜",
                    "title": f"短剧工程周榜 {week_date}",
                    "url": "https://www.duanjugongcheng.com/cn/bangdan/",
                    "snippet": f"基于红果官方周榜，获取 {len(duanju_data)} 条，含热播指数、题材、上架日期",
                    "summary": json.dumps(duanju_data, ensure_ascii=False),
                    "site_name": "短剧工程",
                    "publish_time": week_date,
                    "raw_content": json.dumps(duanju_data, ensure_ascii=False),
                    "type": "duanjugongcheng_ranking",
                    "data_count": len(duanju_data),
                    "week_date": week_date,
                })
            else:
                logger.warning("⚠️ 短剧工程周榜未返回数据")
        except Exception as e:
            logger.warning(f"短剧工程周榜爬取失败: {e}")
        
        # ========== 第二步：爬取红果推荐页（辅助数据源）==========
        logger.info("=" * 50)
        logger.info("第二步：爬取红果首页推荐页（辅助/元数据补充）")
        logger.info("=" * 50)
        
        hongguo_data: List[Dict[str, Any]] = []
        try:
            hongguo_data = fetch_hongguo_data(max_count=100)
            if hongguo_data:
                logger.info(f"✅ 红果推荐页爬取成功，获取 {len(hongguo_data)} 条数据")
            else:
                logger.warning("⚠️ 红果推荐页未返回数据")
        except Exception as e:
            logger.warning(f"红果推荐页爬取失败: {e}")
        
        # 红果推荐页数据（仅作元数据补充，不再调用 DataEye）
        if hongguo_data:
            merged_data = _merge_hongguo_dataeye(hongguo_data, [])
            search_results.append({
                "keyword": "红果推荐页辅助",
                "title": f"红果推荐页辅助数据 {data_date}",
                "url": "hongguo_recommend",
                "snippet": f"红果推荐页{len(hongguo_data)}条",
                "summary": json.dumps(merged_data, ensure_ascii=False),
                "site_name": "红果推荐页",
                "publish_time": data_date,
                "raw_content": json.dumps(merged_data, ensure_ascii=False),
                "type": "hongguo_recommend",
                "data_count": len(merged_data),
            })
        
        # ========== 第三步：Kimi搜索补充行业数据（仅1次调用）==========
        logger.info("=" * 50)
        
        client = MoonshotClient()
        
        industry_prompt = f"""当前系统时间为 {current_month}（数据日期：{data_date}）。
请联网搜索短剧行业最新宏观数据：
1. 用户规模（APP月活、大盘用户数）
2. 市场规模（GMV、充值收入）
3. AI短剧占比
4. 平台分布

数据源建议：
- 新腕儿行业分析
- 艾媒咨询短剧行业报告
- 短剧工程行业观察
- 36氪/虎嗅短剧赛道报道

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
        logger.info(f"数据抓取完成：短剧工程 {len(duanju_data)} 条 + 红果 {len(hongguo_data)} 条 + 行业搜索 1 次")
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
