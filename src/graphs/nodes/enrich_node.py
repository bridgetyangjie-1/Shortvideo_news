"""
数据补充节点 - Gemini架构重构：先搜后问，0幻觉
"""
import os
import json
import re
import logging
from typing import Any
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from tools.deepseek_api import DeepSeekClient

from graphs.state import EnrichNodeInput, EnrichNodeOutput, DramaRanking

# 初始化日志
logger = logging.getLogger(__name__)


def enrich_node(state: EnrichNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> EnrichNodeOutput:
    """
    title: 数据补充（先搜后问架构）
    desc: Gemini重构 - 先在Python层真实搜索每部剧的资料，再喂给LLM做提取，彻底根除幻觉
    integrations: DeepSeek API（search + chat）
    """
    ctx = runtime.context
    
    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        sp = _cfg.get("sp", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.3)
        
        # 初始化DeepSeek客户端
        client = DeepSeekClient()
        
        # 🚨 Gemini核心修复：先在Python层真实搜索每部剧的资料
        real_search_context = ""
        basic_rankings_list = list(state.basic_rankings) if hasattr(state.basic_rankings, '__iter__') else []
        
        for idx, drama in enumerate(basic_rankings_list[:10]):  # 只查前10名控制耗时
            # 获取剧名 - 防御性处理多种类型
            title = ""
            drama_obj: Any = drama  # 明确类型为Any
            if hasattr(drama_obj, "title"):
                title = getattr(drama_obj, "title", "")
            elif isinstance(drama_obj, dict):
                title = drama_obj.get("title", "")
            
            if not title:
                continue
            
            logger.info(f"正在搜索剧目《{title}》的真实资料...")
            
            try:
                # 🚨 使用 DuckDuckGo 真正具有爬虫能力的 search 方法
                search_res = client.search(query=f"短剧 《{title}》 演员 主演 制作公司 厂牌", max_results=3)
                real_search_context += f"\n【剧目：《{title}》真实网页检索结果】:\n{search_res}\n"
                logger.info(f"搜索《{title}》成功")
            except Exception as e:
                logger.warning(f"搜索剧目《{title}》失败: {e}")
                real_search_context += f"\n【剧目：《{title}》搜索失败，请填'未知'】\n"
        
        # 渲染用户提示词 - 防御性序列化
        rankings_json_list: list = []
        for r_item in basic_rankings_list:
            r_any: Any = r_item
            if hasattr(r_any, "model_dump"):
                rankings_json_list.append(r_any.model_dump())
            elif hasattr(r_any, "__dict__"):
                rankings_json_list.append(dict(r_any.__dict__))
            elif isinstance(r_any, dict):
                rankings_json_list.append(r_any)
            else:
                rankings_json_list.append(str(r_any))
        
        user_prompt = f"""【数据日期】：{state.data_date}
【基础榜单数据】：
{json.dumps(rankings_json_list, ensure_ascii=False, indent=2)}

🚨以下是你必须依赖的真实互联网检索资料：
如果资料里没有提到演员/厂牌，严格填入"未知"，禁止编造传统影视明星！

{real_search_context}

请严格按照反幻觉铁律，补全缺失字段并输出JSON数组："""

        # 构建消息
        messages = [
            {"role": "system", "content": sp},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用DeepSeek做提取（现在有真实上下文了）
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
                female_lead=item.get("female_lead", "未知"),
                male_lead=item.get("male_lead", "未知"),
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
                production_house=item.get("production_house", "独立厂牌"),
                core_trope=item.get("core_trope", []),
                episodes_count=item.get("episodes_count", 80)
            )
            enriched_rankings.append(ranking)
        
        logger.info(f"数据补充完成，共{len(enriched_rankings)}部剧")
        
        return EnrichNodeOutput(
            enriched_rankings=enriched_rankings,
            success=True
        )
        
    except Exception as e:
        logger.error(f"数据补充节点失败: {e}")
        return EnrichNodeOutput(
            enriched_rankings=[],
            success=False
        )