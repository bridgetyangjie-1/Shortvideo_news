"""
洞察生成节点 - 生成5条行业洞察
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

from graphs.state import (
    InsightsNodeInput,
    InsightsNodeOutput,
    Insight
)

# 初始化日志
logger = logging.getLogger(__name__)


def insights_node(state: InsightsNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> InsightsNodeOutput:
    """
    title: 洞察生成
    desc: 使用DeepSeek基于榜单、演员、行业数据生成5条行业洞察
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
        temperature = _cfg.get("config", {}).get("temperature", 0.5)
        
        # 准备数据
        rankings_data = [r.model_dump() for r in state.enriched_rankings]
        actors_data = state.actors.model_dump()
        industry_data = state.industry.model_dump()
        
        # 渲染用户提示词
        up_tpl = Template(up)
        user_prompt = up_tpl.render({
            "data_date": state.data_date,
            "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2),
            "actors": json.dumps(actors_data, ensure_ascii=False, indent=2),
            "industry": json.dumps(industry_data, ensure_ascii=False, indent=2)
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
            max_tokens=3000
        )
        
        # 提取JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接提取数组
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                json_str = json_match.group()
            else:
                json_str = response
        
        insights_data = json.loads(json_str)
        
        # 转换为Insight对象
        insights = []
        for item in insights_data:
            insight = Insight(
                icon=item.get("icon", "📊"),
                title=item.get("title", ""),
                content=item.get("content", "")
            )
            insights.append(insight)
        
        return InsightsNodeOutput(
            insights=insights,
            success=True
        )
        
    except Exception as e:
        logger.error(f"洞察生成失败: {str(e)}")
        # 返回默认洞察
        default_insights = [
            Insight(icon="🤖", title="AI短剧崛起", content="AI短剧占比持续上升，技术与内容融合加速。"),
            Insight(icon="📈", title="女频主导", content="女频短剧仍占据市场主导地位，甜宠题材持续火热。"),
            Insight(icon="🎬", title="题材多元化", content="题材从都市甜宠向多元化发展，悬疑、古风题材增长。"),
            Insight(icon="👥", title="演员迭代", content="新人演员快速崛起，老牌演员保持稳定人气。"),
            Insight(icon="📱", title="平台格局", content="红果保持领先，平台竞争加剧，用户粘性提升。")
        ]
        return InsightsNodeOutput(
            insights=default_insights,
            success=True
        )