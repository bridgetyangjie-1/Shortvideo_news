"""
情绪与动机拆解节点 - 基于真实榜单做规则化归因 + DeepSeek 提炼

规则映射表外置到 config/emotion_rules.json，可按月审视更新，不再写死在代码里。
DeepSeek 失败时，summary 与 insights 基于当日实际统计数据动态生成，避免每天同一套兜底文案。
"""
import os
import json
import re
import math
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple, Optional
from collections import defaultdict
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from coze_coding_utils.runtime_ctx.context import Context
from tools.deepseek_api import DeepSeekClient
from graphs.state import (
    EmotionAnalysisNodeInput,
    EmotionAnalysisNodeOutput,
    EmotionalAnalysis,
    EmotionWordCloudItem,
    EmotionRankingItem,
    EmotionTrendItem,
    ActionableInsight,
    default_emotional_analysis,
)

logger = logging.getLogger(__name__)


# ==================== 内置默认规则（config/emotion_rules.json 缺失时使用）====================

_DEFAULT_EMOTION_RULES: List[Tuple[List[str], str, int]] = [
    # (匹配关键词列表, 维度名称, 基础强度)
    # 情绪
    (["打脸", "虐渣", "复仇", "逆袭", "重生", "马甲", "战神", "赘婿"], "身份逆袭", 60),
    (["甜宠", "撒糖", "总裁", "先婚后爱", "闪婚", "契约"], "浪漫幻想", 55),
    (["萌宝", "带娃", "团宠"], "心理补偿", 55),
    (["悬疑", "推理", "惊悚", "恐怖", "无限流"], "猎奇刺激", 55),
    (["职场", "商战", "创业"], "自我实现", 50),
    # 焦虑
    (["离婚", "前夫", "前妻", "出轨", "背叛", "追妻", "追夫"], "亲密关系失衡", 60),
    (["职场", "裁员", "加班", "上司", "同事"], "职场阶层固化", 55),
    (["破产", "欠债", "穷", "暴富", "千金", "首富"], "经济匮乏", 55),
    (["婆媳", "家斗", "亲戚", "极品"], "家庭矛盾", 50),
    (["容貌", "变美", "减肥", "逆袭", "丑女"], "容貌年龄焦虑", 45),
    (["校园", "霸凌", "社恐", "孤立"], "社会认同缺失", 45),
    # 触发点
    (["打脸", "虐渣", "复仇"], "复仇打脸", 65),
    (["甜宠", "撒糖", "吻"], "甜宠撒糖", 55),
    (["身份", "马甲", "揭晓", "暴露"], "身份揭晓", 55),
    (["反转", "虐心", "误会", "追妻火葬场"], "虐心反转", 50),
    (["悬念", "推理", "凶手", "真相"], "高能悬念", 50),
    (["萌宝", "团宠", "助攻"], "萌宝助攻", 50),
    # 内容期待
    (["快节奏", "爽", "反转", "打脸"], "快节奏", 55),
    (["大女主", "强女主", "女主", "女强"], "强女主", 55),
    (["智商", "谋略", "智斗", "布局"], "智商在线", 50),
    (["反套路", "创新", "穿越"], "反套路", 45),
    # 代偿场景
    (["职场", "裁员", "上司"], "职场受挫", 55),
    (["离婚", "前夫", "亲密关系", "出轨"], "亲密关系", 60),
    (["破产", "欠债", "穷"], "经济压力", 50),
    (["婆媳", "家斗", "亲戚"], "家庭矛盾", 50),
    (["孤独", "无聊", "解压", "下班"], "孤独无聊", 45),
    # 观看动机
    (["爽", "打脸", "复仇"], "解压放空", 55),
    (["甜宠", "总裁", "浪漫"], "情感代偿", 55),
    (["连载", "追更", "日更"], "追更陪伴", 45),
    (["悬疑", "无限流", "新剧"], "猎奇尝鲜", 50),
]

