"""
数据补充节点 - 优化版：本地缓存 + 爬虫优先 + 多源融合
Kimi调用：从N次（每部剧多次）降到最多1次（批量补充）
"""
import os
import json
import re
import logging
import time
import urllib.request
from typing import Any, List, Dict, Optional
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from tools.moonshot_api import MoonshotClient
from tools.deepseek_api import DeepSeekClient
from tools.cache_db import get_drama, save_drama
from tools.tag_normalizer import normalize_tags, classify_category

from graphs.ranking_quality import RankingCountError, ensure_top_rankings
from graphs.state import EnrichNodeInput, EnrichNodeOutput, DramaRanking, default_emotional_analysis

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_hongguo_detail(series_id: str) -> Optional[Dict]:
    """
    尝试从红果详情页获取演员/工作室信息
    返回: {"actors": [...], "studio": "...", "release_date": "..."} 或 None
    """
    if not series_id:
        return None
    
    try:
        url = f"https://novelquickapp.com/series/{series_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
        
        # 提取 window._ROUTER_DATA
        start = html.find('window._ROUTER_DATA = ')
        end = html.find('</script>', start)
        if start < 0 or end < 0:
            return None
        
        json_str = html[start+len('window._ROUTER_DATA = '):end].strip().rstrip(';')
        data = json.loads(json_str)
        
        # 尝试查找详情数据
        page_data = data.get('loaderData', {}).get('page', {})
        
        # 查找可能的详情字段
        detail_data = None
        for key in ['detail', 'seriesDetail', 'dramaDetail']:
            if key in page_data:
                detail_data = page_data[key]
                break
        
        if not detail_data:
            return None
        
        result: Dict[str, Any] = {
            "actors": [],
            "studio": "",
            "release_date": ""
        }
        
        # 提取演员信息
        if 'actors' in detail_data:
            result["actors"] = detail_data['actors']
        elif 'performer' in detail_data:
            result["actors"] = detail_data['performer']
        elif 'cast' in detail_data:
            result["actors"] = detail_data['cast']
        
        # 提取工作室信息
        for studio_key in ['studio', 'production', 'company', 'production_company']:
            if studio_key in detail_data and detail_data[studio_key]:
                result["studio"] = detail_data[studio_key]
                break
        
        # 提取上线时间
        for date_key in ['release_date', 'online_time', 'publish_date', 'create_time']:
            if date_key in detail_data and detail_data[date_key]:
                result["release_date"] = str(detail_data[date_key])
                break
        
        # 如果至少有一个有效字段，返回结果
        if result["actors"] or result["studio"]:
            logger.info(f"红果详情页爬取成功: series_id={series_id}")
            return result
        
        return None
        
    except Exception as e:
        logger.warning(f"爬取红果详情页失败: {e}")
        return None


