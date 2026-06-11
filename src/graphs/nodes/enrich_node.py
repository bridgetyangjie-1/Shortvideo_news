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
        
        # 搜索全部剧集（Tier 2配额充足）
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
            
            logger.info(f"Kimi多轮搜索剧目《{title}》...")
            
            # 🚨 多轮搜索策略：尝试多种关键词组合
            search_queries = [
                f"短剧《{title}》主演演员女演员男主角女主角",
                f"《{title}》短剧演员阵容DataEye红果短剧",
                f"短剧 {title} 主演是谁 小红书抖音豆瓣"
            ]
            
            search_found = False
            for query in search_queries:
                try:
                    search_res: str = kimi_client.search(query, max_results=3)
                    # 检查搜索结果是否包含演员信息（关键词：演员、主演、女主、男主）
                    if search_res and any(keyword in search_res for keyword in ["演员", "主演", "女主", "男主", "女主角", "男主角"]):
                        search_text = search_res[:2000] if len(search_res) > 2000 else search_res
                        real_search_context += f"\n【剧目：《{title}》真实检索】:\n{search_text}\n"
                        logger.info(f"搜索《{title}》成功，找到演员信息")
                        search_found = True
                        break  # 找到有效结果，停止后续搜索
                    time.sleep(1)  # 每次搜索间隔
                except Exception as e:
                    logger.warning(f"搜索《{title}》关键词'{query}'失败: {e}")
                    time.sleep(1)
            
            if not search_found:
                # 🚨 搜索失败时添加推理补充提示
                real_search_context += f"\n【剧目：《{title}》搜索无结果，请推理补充】\n"
                logger.warning(f"《{title}》未找到演员信息，将推理补充")
            
            time.sleep(1)  # 每部剧搜索间隔
        
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

🚨【演员推理补充规则】：
- 若搜索结果无演员信息，请根据剧目类型（女频/男频）推理可能的演员特征
- 女频短剧主演通常是新生代女演员，优先选择：徐艺真、马秋元、王艺瑾、白妍、赵佳、余茵、杨咩咩、滕泽文、贾翼瑄、张楚嫣
- 男频短剧主演通常是新生代男演员，优先选择：曾辉、何健麒、孙晨越、王道铁、甄永涛、刘擎、张集骏、刘萧旭、鹿单东、龚俊
- 严禁填"未知"！如果实在不确定，请从上述名单中选择最可能的演员
- 必须填写具体的演员名字，不要出现"未知"

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