_DEFAULT_DIMENSION_CATEGORIES: Dict[str, str] = {
    "身份逆袭": "emotion",
    "浪漫幻想": "emotion",
    "心理补偿": "emotion",
    "猎奇刺激": "emotion",
    "自我实现": "emotion",
    "亲密关系失衡": "anxiety",
    "职场阶层固化": "anxiety",
    "经济匮乏": "anxiety",
    "家庭矛盾": "anxiety",
    "容貌年龄焦虑": "anxiety",
    "社会认同缺失": "anxiety",
    "复仇打脸": "trigger",
    "甜宠撒糖": "trigger",
    "身份揭晓": "trigger",
    "虐心反转": "trigger",
    "高能悬念": "trigger",
    "萌宝助攻": "trigger",
    "快节奏": "expectation",
    "强女主": "expectation",
    "智商在线": "expectation",
    "反套路": "expectation",
    "职场受挫": "payoff",
    "亲密关系": "payoff",
    "经济压力": "payoff",
    "家庭矛盾": "payoff",
    "孤独无聊": "payoff",
    "解压放空": "motivation",
    "情感代偿": "motivation",
    "追更陪伴": "motivation",
    "猎奇尝鲜": "motivation",
}


# ==================== 加载外置规则 ====================

def _load_emotion_rules(
    workspace_path: Optional[str] = None,
) -> Tuple[List[Tuple[List[str], str, int]], Dict[str, str]]:
    """
    从 config/emotion_rules.json 加载情绪维度规则。

    如果文件不存在或解析失败，返回内置默认规则，保证节点不中断。
    """
    root = workspace_path or os.getenv("COZE_WORKSPACE_PATH", os.getcwd())
    rules_file = os.path.join(root, "config", "emotion_rules.json")

    if not os.path.exists(rules_file):
        logger.warning("emotion_analysis_node: config/emotion_rules.json 不存在，使用内置默认规则")
        return _DEFAULT_EMOTION_RULES, _DEFAULT_DIMENSION_CATEGORIES

    try:
        with open(rules_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("emotion_analysis_node: 解析 emotion_rules.json 失败: %s，使用内置默认规则", e)
        return _DEFAULT_EMOTION_RULES, _DEFAULT_DIMENSION_CATEGORIES

    rules_data = data.get("rules")
    if not isinstance(rules_data, list) or not rules_data:
        logger.warning("emotion_analysis_node: emotion_rules.json 中 rules 为空，使用内置默认规则")
        return _DEFAULT_EMOTION_RULES, _DEFAULT_DIMENSION_CATEGORIES

    rules: List[Tuple[List[str], str, int]] = []
    categories: Dict[str, str] = {}

    for item in rules_data:
        if not isinstance(item, dict):
            continue
        keywords = item.get("keywords")
        dimension = item.get("dimension")
        base_score = item.get("base_score")
        category = item.get("category")

        if (
            not isinstance(keywords, list)
            or not dimension
            or not isinstance(dimension, str)
            or not isinstance(base_score, (int, float))
        ):
            continue

        keywords = [str(k).strip() for k in keywords if isinstance(k, str) and k.strip()]
        if not keywords:
            continue

        rules.append((keywords, dimension.strip(), int(base_score)))
        if isinstance(category, str) and category.strip():
            categories[dimension.strip()] = category.strip()

    if not rules:
        logger.warning("emotion_analysis_node: emotion_rules.json 未解析出有效规则，使用内置默认规则")
        return _DEFAULT_EMOTION_RULES, _DEFAULT_DIMENSION_CATEGORIES

    logger.info("emotion_analysis_node: 已从 config/emotion_rules.json 加载 %s 条情绪规则", len(rules))
    return rules, categories


# 模块加载时读取一次；后续如需热更新可重新调用 _load_emotion_rules
EMOTION_RULES, DIMENSION_CATEGORIES = _load_emotion_rules()


# ==================== 规则化统计与构建 ====================

def _extract_text(drama: Any) -> str:
    """从剧目对象中提取可用于匹配规则的文本。"""
    texts: List[str] = []
    if hasattr(drama, "title"):
        texts.append(str(getattr(drama, "title", "") or ""))
        texts.append(str(getattr(drama, "genre", "") or ""))
        texts.append(str(getattr(drama, "desc", "") or ""))
        tags = getattr(drama, "tags", []) or []
        core_trope = getattr(drama, "core_trope", []) or []
        texts.extend([str(t) for t in tags])
        texts.extend([str(t) for t in core_trope])
    elif isinstance(drama, dict):
        texts.append(str(drama.get("title", "")))
        texts.append(str(drama.get("genre", "")))
        texts.append(str(drama.get("desc", "")))
        texts.extend([str(t) for t in (drama.get("tags") or [])])
        texts.extend([str(t) for t in (drama.get("core_trope") or [])])
    return " ".join(texts)


def _rank_weight(rank: int) -> int:
    """排名越靠前权重越高，TOP1=20，TOP20=1。"""
    return max(1, 21 - rank)


def _aggregate_emotion_scores(
    rankings: List[Any],
    rules: Optional[List[Tuple[List[str], str, int]]] = None,
) -> Dict[str, int]:
    """基于规则映射和排名加权，统计各情绪维度得分。"""
    rules = rules or EMOTION_RULES
    scores: Dict[str, int] = defaultdict(int)
    for drama in rankings:
        rank = 0
        if hasattr(drama, "rank"):
            rank = int(getattr(drama, "rank", 0) or 0)
        elif isinstance(drama, dict):
            rank = int(drama.get("rank", 0) or 0)
        weight = _rank_weight(rank)
        text = _extract_text(drama)
        if not text:
            continue
        for keywords, dimension, base_score in rules:
            if any(kw in text for kw in keywords):
                scores[dimension] += int(base_score * weight / 10)
    return dict(scores)


def _build_wordcloud(
    scores: Dict[str, int],
    categories: Optional[Dict[str, str]] = None,
) -> List[EmotionWordCloudItem]:
    """把得分转成词云，按 category 分类，取 TOP15。

    采用 log1p 压缩 + max-normalization，避免多个维度同时顶到 100 失去区分度。
    """
    categories = categories or DIMENSION_CATEGORIES
    if not scores:
        return []

    # log1p 压缩：削弱极端高分，保留相对差异
    log_scores = {name: math.log1p(value) for name, value in scores.items()}
    max_log = max(log_scores.values()) if log_scores else 1.0

    items = []
    for name, value in log_scores.items():
        cat = categories.get(name, "emotion")
        normalized = int(value / max_log * 100) if max_log > 0 else 0
        items.append(EmotionWordCloudItem(name=name, value=normalized, category=cat))

    items.sort(key=lambda x: x.value, reverse=True)
    return items[:15]


def _build_emotion_rankings(
    rankings: List[Any],
    scores: Dict[str, int],
    rules: Optional[List[Tuple[List[str], str, int]]] = None,
    categories: Optional[Dict[str, str]] = None,
) -> List[EmotionRankingItem]:
    """为 TOP3 剧目绑定情绪标签。"""
    rules = rules or EMOTION_RULES
    categories = categories or DIMENSION_CATEGORIES

    # 找出得分最高的三个维度作为主导维度
    top_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_dim_names = [d[0] for d in top_dims]

    # 为每个分类预选一个最佳维度（从实际 scores 取，不再硬编码）
    best_by_category: Dict[str, str] = {}
    for dim, _ in top_dims:
        cat = categories.get(dim, "emotion")
        if cat not in best_by_category:
            best_by_category[cat] = dim

    result = []
    for drama in rankings[:3]:
        rank = int(getattr(drama, "rank", 0) or (drama.get("rank", 0) if isinstance(drama, dict) else 0))
        title = str(getattr(drama, "title", "") or (drama.get("title", "") if isinstance(drama, dict) else ""))
        text = _extract_text(drama)

        # 为该剧目匹配最相关的维度
        matched: List[Tuple[str, int]] = []
        for keywords, dimension, base_score in rules:
            if any(kw in text for kw in keywords):
                matched.append((dimension, base_score))

        # 默认值从实际 top scores 取，避免每天同一套兜底
        primary_emotion = best_by_category.get("emotion", top_dim_names[0] if top_dim_names else "身份逆袭")
        anxiety = best_by_category.get("anxiety", top_dim_names[0] if top_dim_names else "亲密关系失衡")
        trigger = best_by_category.get("trigger", top_dim_names[0] if top_dim_names else "复仇打脸")

        if matched:
            dim_counts: Dict[str, int] = defaultdict(int)
            for dim, score in matched:
                dim_counts[dim] += score
            best_dim = max(dim_counts.items(), key=lambda x: x[1])[0]
            cat = categories.get(best_dim, "emotion")
            if cat == "emotion":
                primary_emotion = best_dim
            elif cat == "anxiety":
                anxiety = best_dim
            elif cat == "trigger":
                trigger = best_dim
            else:
                trigger = best_dim

        # 如果该剧目没匹配到某分类，从全局 top 维度补齐
        valid_emotions = {d for d, c in categories.items() if c == "emotion"}
        valid_anxieties = {d for d, c in categories.items() if c == "anxiety"}
        valid_triggers = {d for d, c in categories.items() if c == "trigger"}

        if primary_emotion not in valid_emotions:
            for d in top_dim_names:
                if categories.get(d) == "emotion":
                    primary_emotion = d
                    break
        if anxiety not in valid_anxieties:
            for d in top_dim_names:
                if categories.get(d) == "anxiety":
                    anxiety = d
                    break
        if trigger not in valid_triggers:
            for d in top_dim_names:
                if categories.get(d) == "trigger":
                    trigger = d
                    break

        result.append(EmotionRankingItem(
            rank=rank,
            title=title,
            primary_emotion=primary_emotion,
            anxiety=anxiety,
            trigger=trigger,
            one_line=""
        ))
    return result


# ==================== 历史趋势与 JSON 解析 ====================

def _load_yesterday_wordcloud(data_date: str, workspace_path: str) -> Dict[str, int]:
    """读取前一天的 emotional_analysis.wordcloud 用于环比。"""
    try:
        yesterday = (datetime.strptime(data_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        history_file = os.path.join(workspace_path, "assets", "data", "history", f"{yesterday}.json")
        if not os.path.exists(history_file):
            return {}
        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        ea = data.get("emotional_analysis") or {}
        wordcloud = ea.get("wordcloud") or []
        return {item.get("name", ""): int(item.get("value", 0) or 0) for item in wordcloud if item.get("name")}
    except Exception as e:
        logger.warning(f"读取昨日情绪词云失败: {e}")
        return {}


def _build_trends(current_scores: Dict[str, int], yesterday_scores: Dict[str, int]) -> List[EmotionTrendItem]:
    """计算 TOP8 情绪维度较昨日变化。"""
    trends = []
    for name, value in sorted(current_scores.items(), key=lambda x: x[1], reverse=True)[:8]:
        yesterday_value = yesterday_scores.get(name, 0)
        change = value - yesterday_value
        if yesterday_value == 0:
            trend = "new" if value > 15 else "same"
        elif change >= 10:
            trend = "up"
        elif change <= -10:
            trend = "down"
        else:
            trend = "same"
        trends.append(EmotionTrendItem(name=name, change=change, trend=trend))
    return trends


def _parse_json_response(response: str) -> Optional[Dict[str, Any]]:
    """从 DeepSeek 响应中提取 JSON 对象。"""
    if not response:
        return None
    text = response.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


# ==================== 动态兜底文案生成 ====================

def _build_fallback_summary(
    dominant_emotion: str,
    dominant_anxiety: str,
    top_trigger: str,
    top_titles: List[str],
) -> str:
    """DeepSeek 失败时，基于实际统计数据动态生成 summary。"""
    titles_text = "、".join(top_titles[:3]) if top_titles else "头部剧目"
    templates = [
        f"今日榜单以{dominant_emotion}为核心驱动力，融合{dominant_anxiety}与{top_trigger}，"
        f"《{titles_text}》等剧集中体现了观众对现实焦虑的强烈代偿需求。",
        f"今日短剧市场由{dominant_emotion}主导，观众通过{top_trigger}释放{dominant_anxiety}，"
        f"《{titles_text}》成为典型情绪载体。",
        f"从今日榜单看，{dominant_emotion}情绪占据上风，{dominant_anxiety}是主要现实焦虑来源，"
        f"{top_trigger}为最高频触发点，《{titles_text}》等作品精准命中该心理。",
    ]
    # 根据日期选择模板，保证同一日期稳定、不同日期有变化
    day = int(datetime.now().strftime("%d"))
    return templates[day % len(templates)]


def _build_fallback_insights(
    dominant_emotion: str,
    dominant_anxiety: str,
    top_trigger: str,
    top_titles: List[str],
) -> List[ActionableInsight]:
    """DeepSeek 失败时，基于实际统计数据动态生成 3 条建议。"""
    titles_text = "、".join(top_titles[:3]) if top_titles else "榜单TOP3"
    return [
        ActionableInsight(
            icon="💡",
            title="聚焦主导情绪",
            content=f"今日'{dominant_emotion}'情绪显著，新剧本可围绕'{top_trigger}'设计前3秒冲突，"
                    f"参考《{titles_text}》的爽点结构，提升素材CTR。",
        ),
        ActionableInsight(
            icon="📈",
            title="瞄准现实焦虑",
            content=f"观众对'{dominant_anxiety}'的代偿需求强，投流文案可直接点出痛点并展示反转爽点，"
                    f"强化情绪共鸣与转化。",
        ),
        ActionableInsight(
            icon="🎯",
            title="复用高触发题材",
            content=f"《{titles_text}》均命中'{top_trigger}'，后续创作可延续该爽点框架，"
                    f"在人物关系或时代背景上做微创新。",
        ),
    ]


# ==================== 节点主函数 ====================

def emotion_analysis_node(
    state: EmotionAnalysisNodeInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> EmotionAnalysisNodeOutput:
    """
    title: 核心情绪与动机拆解
    desc: 基于外置规则表统计情绪维度，DeepSeek 提炼总览与行动建议；失败时动态兜底
    integrations: DeepSeek API
    """
    try:
        rankings = list(state.enriched_rankings) if state.enriched_rankings else []
        if not rankings:
            return EmotionAnalysisNodeOutput(
                emotional_analysis=default_emotional_analysis(),
                success=False,
                error_message="emotion_analysis_node: 输入榜单为空\n"
            )

        # 读取配置文件（温度等参数）
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), config["metadata"]["llm_cfg"])
        temperature = 0.4
        try:
            with open(cfg_file, "r", encoding="utf-8") as fd:
                _cfg = json.load(fd)
            temperature = _cfg.get("config", {}).get("temperature", 0.4)
        except Exception:
            pass

        workspace_path = os.getenv("COZE_WORKSPACE_PATH", os.getcwd())
        data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")

        # 支持热更新：每次运行重新加载规则
        rules, categories = _load_emotion_rules(workspace_path)

        # 1. 规则化统计情绪维度
        scores = _aggregate_emotion_scores(rankings, rules=rules)
        if not scores:
            scores = {
                "心理补偿": 35, "身份逆袭": 32, "亲密关系失衡": 30,
                "复仇打脸": 28, "解压放空": 25, "快节奏": 22
            }

        wordcloud = _build_wordcloud(scores, categories=categories)
        emotion_rankings = _build_emotion_rankings(rankings, scores, rules=rules, categories=categories)

        # 2. 计算环比趋势
        yesterday_scores = _load_yesterday_wordcloud(data_date, workspace_path)
        trends = _build_trends(scores, yesterday_scores)

        # 3. 主导维度（从实际 scores 取，不再硬编码）
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        dominant_emotion = next((n for n, _ in sorted_scores if categories.get(n) == "emotion"), sorted_scores[0][0] if sorted_scores else "身份逆袭")
        dominant_anxiety = next((n for n, _ in sorted_scores if categories.get(n) == "anxiety"), sorted_scores[0][0] if sorted_scores else "亲密关系失衡")
        top_trigger = next((n for n, _ in sorted_scores if categories.get(n) == "trigger"), sorted_scores[0][0] if sorted_scores else "复仇打脸")

        # 4. DeepSeek 提炼：总览 + 剧目 one_line + 行动建议
        ds_client = DeepSeekClient()
        top_titles = [r.title for r in emotion_rankings]
        top_tags = [item.name for item in wordcloud[:8]]

        prompt = f"""你是短剧用户心理研究专家。请基于以下今日榜单情绪统计数据，输出纯 JSON（不要 Markdown 包裹）：

【数据日期】：{data_date}
【主导情绪】：{dominant_emotion}
【主导焦虑】：{dominant_anxiety}
【TOP1 触发点】：{top_trigger}
【TOP3 情绪典型剧目】：{', '.join(top_titles)}
【TOP8 情绪关键词】：{', '.join(top_tags)}

请输出以下字段：
- summary: 一句话总结今日榜单情绪特征（40-60字），要具体到今天榜单题材，禁止泛泛而谈。
- emotion_rankings_oneliners: 数组，长度为 {len(emotion_rankings)}，依次给每部剧写一句心理拆解（20-30字）。
- actionable_insights: 数组，3 条针对创作者/投流方的可执行建议，每条包含 title（15字内）和 content（80-120字）。

JSON 结构：
{{
  "summary": "...",
  "emotion_rankings_oneliners": ["...", "...", "..."],
  "actionable_insights": [
    {{"icon": "💡", "title": "...", "content": "..."}},
    {{"icon": "📈", "title": "...", "content": "..."}},
    {{"icon": "🎯", "title": "...", "content": "..."}}
  ]
}}"""

        try:
            response = ds_client.chat(
                messages=[
                    {"role": "system", "content": "你是短剧用户心理研究专家，只输出纯JSON。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=2000
            )
            parsed = _parse_json_response(response) or {}
        except Exception as e:
            logger.warning(f"DeepSeek 情绪提炼失败: {e}")
            parsed = {}

        summary = parsed.get("summary") or _build_fallback_summary(dominant_emotion, dominant_anxiety, top_trigger, top_titles)
        oneliners = parsed.get("emotion_rankings_oneliners") or []
        insights_raw = parsed.get("actionable_insights") or []

        # 5. 合并 DeepSeek 结果
        for idx, item in enumerate(emotion_rankings):
            if idx < len(oneliners) and oneliners[idx]:
                item.one_line = str(oneliners[idx])
            else:
                item.one_line = f"用{item.primary_emotion}补偿{item.anxiety}中的价值缺失"

        actionable_insights: List[ActionableInsight] = []
        fallback_insights = _build_fallback_insights(dominant_emotion, dominant_anxiety, top_trigger, top_titles)
        for idx in range(3):
            if idx < len(insights_raw) and isinstance(insights_raw[idx], dict):
                raw = insights_raw[idx]
                actionable_insights.append(ActionableInsight(
                    icon=str(raw.get("icon") or fallback_insights[idx].icon),
                    title=str(raw.get("title") or fallback_insights[idx].title),
                    content=str(raw.get("content") or fallback_insights[idx].content),
                ))
            else:
                actionable_insights.append(fallback_insights[idx])

        emotional_analysis = EmotionalAnalysis(
            summary=summary,
            dominant_emotion=dominant_emotion,
            dominant_anxiety=dominant_anxiety,
            top_trigger=top_trigger,
            wordcloud=wordcloud,
            emotion_rankings=emotion_rankings,
            trends=trends,
            actionable_insights=actionable_insights,
            data_source="当日榜单规则统计 + DeepSeek 提炼" if parsed else "当日榜单规则统计（DeepSeek 提炼失败）",
            update_frequency="daily",
        )

        return EmotionAnalysisNodeOutput(
            emotional_analysis=emotional_analysis,
            success=True,
            error_message=""
        )

    except Exception as e:
        error_message = f"emotion_analysis_node: 情绪分析失败: {e}"
        logger.error(error_message, exc_info=True)
        return EmotionAnalysisNodeOutput(
            emotional_analysis=default_emotional_analysis(),
            success=False,
            error_message=error_message + "\n"
        )
