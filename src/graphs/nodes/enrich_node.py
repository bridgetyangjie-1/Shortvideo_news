"""
数据补充节点 - 双模型协同解耦架构
Kimi负责搜索，DeepSeek负责推理，并通过本地缓存复用旧剧资料
"""
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Tuple

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from graphs.ranking_quality import RankingCountError, ensure_top_rankings
from graphs.state import DramaRanking, EnrichNodeInput, EnrichNodeOutput, default_emotional_analysis
from tools.deepseek_api import DeepSeekClient
from tools.moonshot_api import MoonshotClient

CACHE_FILE = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "."), "assets", "dramas_cache.json")

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DYNAMIC_FIELDS = {
    "rank",
    "title",
    "views",
    "views_num",
    "platform",
    "trend",
    "trend_tag",
    "trend_type",
}


def _drama_to_dict(drama: Any) -> Dict[str, Any]:
    if hasattr(drama, "model_dump"):
        dumped = drama.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(drama, dict):
        return dict(drama)
    return {}


def _get_title(drama: Any) -> str:
    if hasattr(drama, "title"):
        return str(getattr(drama, "title", "") or "").strip()
    if isinstance(drama, dict):
        return str(drama.get("title", "") or "").strip()
    return ""


def _load_cache() -> Dict[str, Dict[str, Any]]:
    try:
        if not os.path.exists(CACHE_FILE):
            logger.info("enrich_node: 缓存文件不存在，初始化为空缓存: %s", CACHE_FILE)
            return {}
        with open(CACHE_FILE, "r", encoding="utf-8") as fd:
            cache_data = json.load(fd)
        if not isinstance(cache_data, dict):
            logger.warning("enrich_node: 缓存文件格式不是字典，已忽略: %s", CACHE_FILE)
            return {}
        return {str(title): value for title, value in cache_data.items() if isinstance(value, dict)}
    except Exception as cache_error:
        logger.warning("enrich_node: 读取缓存失败，将使用空缓存: %s", cache_error)
        return {}


def _write_cache(cache_data: Dict[str, Dict[str, Any]]) -> None:
    try:
        cache_dir = os.path.dirname(CACHE_FILE)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as fd:
            json.dump(cache_data, fd, ensure_ascii=False, indent=2)
        logger.info("enrich_node: 缓存已更新，共%s部剧: %s", len(cache_data), CACHE_FILE)
    except Exception as cache_error:
        logger.warning("enrich_node: 写入缓存失败: %s", cache_error)


def _merge_drama_data(base_data: Dict[str, Any], enrich_data: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base_data)
    for key, value in enrich_data.items():
        if value not in (None, "", [], {}):
            merged[key] = value

    # 当前榜单中的动态字段优先，避免缓存里的旧排名、播放量覆盖今日数据。
    for key in DYNAMIC_FIELDS:
        value = base_data.get(key)
        if value not in (None, "", [], {}):
            merged[key] = value

    merged["title"] = base_data.get("title") or enrich_data.get("title", "")
    merged["enriched"] = True
    return merged


def _normalise_for_cache(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": item.get("title", ""),
        "female_lead": item.get("female_lead", ""),
        "male_lead": item.get("male_lead", ""),
        "genre": item.get("genre", ""),
        "tags": item.get("tags", []),
        "category": item.get("category", "female"),
        "is_ai": item.get("is_ai", False),
        "desc": item.get("desc", ""),
        "production_house": item.get("production_house", "独立厂牌"),
        "core_trope": item.get("core_trope", []),
        "episodes_count": item.get("episodes_count", 80),
    }


def _parse_deepseek_response(response: str) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    rankings_data: List[Dict[str, Any]] = []
    emotional_analysis: Dict[str, List[Dict[str, Any]]] = default_emotional_analysis()

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
    json_match = re.search(r"\{[\s\S]*\}", clean_response)
    if not json_match:
        json_match = re.search(r"\[[\s\S]*\]", clean_response)
    if not json_match:
        raise ValueError("未找到有效JSON对象或数组")

    parsed = json.loads(json_match.group(0))
    if isinstance(parsed, list):
        rankings_data = [item for item in parsed if isinstance(item, dict)]
    elif isinstance(parsed, dict):
        candidate_rankings = parsed.get("rankings") or parsed.get("data") or []
        if isinstance(candidate_rankings, list):
            rankings_data = [item for item in candidate_rankings if isinstance(item, dict)]

        candidate_analysis = parsed.get("emotional_analysis")
        if isinstance(candidate_analysis, dict):
            primary_emotions = candidate_analysis.get("primary_emotions")
            target_anxieties = candidate_analysis.get("target_anxieties")
            if isinstance(primary_emotions, list) and isinstance(target_anxieties, list):
                emotional_analysis = {
                    "primary_emotions": primary_emotions[:3],
                    "target_anxieties": target_anxieties[:3],
                }

    return rankings_data, emotional_analysis


