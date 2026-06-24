"""
洞察生成节点 - 双模型协同解耦架构
Kimi负责搜索，DeepSeek负责推理

更新策略：洞察为周更数据。每周一调用 Kimi + DeepSeek 生成并写入缓存，
周二至周日直接读取上周一的缓存，避免每日重复调用 API。
"""
import os
import json
import re
import logging
import time
from typing import List, Dict, Any
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from tools.moonshot_api import MoonshotClient
from tools.deepseek_api import DeepSeekClient
from tools import weekly_cache

from graphs.state import (
    InsightsNodeInput,
    InsightsNodeOutput,
    Insight
)

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _generate_insights(
    state: InsightsNodeInput,
    config: RunnableConfig,
) -> tuple[List[Insight], str]:
    """实际调用 API 生成洞察，返回 (insights, error_message)。"""
    input_error_message = ""

    # 读取配置文件
    cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
    with open(cfg_file, "r", encoding="utf-8") as fd:
        _cfg = json.load(fd)

    sp = _cfg.get("sp", "")
    up = _cfg.get("up", "")
    temperature = _cfg.get("config", {}).get("temperature", 0.3)

    # 准备榜单数据
    rankings_data: List[Dict[str, Any]] = []
    enriched_rankings_list = list(state.enriched_rankings) if hasattr(state.enriched_rankings, '__iter__') else []

    if not enriched_rankings_list:
        input_error_message = "insights_node: enriched_rankings 为空\n"
        logger.error(input_error_message.strip())

    for r in enriched_rankings_list:
        if hasattr(r, 'model_dump'):
            rankings_data.append(r.model_dump())
        elif isinstance(r, dict):
            rankings_data.append(r)

    # 准备行业数据
    industry_data: Dict[str, Any] = {}
    if hasattr(state.industry, 'model_dump'):
        industry_data = state.industry.model_dump()
    elif isinstance(state.industry, dict):
        industry_data = state.industry

    # 初始化双客户端
    kimi_client = MoonshotClient()
    ds_client = DeepSeekClient()

    # ========== 搜集阶段：Kimi搜索 ==========
    search_query = f"短剧行业 最新爆款 融资 政策 动态 {state.data_date}"
    search_response = kimi_client.search(query=search_query, max_results=5)
    logger.info(f"Kimi搜索成功: {search_response[:300]}...")
    time.sleep(1)  # 🚨 节流阀（Tier 7配额充足）

    # ========== 推理阶段：DeepSeek生成JSON ==========
    up_tpl = Template(up)
    user_prompt = up_tpl.render({
        "data_date": state.data_date,
        "rankings": json.dumps(rankings_data, ensure_ascii=False, indent=2),
        "industry": json.dumps(industry_data, ensure_ascii=False, indent=2),
        "search_results": search_response
    })

    full_prompt = f"""{user_prompt}

🚨【时间铁律 - 最高优先级】
⚠️ 只分析【本周：{state.data_date} 所在周】的行业大事件！
⚠️ 搜索结果中的往年数据一律丢弃，不作为本周洞察来源！
⚠️ 如果没有本周大事件，基于当周榜单数据进行分析。

🚨 必须输出合法JSON数组格式，不要加```json包裹：
[
  {{
    "icon": "🔥|💰|📊",
    "title": "洞察标题",
    "content": "具体分析内容（爆款归因/买量建议）",
    "source": "数据来源"
  }}
]
"""

    response = ds_client.chat(
        messages=[
            {"role": "system", "content": sp or "你是短剧行业分析师。必须输出纯JSON数组，爆款归因+买量建议。"},
            {"role": "user", "content": full_prompt}
        ],
        temperature=temperature,
        max_tokens=3000
    )

    logger.info(f"DeepSeek响应: {response[:500]}...")

    # ========== 健壮性解析 ==========
    insights: List[Insight] = []
    try:
        # 去除Markdown标记
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
            insights_data = json.loads(json_str)

            for item in insights_data:
                if isinstance(item, dict):
                    insight = Insight(
                        icon=item.get("icon", "📊"),
                        title=item.get("title", ""),
                        content=item.get("content", ""),
                        source=item.get("source", ""),
                        data_source="Kimi 搜索 + DeepSeek 提炼",
                        update_frequency="weekly",
                    )
                    insights.append(insight)
        else:
            raise ValueError("未找到有效JSON数组")

    except Exception as parse_error:
        logger.error(f"insights_node: JSON解析失败: {parse_error}")
        logger.error(f"原始响应: {response}")

    # 确保至少有2条洞察
    if len(insights) < 2:
        if rankings_data:
            top_drama = rankings_data[0] if rankings_data else {}
            insights.append(Insight(
                icon="🔥",
                title=f"爆款归因：{top_drama.get('title', 'TOP1')}",
                content=f"受众定位25-35岁女性，爽点公式：{', '.join(top_drama.get('core_trope', ['逆袭', '甜宠']))}",
                source="榜单推演",
                data_source="当周榜单规则推演",
                update_frequency="weekly",
            ))
            insights.append(Insight(
                icon="💰",
                title="买量建议",
                content=f"建议关注{top_drama.get('genre', '甜宠')}题材投流机会",
                source="数据分析",
                data_source="当周榜单规则推演",
                update_frequency="weekly",
            ))

    return insights, input_error_message


def insights_node(state: InsightsNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> InsightsNodeOutput:
    """
    title: 行业大事件（双模型协同）
    desc: Kimi搜索行业事件 → DeepSeek推理生成洞察JSON；周更刷新，非周一读缓存
    integrations: Moonshot API + DeepSeek API
    """
    ctx = runtime.context

    # 非周一且命中缓存：直接返回缓存，不调用 API
    if not weekly_cache.is_refresh_day(state.data_date):
        cached = weekly_cache.load_cache("insights", state.data_date)
        if cached:
            insights = [Insight(**item) for item in cached.get("insights", [])]
            logger.info("insights_node: 命中周缓存，返回 %s 条洞察", len(insights))
            return InsightsNodeOutput(
                insights=insights,
                success=True,
                error_message="",
            )
        logger.info("insights_node: 非周一且缓存缺失，将重新生成并缓存")

    try:
        insights, input_error_message = _generate_insights(state, config)

        # 保存周缓存（生成后都缓存，供本周后续日期使用）
        try:
            weekly_cache.save_cache(
                "insights",
                {"insights": [i.model_dump() for i in insights]},
                state.data_date,
            )
        except Exception as cache_err:
            logger.warning("insights_node: 缓存保存失败: %s", cache_err)

        logger.info(f"洞察生成完成，共{len(insights)}条")

        return InsightsNodeOutput(
            insights=insights,
            success=True,
            error_message=input_error_message
        )

    except Exception as e:
        error_message = f"insights_node: 洞察生成失败: {e}"
        logger.error(error_message, exc_info=True)
        return InsightsNodeOutput(
            insights=[
                Insight(
                    icon="📊",
                    title="数据待补充",
                    content="请稍后再试",
                    source="",
                    data_source="洞察生成失败",
                    update_frequency="weekly",
                )
            ],
            success=False,
            error_message=error_message + "\n"
        )
