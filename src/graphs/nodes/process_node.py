"""
数据处理节点 - 清洗和结构化数据
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
        return str(exc) == "API \u8c03\u7528\u6b21\u6570\u8fc7\u591a\uff0c\u5df2\u718f\u65ad"
from jinja2 import Template
from graphs.state import ProcessNodeInput, ProcessNodeOutput


# 初始化日志
logger = logging.getLogger(__name__)


def process_node(
    state: ProcessNodeInput, 
    config: RunnableConfig, 
    runtime: Runtime[Context]
) -> ProcessNodeOutput:
    """
    title: 🧹 数据清洗与结构化
    desc: 使用 Kimi 清洗和结构化搜索结果，提取榜单数据
    integrations: Moonshot API
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
        
        # 调用 Kimi 并用统一解析器提取 JSON，解析失败会打印 raw_text
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
            raw_rankings = result_data.get("rankings") or result_data.get("top10") or result_data.get("data") or []
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
            success=True
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