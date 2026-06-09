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
from utils.runtime import Context
from tools.deepseek_api import DeepSeekClient
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
    desc: 使用DeepSeek清洗和结构化搜索结果，提取榜单数据
    integrations: DeepSeek API
    """
    ctx = runtime.context
    
    # 处理默认日期
    data_date = state.data_date
    if not data_date:
        data_date = datetime.now().strftime("%Y-%m-%d")
    
    # 生成时间戳
    generated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    
    try:
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
        
        # 初始化DeepSeek客户端
        client = DeepSeekClient()
        
        # 构建消息
        messages = [
            {"role": "system", "content": sp},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用DeepSeek
        response = client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=4096
        )
        
        # 解析JSON结果
        rankings: List[Dict[str, Any]] = []
        quality_score = 0.0
        
        # 尝试提取JSON块
        json_pattern = r'```json\s*([\s\S]*?)\s*```'
        json_matches = re.findall(json_pattern, response)
        
        if json_matches:
            try:
                result_data = json.loads(json_matches[0])
                if isinstance(result_data, list):
                    rankings = result_data
                else:
                    rankings = result_data.get("rankings", [])
                    quality_score = float(result_data.get("quality_score", 0))
            except json.JSONDecodeError:
                try:
                    result_data = json.loads(response)
                    if isinstance(result_data, list):
                        rankings = result_data
                    else:
                        rankings = result_data.get("rankings", [])
                        quality_score = float(result_data.get("quality_score", 0))
                except:
                    pass
        else:
            try:
                result_data = json.loads(response)
                if isinstance(result_data, list):
                    rankings = result_data
                else:
                    rankings = result_data.get("rankings", [])
                    quality_score = float(result_data.get("quality_score", 0))
            except:
                pass
        
        # 检查数据质量
        if not rankings:
            return ProcessNodeOutput(
                basic_rankings=[],
                quality_score=0.0,
                success=False
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
        logger.error(f"数据清洗失败: {e}")
        return ProcessNodeOutput(
            data_date=data_date,
            basic_rankings=[],
            quality_score=0.0,
            success=False
        )