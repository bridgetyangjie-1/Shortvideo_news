"""
数据处理节点 - 清洗和结构化数据
优先处理红果官网直接爬取的数据，无数据时使用Kimi搜索结果
"""
import os
import json
import re
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
        return str(exc) == "API 调用次数过多，已熔断"

from jinja2 import Template
from graphs.ranking_quality import RankingCountError, ensure_top_rankings
from graphs.state import ProcessNodeInput, ProcessNodeOutput


# 初始化日志
logger = logging.getLogger(__name__)


def _parse_hongguo_direct_data(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    从搜索结果中提取红果直接爬取的数据
    
    Returns:
        榜单数据列表，如果不存在则返回空列表
    """
    for item in search_results:
        if item.get("type") == "hongguo_direct":
            raw_content = item.get("raw_content", "")
            if raw_content:
                try:
                    data = json.loads(raw_content)
                    if isinstance(data, list):
                        logger.info(f"✅ 从红果直接爬取数据中提取 {len(data)} 条榜单")
                        return data
                except json.JSONDecodeError as e:
                    logger.warning(f"解析红果数据失败: {e}")
    return []


def _convert_hongguo_to_rankings(hongguo_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将红果直接爬取的数据转换为标准榜单格式
    
    Args:
        hongguo_data: 红果官网直接爬取的数据
        
    Returns:
        标准格式的榜单数据
    """
    rankings = []
    
    for item in hongguo_data:
        ranking = {
            "rank": item.get("rank", 0),
            "title": item.get("title", ""),
            "views": "热度上榜",  # 红果官网没有播放量，用占位符
            "views_num": 0,
            "platform": item.get("platform", "红果"),
            "genre": "",
            "tags": item.get("tags", []),
            "trend": "",
            "trend_tag": "",
            "trend_type": "same",
            "category": "female",  # 默认女频
            "is_ai": False,
            "desc": "",
            "change": "",
            "heat": 100 - item.get("rank", 0),  # 简单热度计算
            "female_lead": item.get("female_lead", ""),
            "male_lead": item.get("male_lead", ""),
            "production_house": item.get("studio", ""),
            "core_trope": [],
            "episodes_count": _parse_episodes(item.get("episodes", "")),
        }
        rankings.append(ranking)
    
    return rankings


def _parse_episodes(episodes_str: str) -> int:
    """解析集数字符串，如'全92集' -> 92"""
    if not episodes_str:
        return 80
    match = re.search(r'(\d+)', episodes_str)
    if match:
        return int(match.group(1))
    return 80


def process_node(
    state: ProcessNodeInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> ProcessNodeOutput:
    """
    title: 🧹 数据清洗与结构化
    desc: 优先处理红果官网直接爬取数据，无数据时使用Kimi搜索
    integrations: Moonshot API, 红果官网爬虫
    """
    ctx = runtime.context
    
    # 处理默认日期
    data_date = state.data_date
    if not data_date:
        data_date = datetime.now().strftime("%Y-%m-%d")
    
    # 生成时间戳
    generated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    
    try:
        if not state.search_results:
            error_message = "process_node: search_results 为空，无法抽取榜单；请先检查 search_node。"
            logger.error(error_message)
            return ProcessNodeOutput(
                basic_rankings=[],
                quality_score=0.0,
                success=False,
                error_message=error_message + "\n"
            )

        # ========== 优先处理红果直接爬取的数据 ==========
        hongguo_data = _parse_hongguo_direct_data(state.search_results)
        
        if hongguo_data:
            logger.info("=" * 50)
            logger.info("使用红果官网直接爬取的数据")
            logger.info("=" * 50)
            
            # 转换为标准榜单格式
            rankings = _convert_hongguo_to_rankings(hongguo_data)
            
            if rankings:
                logger.info(f"✅ 成功转换 {len(rankings)} 条榜单数据")
                
                # 数据质量检查
                count_warning = ""
                try:
                    rankings, count_warning = ensure_top_rankings(
                        rankings,
                        data_date=data_date,
                        workspace_path=os.getenv("COZE_WORKSPACE_PATH", "."),
                    )
                except RankingCountError as count_error:
                    error_message = f"process_node: {count_error}"
                    logger.error(error_message)
                    return ProcessNodeOutput(
                        basic_rankings=[],
                        quality_score=0.0,
                        success=False,
                        error_message=error_message + "\n"
                    )
                
                if count_warning:
                    logger.warning("process_node: %s", count_warning)
                
                # 计算数据质量分数
                quality_score = 85.0  # 红果直接爬取的数据质量较高
                
                return ProcessNodeOutput(
                    basic_rankings=rankings,
                    quality_score=quality_score,
                    success=True,
                    error_message=(count_warning + "\n") if count_warning else ""
                )

        # ========== 红果数据不存在，使用Kimi搜索结果 ==========
        logger.info("=" * 50)
        logger.info("红果数据不存在，使用Kimi搜索结果")
        logger.info("=" * 50)
        
        # 读取LLM配置
        cfg_file = os.path.join(
            os.getenv("COZE_WORKSPACE_PATH", "."), 
            config["metadata"]["llm_cfg"]
        )
        with open(cfg_file, 'r', encoding='utf-8') as fd:
            _cfg = json.load(fd)
        
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.3)
        
        # 准备搜索结果文本
        search_text = ""
        for idx, item in enumerate(state.search_results, 1):
            # 跳过红果数据（已处理）
            if item.get("type") == "hongguo_direct":
                continue
            search_text += f"\n【来源 {idx}】\n"
            search_text += f"关键词: {item.get('keyword', '')}\n"
            search_text += f"标题: {item.get('title', '')}\n"
            search_text += f"来源网站: {item.get('site_name', '')}\n"
            search_text += f"摘要: {item.get('summary', '') or item.get('snippet', '')}\n"
            search_text += f"发布时间: {item.get('publish_time', '')}\n"
        
        # 渲染用户提示词
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "data_date": data_date,
            "search_results": search_text
        })
        
        # 初始化 Kimi 客户端
        client = MoonshotClient()
        
        # 构建消息
        messages = [
            {"role": "system", "content": sp},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 Kimi 并用统一解析器提取 JSON
        result_data = client.structured_output(
            messages=messages,
            temperature=temperature,
            max_tokens=4096
        )

        rankings: List[Dict[str, Any]] = []
        quality_score = 0.0

        if isinstance(result_data, list):
            rankings = [item for item in result_data if isinstance(item, dict)]
        elif isinstance(result_data, dict):
            raw_rankings = result_data.get("rankings") or result_data.get("top20") or result_data.get("top10") or result_data.get("data") or []
            if isinstance(raw_rankings, list):
                rankings = [item for item in raw_rankings if isinstance(item, dict)]
            quality_score = float(result_data.get("quality_score", 0) or 0)
        else:
            raise ValueError(f"process_node 解析结果类型错误: {type(result_data)}")
        
        # 检查数据质量
        if not rankings:
            error_message = "process_node: Kimi JSON 已解析但未提取到 rankings/top10 榜单数据；请检查 search_node 返回内容。"
            logger.error(error_message)
            return ProcessNodeOutput(
                basic_rankings=[],
                quality_score=0.0,
                success=False,
                error_message=error_message + "\n"
            )
        
        count_warning = ""

        try:
            rankings, count_warning = ensure_top_rankings(
                rankings,
                data_date=data_date,
                workspace_path=os.getenv("COZE_WORKSPACE_PATH", "."),
            )
        except RankingCountError as count_error:
            error_message = f"process_node: {count_error}"
            logger.error(error_message)
            return ProcessNodeOutput(
                basic_rankings=[],
                quality_score=0.0,
                success=False,
                error_message=error_message + "\n"
            )

        if count_warning:
            logger.warning("process_node: %s", count_warning)

        # 计算数据质量分数
        if quality_score == 0:
            required_fields = ["rank", "title", "views"]
            valid_count = 0
            for item in rankings:
                if all(item.get(field) for field in required_fields):
                    valid_count += 1
            quality_score = (valid_count / len(rankings)) * 100 if rankings else 0
        
        return ProcessNodeOutput(
            basic_rankings=rankings,
            quality_score=quality_score,
            success=True,
            error_message=(count_warning + "\n") if count_warning else ""
        )
        
    except Exception as e:
        if is_api_budget_error(e):
            raise
        error_message = f"process_node: 数据清洗或 JSON 解析失败: {e}"
        logger.error(error_message, exc_info=True)
        return ProcessNodeOutput(
            data_date=data_date,
            basic_rankings=[],
            quality_score=0.0,
            success=False,
            error_message=error_message + "\n"
        )