def _build_ranking(item: Dict[str, Any]) -> DramaRanking:
    return DramaRanking(
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
        episodes_count=item.get("episodes_count", 80),
    )


def enrich_node(state: EnrichNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> EnrichNodeOutput:
    """
    title: 数据补充（双模型协同 + 本地缓存）
    desc: 旧剧复用缓存，新剧才执行Kimi搜索和DeepSeek推理
    integrations: Moonshot API + DeepSeek API
    """
    try:
        _ = runtime.context
        search_errors: List[str] = []
        basic_rankings_list = list(state.basic_rankings) if hasattr(state.basic_rankings, "__iter__") else []

        if not basic_rankings_list:
            error_message = "enrich_node: 输入 basic_rankings 为空"
            logger.error(error_message)
            return EnrichNodeOutput(
                enriched_rankings=[],
                success=False,
                error_message=error_message + "\n",
            )

        rankings_json_list = [_drama_to_dict(r_item) for r_item in basic_rankings_list]
        rankings_json_list = [item for item in rankings_json_list if item]

        cache_data = _load_cache()
        logger.info("enrich_node: 已加载缓存%s部剧", len(cache_data))

        merged_by_title: Dict[str, Dict[str, Any]] = {}
        need_enrich_list: List[Any] = []
        need_enrich_json_list: List[Dict[str, Any]] = []

        # ========== 分流阶段：旧剧命中缓存，新剧进入待抓取列表 ==========
        for drama in basic_rankings_list:
            title = _get_title(drama)
            base_data = _drama_to_dict(drama)
            if not title:
                logger.warning("enrich_node: 跳过无标题剧目: %s", base_data)
                continue

            if title in cache_data:
                merged_by_title[title] = _merge_drama_data(base_data, cache_data[title])
                logger.info("enrich_node: 命中缓存《%s》", title)
            else:
                need_enrich_list.append(drama)
                need_enrich_json_list.append(base_data)
                logger.info("enrich_node: 新剧待补充《%s》", title)

        emotional_analysis: Dict[str, List[Dict[str, Any]]] = default_emotional_analysis()

        # ========== 搜集与推理阶段：仅处理新剧 ==========
        if need_enrich_list:
            # 读取配置文件
            cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
            with open(cfg_file, "r", encoding="utf-8") as fd:
                _cfg = json.load(fd)

            sp = _cfg.get("sp", "")
            temperature = _cfg.get("config", {}).get("temperature", 0.3)

            # 初始化双客户端
            kimi_client = MoonshotClient()
            ds_client = DeepSeekClient()

            # ========== 搜集阶段：Kimi搜索新剧 ==========
            real_search_context = ""
            for drama in need_enrich_list:
                title = _get_title(drama)
                if not title:
                    continue

                logger.info("Kimi多轮搜索新剧《%s》...", title)

                # 多轮搜索策略：尝试多种关键词组合
                search_queries = [
                    f"短剧《{title}》主演演员女演员男主角女主角",
                    f"《{title}》短剧演员阵容DataEye红果短剧",
                    f"短剧 {title} 主演是谁 小红书抖音豆瓣",
                ]

                search_found = False
                for query in search_queries:
                    try:
                        search_res: str = kimi_client.search(query, max_results=3)
                        # 检查搜索结果是否包含演员信息（关键词：演员、主演、女主、男主）
                        if search_res and any(keyword in search_res for keyword in ["演员", "主演", "女主", "男主", "女主角", "男主角"]):
                            search_text = search_res[:2000] if len(search_res) > 2000 else search_res
                            real_search_context += f"\n【剧目：《{title}》真实检索】:\n{search_text}\n"
                            logger.info("搜索《%s》成功，找到演员信息", title)
                            search_found = True
                            break
                        time.sleep(1)
                    except Exception as e:
                        logger.warning("搜索《%s》关键词'%s'失败: %s", title, query, e)
                        time.sleep(1)

                if not search_found:
                    # 搜索失败时添加推理补充提示
                    real_search_context += f"\n【剧目：《{title}》搜索无结果，请推理补充】\n"
                    logger.warning("《%s》未找到演员信息，将推理补充", title)

                time.sleep(1)

            user_prompt = f"""【数据日期】：{state.data_date}
【待补充新剧基础榜单数据】：
{json.dumps(need_enrich_json_list, ensure_ascii=False, indent=2)}

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
作为资深用户心理研究员，请深度分析今日新上榜短剧的题材与爽点。除了常规字段，你必须推演出 `emotional_analysis` 对象。
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
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=8000,
            )

            logger.info("DeepSeek响应: %s...", response[:500])

            # ========== 健壮性解析 ==========
            parsed_new_rankings: List[Dict[str, Any]] = []
            try:
                parsed_new_rankings, emotional_analysis = _parse_deepseek_response(response)
            except Exception as parse_error:
                logger.error("enrich_node: JSON解析失败: %s", parse_error)
                logger.error("原始响应: %s", response)
                search_errors.append(f"JSON解析失败: {parse_error}")

            parsed_by_title: Dict[str, Dict[str, Any]] = {}
            for item in parsed_new_rankings:
                title = str(item.get("title", "") or "").strip()
                if title:
                    parsed_by_title[title] = item

            cache_updated = False
            for base_data in need_enrich_json_list:
                title = str(base_data.get("title", "") or "").strip()
                if not title:
                    continue

                enrich_data = parsed_by_title.get(title, {})
                merged_item = _merge_drama_data(base_data, enrich_data)
                merged_by_title[title] = merged_item

                if enrich_data:
                    cache_data[title] = _normalise_for_cache(merged_item)
                    cache_updated = True
                    logger.info("enrich_node: 新剧《%s》已写入缓存", title)
                else:
                    logger.warning("enrich_node: 新剧《%s》未从DeepSeek结果中解析到，将使用基础数据兜底", title)

            if cache_updated:
                _write_cache(cache_data)
        else:
            logger.info("enrich_node: 全部剧目命中缓存，本轮不调用Kimi和DeepSeek")

        # ========== 合并输出：按原始榜单顺序组装完整列表 ==========
        rankings_data: List[Dict[str, Any]] = []
        for drama in basic_rankings_list:
            title = _get_title(drama)
            base_data = _drama_to_dict(drama)
            if title and title in merged_by_title:
                rankings_data.append(merged_by_title[title])
            elif base_data:
                fallback_item = dict(base_data)
                fallback_item["enriched"] = False
                rankings_data.append(fallback_item)

        try:
            rankings_data, count_warning = ensure_top_rankings(
                rankings_data,
                data_date=state.data_date,
                supplemental_rankings=rankings_json_list,
                workspace_path=os.getenv("COZE_WORKSPACE_PATH", ""),
            )
            if count_warning:
                logger.warning("enrich_node: %s", count_warning)
                search_errors.append(f"enrich_node: {count_warning}")
        except RankingCountError as count_error:
            error_message = f"enrich_node: {count_error}"
            logger.error(error_message)
            return EnrichNodeOutput(
                enriched_rankings=[],
                emotional_analysis=emotional_analysis,
                success=False,
                error_message=error_message + "\n",
            )

        # 转换为DramaRanking对象
        enriched_rankings: List[DramaRanking] = []
        for item in rankings_data:
            if not isinstance(item, dict):
                continue
            enriched_rankings.append(_build_ranking(item))

        logger.info("数据补充完成，共%s部剧，其中新剧%s部", len(enriched_rankings), len(need_enrich_list))

        return EnrichNodeOutput(
            enriched_rankings=enriched_rankings,
            emotional_analysis=emotional_analysis,
            success=True,
            error_message=("\n".join(search_errors) + "\n") if search_errors else "",
        )

    except Exception as e:
        error_message = f"enrich_node: 数据补充失败: {e}"
        logger.error(error_message, exc_info=True)
        return EnrichNodeOutput(
            enriched_rankings=[],
            success=False,
            error_message=error_message + "\n",
        )