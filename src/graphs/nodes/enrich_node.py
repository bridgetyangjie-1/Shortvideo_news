"""
数据补充节点 - 双模型协同解耦架构
Kimi负责搜索，DeepSeek负责推理
"""
import os
import json
import re
import logging
import time
from typing import Any, List, Dict
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from tools.moonshot_api import MoonshotClient
from tools.deepseek_api import DeepSeekClient

from graphs.state import EnrichNodeInput, EnrichNodeOutput, DramaRanking

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def enrich_node(state: EnrichNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> EnrichNodeOutput:
    """
    title: 数据补充（双模型协同）
    desc: Kimi搜索每部剧资料 → DeepSeek推理生成完整JSON
    integrations: Moonshot API + DeepSeek API
    """
    ctx = runtime.context
    
    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        with open(cfg_file, "r", encoding="utf-8") as fd:
            _cfg = json.load(fd)
        
        sp = _cfg.get("sp", "")
        temperature = _cfg.get("config", {}).get("temperature", 0.3)
        
        # 初始化双客户端
        kimi_client = MoonshotClient()
        ds_client = DeepSeekClient()
        
        # ========== 搜集阶段：Kimi搜索每部剧 ==========
        real_search_context = ""
        search_errors: List[str] = []
        basic_rankings_list = list(state.basic_rankings) if hasattr(state.basic_rankings, '__iter__') else []
        
        if not basic_rankings_list:
            error_message = "enrich_node: 输入 basic_rankings 为空"
            logger.error(error_message)
            return EnrichNodeOutput(
                enriched_rankings=[],
                success=False,
                error_message=error_message + "\n"
            )
        
        # 搜索全部剧集（Tier 7配额充足）
        for idx, drama in enumerate(basic_rankings_list):
            # 获取剧名
            title = ""
            drama_obj: Any = drama
            if hasattr(drama_obj, "title"):
                title = getattr(drama_obj, "title", "")
            elif isinstance(drama_obj, dict):
                title = drama_obj.get("title", "")
            
            if not title:
                continue
            
            logger.info(f"Kimi搜索剧目《{title}》...")
            
            try:
                search_res: str = kimi_client.search(
                    query=f"短剧 《{title}》 演员 主演 制作公司 厂牌",
                    max_results=3
                )
                search_text = search_res[:2000] if len(search_res) > 2000 else search_res
                real_search_context += f"\n【剧目：《{title}》真实检索】:\n{search_text}\n"
                logger.info(f"搜索《{title}》成功")
                time.sleep(1)  # 🚨 节流阀（Tier 7配额充足，缩短间隔）
            except Exception as e:
                search_error = f"enrich_node: 搜索《{title}》失败: {e}"
                logger.warning(search_error)
                search_errors.append(search_error)
                real_search_context += f"\n【剧目：《{title}》搜索失败，填'未知'】\n"
        
        # ========== 推理阶段：DeepSeek生成JSON ==========
        rankings_json_list: List[Dict] = []
        for r_item in basic_rankings_list:
            r_any: Any = r_item
            if hasattr(r_any, "model_dump"):
                rankings_json_list.append(r_any.model_dump())
            elif isinstance(r_any, dict):
                rankings_json_list.append(r_any)
        
        user_prompt = f"""【数据日期】：{state.data_date}
【基础榜单数据】：
{json.dumps(rankings_json_list, ensure_ascii=False, indent=2)}

🚨 真实互联网检索资料（从中提取，无提及则填'未知'）：
{real_search_context}

请补全缺失字段并输出JSON数组，不要加```json包裹："""
        
        response = ds_client.chat(
            messages=[
                {"role": "system", "content": sp or "你是数据提取专家。必须输出纯JSON数组，禁止编造传统影视明星。"},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=8000
        )
        
        logger.info(f"DeepSeek响应: {response[:500]}...")
        
        # ========== 健壮性解析 ==========
        rankings_data: List[Dict] = []
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
                parsed = json.loads(json_str)
                
                if isinstance(parsed, list):
                    rankings_data = parsed
                elif isinstance(parsed, dict):
                    rankings_data = parsed.get("rankings") or parsed.get("data") or []
            else:
                raise ValueError("未找到有效JSON数组")
                
        except Exception as parse_error:
            logger.error(f"enrich_node: JSON解析失败: {parse_error}")
            logger.error(f"原始响应: {response}")
            search_errors.append(f"JSON解析失败: {parse_error}")
        
        # 转换为DramaRanking对象
        enriched_rankings: List[DramaRanking] = []
        for item in rankings_data:
            if not isinstance(item, dict):
                continue
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
            success=True,
            error_message=("\n".join(search_errors) + "\n") if search_errors else ""
        )
        
    except Exception as e:
        error_message = f"enrich_node: 数据补充失败: {e}"
        logger.error(error_message, exc_info=True)
        return EnrichNodeOutput(
            enriched_rankings=[],
            success=False,
            error_message=error_message + "\n"
        )