def enrich_node(state: EnrichNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> EnrichNodeOutput:
    """
    title: 数据补充（爬虫优先）
    desc: 红果详情页爬虫 → Kimi批量补充（最多1次） → DeepSeek推理生成JSON
    integrations: 红果爬虫 + Moonshot API + DeepSeek API
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
        
        # ========== 第一步：本地缓存查询 + 红果详情页爬虫 ==========
        basic_rankings_list = list(state.basic_rankings) if hasattr(state.basic_rankings, '__iter__') else []
        
        if not basic_rankings_list:
            error_message = "enrich_node: 输入 basic_rankings 为空"
            logger.error(error_message)
            return EnrichNodeOutput(
                enriched_rankings=[],
                success=False,
                error_message=error_message + "\n"
            )
        
        real_search_context = ""
        missing_dramas: List[Dict] = []  # 爬虫失败的剧目
        cache_hits = 0  # 缓存命中计数
        
        for idx, drama in enumerate(basic_rankings_list[:20]):  # 只处理前20条
            # 获取剧名和series_id
            title = ""
            series_id = ""
            tags: List[str] = []
            drama_obj: Any = drama
            if hasattr(drama_obj, "title"):
                title = getattr(drama_obj, "title", "")
                series_id = getattr(drama_obj, "series_id", "")
                tags = getattr(drama_obj, "tags", []) or []
            elif isinstance(drama_obj, dict):
                title = drama_obj.get("title", "")
                series_id = drama_obj.get("series_id", "")
                tags = drama_obj.get("tags", []) or []
            
            if not title:
                continue
            
            # 🔑 优先查询本地缓存（7天内有效）
            if series_id:
                cached = get_drama(series_id)
                if cached:
                    cache_hits += 1
                    actors_str = ", ".join(cached.get("actors", {}).values()) if cached.get("actors") else "未知"
                    studio_str = cached.get("studio", "未知")
                    release_str = cached.get("release_date", "")
                    
                    real_search_context += f"\n【剧目：《{title}》本地缓存数据】:\n"
                    real_search_context += f"演员: {actors_str}\n"
                    real_search_context += f"工作室: {studio_str}\n"
                    if release_str:
                        real_search_context += f"上线时间: {release_str}\n"
                    
                    logger.info(f"《{title}》缓存命中")
                    continue
            
            # 尝试爬取红果详情页
            if series_id:
                detail = fetch_hongguo_detail(series_id)
                if detail:
                    # 爬取成功，保存到缓存
                    actors_dict: Dict[str, str] = {}
                    if detail.get("actors"):
                        actors_list = detail["actors"]
                        if isinstance(actors_list, list) and len(actors_list) >= 1:
                            actors_dict["female_lead"] = actors_list[0] if len(actors_list) > 0 else ""
                            actors_dict["male_lead"] = actors_list[1] if len(actors_list) > 1 else ""
                    
                    save_drama(
                        series_id=series_id,
                        title=title,
                        actors=actors_dict,
                        studio=detail.get("studio", ""),
                        release_date=detail.get("release_date", ""),
                        tags=tags,
                        data_source="hongguo"
                    )
                    
                    # 记录搜索上下文
                    actors_str = ", ".join(detail.get("actors", [])) if detail.get("actors") else "未知"
                    studio_str = detail.get("studio", "未知")
                    release_str = detail.get("release_date", "")
                    
                    real_search_context += f"\n【剧目：《{title}》红果详情页数据】:\n"
                    real_search_context += f"演员: {actors_str}\n"
                    real_search_context += f"工作室: {studio_str}\n"
                    if release_str:
                        real_search_context += f"上线时间: {release_str}\n"
                    
                    logger.info(f"《{title}》爬取成功并缓存")
                    time.sleep(0.5)  # 爬虫间隔
                    continue
            
            # 爬取失败，加入待补充列表
            missing_dramas.append({"title": title, "rank": idx + 1})
            real_search_context += f"\n【剧目：《{title}》需要补充演员信息】\n"
        
        logger.info(f"缓存命中: {cache_hits}部，爬虫补充: {20-cache_hits-len(missing_dramas)}部，待Kimi补充: {len(missing_dramas)}部")
        
        # ========== 第二步：Kimi批量补充（最多1次调用）==========
        if missing_dramas:
            logger.info(f"开始Kimi批量补充 {len(missing_dramas)} 部剧...")
            
            # 构建批量查询
            batch_titles = [f"《{d['title']}》" for d in missing_dramas[:10]]  # 最多补充10部
            batch_query = f"短剧演员信息查询，请告诉我以下短剧的主演（女主男主）和制作公司：{', '.join(batch_titles)}"
            
            try:
                batch_result = kimi_client.search(batch_query, max_results=5)
                if batch_result:
                    real_search_context += f"\n【Kimi批量搜索结果】:\n{batch_result[:3000]}\n"
                    logger.info("Kimi批量搜索成功")
            except Exception as e:
                logger.warning(f"Kimi批量搜索失败: {e}")
        
        # ========== 第三步：DeepSeek推理生成JSON ==========
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

🚨【趋势标签判定规则】：
- 请根据检索到的资料，判断该剧的爆发速度。
- 如果该剧是刚刚上线几天就冲入榜单，或者新闻中明确提到其播放量增速极快、成为黑马，请将该剧的 `trend_tag` 字段赋值为 "🔥 飙升" 或 "🚀 新晋"。
- 如果只是老剧平稳表现，该字段请保留为空字符串 ""。

🚨【核心情绪与动机拆解】：
作为资深用户心理研究员，请深度分析今日上榜短剧的题材与爽点。除了常规字段，你必须推演出 `emotional_analysis` 对象。
请洞察这些剧情本质上是在为观众提供哪种【心理补偿】，以及它们精准踩中了当代社会的哪些【现实焦虑】。

请补全缺失字段并输出纯JSON对象，不要加```json包裹。结构必须为：
{{
  "rankings": [
    {{
      "rank": 1,
      "title": "剧名",
      "female_lead": "女演员",
      "male_lead": "男演员",
      "views": "播放量",
      "views_num": 0,
      "platform": "平台",
      "genre": "题材",
      "tags": ["标签"],
      "trend": "趋势",
      "trend_tag": "",
      "trend_type": "new/up/down/same",
      "category": "female/male/ai",
      "is_ai": false,
      "desc": "剧情描述",
      "production_house": "制作厂牌",
      "core_trope": ["核心爽点"],
      "episodes_count": 80
    }}
  ],
  "emotional_analysis": {{
    "primary_emotions": [
      {{"name": "心理补偿", "value": 35}},
      {{"name": "强力宣泄", "value": 32}},
      {{"name": "身份逆袭", "value": 28}}
    ],
    "target_anxieties": [
      {{"name": "职场阶层固化", "value": 34}},
      {{"name": "经济匮乏", "value": 31}},
      {{"name": "亲密关系失衡", "value": 27}}
    ]
  }}
}}"""
        
        response = ds_client.chat(
            messages=[
                {"role": "system", "content": sp or "你是数据提取与短剧用户心理研究专家。必须输出纯JSON对象，禁止编造传统影视明星。"},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=8000
        )
        
        logger.info(f"DeepSeek响应: {response[:500]}...")
        
        # ========== 健壮性解析 ==========
        rankings_data: List[Dict] = []
        emotional_analysis: Dict[str, List[Dict[str, Any]]] = default_emotional_analysis()
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
            
            # 优先提取JSON对象，兼容旧版JSON数组
            json_match = re.search(r'\{[\s\S]*\}', clean_response)
            if not json_match:
                json_match = re.search(r'\[[\s\S]*\]', clean_response)
            if json_match:
                json_str = json_match.group(0)
                parsed = json.loads(json_str)
                
                if isinstance(parsed, list):
                    rankings_data = parsed
                elif isinstance(parsed, dict):
                    rankings_data = parsed.get("rankings") or parsed.get("data") or []
                    candidate_analysis = parsed.get("emotional_analysis")
                    if isinstance(candidate_analysis, dict):
                        primary_emotions = candidate_analysis.get("primary_emotions")
                        target_anxieties = candidate_analysis.get("target_anxieties")
                        if isinstance(primary_emotions, list) and isinstance(target_anxieties, list):
                            emotional_analysis = {
                                "primary_emotions": primary_emotions[:3],
                                "target_anxieties": target_anxieties[:3],
                            }
            else:
                raise ValueError("未找到有效JSON对象或数组")
                
        except Exception as parse_error:
            logger.error(f"enrich_node: JSON解析失败: {parse_error}")
            logger.error(f"原始响应: {response}")
        
        try:
            rankings_data, count_warning = ensure_top_rankings(
                rankings_data,
                data_date=state.data_date,
                supplemental_rankings=rankings_json_list,
                workspace_path=os.getenv("COZE_WORKSPACE_PATH", ""),
            )
            if count_warning:
                logger.warning("enrich_node: %s", count_warning)
        except RankingCountError as count_error:
            error_message = f"enrich_node: {count_error}"
            logger.error(error_message)
            return EnrichNodeOutput(
                enriched_rankings=[],
                emotional_analysis=emotional_analysis,
                success=False,
                error_message=error_message + "\n"
            )

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
                trend_tag=item.get("trend_tag", ""),
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
            emotional_analysis=emotional_analysis,
            success=True,
            error_message=""
        )
        
    except Exception as e:
        error_message = f"enrich_node: 数据补充失败: {e}"
        logger.error(error_message, exc_info=True)
        return EnrichNodeOutput(
            enriched_rankings=[],
            success=False,
            error_message=error_message + "\n"
        )
