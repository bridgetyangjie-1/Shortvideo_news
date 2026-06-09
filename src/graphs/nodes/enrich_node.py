"""
数据补充节点 - 补充演员信息、tags、desc、trend等字段
"""
import os
import json
import re
import logging
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from utils.runtime import Context
from tools.deepseek_api import DeepSeekClient

from graphs.state import EnrichNodeInput, EnrichNodeOutput, DramaRanking

# 初始化日志
logger = logging.getLogger(__name__)


def enrich_node(state: EnrichNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> EnrichNodeOutput:
    """
    title: 数据补充
    desc: 使用DeepSeek补充每部剧的演员信息、tags标签、desc剧情描述等字段
    integrations: DeepSeek API
    """
    ctx = runtime.context
    
    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.3)
        
        # 渲染用户提示词
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "basic_rankings": json.dumps(state.basic_rankings, ensure_ascii=False, indent=2),
            "data_date": state.data_date
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
            max_tokens=8000
        )
        
        # 提取JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response
        
        rankings_data = json.loads(json_str)
        
        # 转换为DramaRanking对象列表
        enriched_rankings = []
        for item in rankings_data:
            ranking = DramaRanking(
                rank=item.get("rank", 0),
                title=item.get("title", ""),
                female_lead=item.get("female_lead", ""),
                male_lead=item.get("male_lead", ""),
                views=item.get("views", ""),
                views_num=item.get("views_num", 0),
                platform=item.get("platform", "红果"),
                genre=item.get("genre", ""),
                tags=item.get("tags", []),
                trend=item.get("trend", ""),
                trend_type=item.get("trend_type", "same"),
                category=item.get("category", "female"),
                is_ai=item.get("is_ai", False),
                desc=item.get("desc", ""),
                # 🚨 新增商业信息字段
                production_house=item.get("production_house", "未知厂牌"),
                core_trope=item.get("core_trope", []),
                episodes_count=item.get("episodes_count", 80)
            )
            enriched_rankings.append(ranking)
        
        return EnrichNodeOutput(
            enriched_rankings=enriched_rankings,
            success=True
        )
        
    except Exception as e:
        logger.error(f"数据补充失败: {str(e)}")
        return EnrichNodeOutput(
            enriched_rankings=[],
            success=False
        )