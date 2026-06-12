"""
数据抓取节点 - 直接爬取红果官网 + DataEye交叉验证 + Kimi搜索补充行业数据
优化版v1.8.2：多源数据交叉验证，提升数据可信度
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
from tools.dataeye_crawler import fetch_dataeye_rankings

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
    融合红果和DataEye数据，交叉验证提升可信度
    
    融合策略：
    1. 红果数据为主（覆盖更全）
    2. DataEye数据用于验证和补充热度
    3. 匹配规则：标题模糊匹配
    """
    if not dataeye_data:
        # 无DataEye数据，红果数据置信度0.7
        for drama in hongguo_data:
            drama["confidence_score"] = 0.7
            drama["data_source"] = "hongguo"
            drama["cross_validated"] = False
        return hongguo_data
    
    # 构建DataEye标题索引（用于快速查找）
    dataeye_index = {}
    for d in dataeye_data:
        title = d.get("title", "").strip()
        if title:
            dataeye_index[title] = d
    
    merged = []
    for hg_drama in hongguo_data:
        hg_title = hg_drama.get("title", "").strip()
        
        # 尝试匹配DataEye数据
        matched_de = None
        for de_title, de_data in dataeye_index.items():
            # 模糊匹配：标题包含或被包含
            if hg_title in de_title or de_title in hg_title:
                matched_de = de_data
                break
        
        if matched_de:
            # 交叉验证成功，提升置信度
            merged_drama = hg_drama.copy()
            merged_drama["confidence_score"] = 0.95
            merged_drama["data_source"] = "hongguo+dataeye"
            merged_drama["cross_validated"] = True
            merged_drama["dataeye_rank"] = matched_de.get("rank", 0)
            merged_drama["dataeye_heat"] = matched_de.get("heat", 0)
            # 合并热度值（取平均或加权）
            if matched_de.get("heat", 0) > 0:
                merged_drama["heat"] = (hg_drama.get("heat", 0) + matched_de.get("heat", 0)) // 2
            merged.append(merged_drama)
        else:
            # 未匹配到DataEye，保持红果数据
            merged_drama = hg_drama.copy()
            merged_drama["confidence_score"] = 0.7
            merged_drama["data_source"] = "hongguo"
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
        else:
            logger.warning("⚠️ 红果官网爬取失败，将依赖其他数据源")
        
        # ========== 第二步：爬取DataEye榜单（交叉验证）==========
        logger.info("=" * 50)
        logger.info("第二步：爬取DataEye榜单进行交叉验证")
        logger.info("=" * 50)
        
        dataeye_data = []
        try:
            dataeye_data = fetch_dataeye_rankings(top_n=30)
            if dataeye_data:
                logger.info(f"✅ DataEye爬取成功，获取 {len(dataeye_data)} 条数据")
            else:
                logger.warning("⚠️ DataEye爬取返回空数据")
        except Exception as e:
            logger.warning(f"⚠️ DataEye爬取失败: {e}")
        
        # ========== 第三步：数据融合与交叉验证 ==========
        logger.info("=" * 50)
        logger.info("第三步：数据融合与交叉验证")
        logger.info("=" * 50)
        
        if hongguo_data:
            merged_data = _merge_hongguo_dataeye(hongguo_data, dataeye_data)
            validated_count = sum(1 for d in merged_data if d.get("cross_validated"))
            logger.info(f"✅ 数据融合完成：{len(merged_data)} 条数据，{validated_count} 条交叉验证通过")
            
            # 添加到搜索结果
            search_results.append({
                "keyword": "红果+DataEye融合榜单",
                "title": f"短剧融合榜单 {data_date}",
                "url": "multi_source_merged",
                "snippet": f"红果直爬{len(hongguo_data)}条 + DataEye验证{len(dataeye_data)}条，交叉验证{validated_count}条",
                "summary": json.dumps(merged_data, ensure_ascii=False),
                "site_name": "多源融合",
                "publish_time": data_date,
                "raw_content": json.dumps(merged_data, ensure_ascii=False),
                "type": "merged_ranking",
                "data_count": len(merged_data),
                "validated_count": validated_count
            })
        elif dataeye_data:
            # 红果失败，使用DataEye数据
            logger.warning("⚠️ 红果数据为空，使用DataEye数据作为备选")
            for d in dataeye_data:
                d["confidence_score"] = 0.6
                d["data_source"] = "dataeye"
                d["cross_validated"] = False
            search_results.append({
                "keyword": "DataEye榜单（红果失败备选）",
                "title": f"DataEye短剧榜单 {data_date}",
                "url": "dataeye_fallback",
                "snippet": f"DataEye爬取 {len(dataeye_data)} 条数据",
                "summary": json.dumps(dataeye_data, ensure_ascii=False),
                "site_name": "DataEye",
                "publish_time": data_date,
                "raw_content": json.dumps(dataeye_data, ensure_ascii=False),
                "type": "dataeye_fallback",
                "data_count": len(dataeye_data)
            })
        
        # ========== 第四步：Kimi搜索行业宏观数据（仅1次调用）==========
        logger.info("=" * 50)
        logger.info("第四步：Kimi搜索补充行业数据（仅1次调用）")
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
