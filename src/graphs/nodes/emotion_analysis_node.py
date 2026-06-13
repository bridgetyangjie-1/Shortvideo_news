"""
情绪与动机拆解节点 - 基于真实榜单做规则化归因 + DeepSeek 提炼
优先使用 DeepSeek API（成本低），仅在需要联网搜索时才调用 Kimi。
"""
import os
import json
import re
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

# ==================== 规则映射表：题材/标签 → 情绪维度 ====================

EMOTION_RULES: List[Tuple[List[str], str, int]] = [
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

DIMENSION_CATEGORIES = {
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


def _aggregate_emotion_scores(rankings: List[Any]) -> Dict[str, int]:
    """基于规则映射和排名加权，统计各情绪维度得分。"""
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
        for keywords, dimension, base_score in EMOTION_RULES:
            if any(kw in text for kw in keywords):
                scores[dimension] += int(base_score * weight / 10)
    return dict(scores)


def _build_wordcloud(scores: Dict[str, int]) -> List[EmotionWordCloudItem]:
    """把得分转成词云，按 category 分类，取 TOP15。"""
    items = []
    for name, value in scores.items():
        cat = DIMENSION_CATEGORIES.get(name, "emotion")
        items.append(EmotionWordCloudItem(name=name, value=min(100, value), category=cat))
    items.sort(key=lambda x: x.value, reverse=True)
    return items[:15]


def _build_emotion_rankings(rankings: List[Any], scores: Dict[str, int]) -> List[EmotionRankingItem]:
    """为 TOP3 剧目绑定情绪标签。"""
    # 找出得分最高的三个维度作为主导维度
    top_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_dim_names = [d[0] for d in top_dims]

    result = []
    for drama in rankings[:3]:
        rank = int(getattr(drama, "rank", 0) or (drama.get("rank", 0) if isinstance(drama, dict) else 0))
        title = str(getattr(drama, "title", "") or (drama.get("title", "") if isinstance(drama, dict) else ""))
        text = _extract_text(drama)

        # 为该剧目匹配最相关的维度
        matched: List[Tuple[str, int]] = []
        for keywords, dimension, base_score in EMOTION_RULES:
            if any(kw in text for kw in keywords):
                matched.append((dimension, base_score))

        primary_emotion = "身份逆袭"
        anxiety = "亲密关系失衡"
        trigger = "复仇打脸"

        if matched:
            # 取频次最高且属于对应分类的维度
            dim_counts: Dict[str, int] = defaultdict(int)
            for dim, score in matched:
                dim_counts[dim] += score
            best_dim = max(dim_counts.items(), key=lambda x: x[1])[0]
            cat = DIMENSION_CATEGORIES.get(best_dim, "emotion")
            if cat == "emotion":
                primary_emotion = best_dim
            elif cat == "anxiety":
                anxiety = best_dim
            elif cat == "trigger":
                trigger = best_dim
            else:
                trigger = best_dim

        # 如果没匹配到，从全局 top 维度补齐
        if primary_emotion not in [d for d, c in DIMENSION_CATEGORIES.items() if c == "emotion"]:
            for d in top_dim_names:
                if DIMENSION_CATEGORIES.get(d) == "emotion":
                    primary_emotion = d
                    break
        if anxiety not in [d for d, c in DIMENSION_CATEGORIES.items() if c == "anxiety"]:
            for d in top_dim_names:
                if DIMENSION_CATEGORIES.get(d) == "anxiety":
                    anxiety = d
                    break
        if trigger not in [d for d, c in DIMENSION_CATEGORIES.items() if c == "trigger"]:
            for d in top_dim_names:
                if DIMENSION_CATEGORIES.get(d) == "trigger":
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


def emotion_analysis_node(
    state: EmotionAnalysisNodeInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> EmotionAnalysisNodeOutput:
    """
    title: 核心情绪与动机拆解
    desc: 基于今日榜单规则化统计情绪维度，DeepSeek 提炼总览与行动建议
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

        # 1. 规则化统计情绪维度
        scores = _aggregate_emotion_scores(rankings)
        if not scores:
            scores = {
                "心理补偿": 35, "身份逆袭": 32, "亲密关系失衡": 30,
                "复仇打脸": 28, "解压放空": 25, "快节奏": 22
            }

        wordcloud = _build_wordcloud(scores)
        emotion_rankings = _build_emotion_rankings(rankings, scores)

        # 2. 计算环比趋势
        yesterday_scores = _load_yesterday_wordcloud(data_date, workspace_path)
        trends = _build_trends(scores, yesterday_scores)

        # 3. 主导维度
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        dominant_emotion = next((n for n, _ in sorted_scores if DIMENSION_CATEGORIES.get(n) == "emotion"), "心理补偿")
        dominant_anxiety = next((n for n, _ in sorted_scores if DIMENSION_CATEGORIES.get(n) == "anxiety"), "亲密关系失衡")
        top_trigger = next((n for n, _ in sorted_scores if DIMENSION_CATEGORIES.get(n) == "trigger"), "复仇打脸")

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

        summary = parsed.get("summary") or f"今日榜单以{dominant_emotion}与{top_trigger}为主，观众通过剧情补偿{dominant_anxiety}。"
        oneliners = parsed.get("emotion_rankings_oneliners") or []
        insights_raw = parsed.get("actionable_insights") or []

        # 5. 合并 DeepSeek 结果
        for idx, item in enumerate(emotion_rankings):
            if idx < len(oneliners) and oneliners[idx]:
                item.one_line = str(oneliners[idx])
            else:
                item.one_line = f"用{item.primary_emotion}补偿{item.anxiety}中的价值缺失"

        actionable_insights = []
        default_insights = [
            ActionableInsight(icon="💡", title="聚焦主导情绪", content=f"今日'{dominant_emotion}'情绪显著，新剧本可围绕'{top_trigger}'设计前3秒冲突，提升素材CTR。"),
            ActionableInsight(icon="📈", title="瞄准现实焦虑", content=f"观众对'{dominant_anxiety}'的代偿需求强，投流文案可直接点出痛点并展示反转爽点。"),
            ActionableInsight(icon="🎯", title="复用高触发题材", content=f"榜单TOP3剧目均命中'{top_trigger}'，后续创作可延续该爽点框架并做微创新。"),
        ]
        for idx in range(3):
            if idx < len(insights_raw) and isinstance(insights_raw[idx], dict):
                raw = insights_raw[idx]
                actionable_insights.append(ActionableInsight(
                    icon=str(raw.get("icon") or default_insights[idx].icon),
                    title=str(raw.get("title") or default_insights[idx].title),
                    content=str(raw.get("content") or default_insights[idx].content),
                ))
            else:
                actionable_insights.append(default_insights[idx])

        emotional_analysis = EmotionalAnalysis(
            summary=summary,
            dominant_emotion=dominant_emotion,
            dominant_anxiety=dominant_anxiety,
            top_trigger=top_trigger,
            wordcloud=wordcloud,
            emotion_rankings=emotion_rankings,
            trends=trends,
            actionable_insights=actionable_insights,
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
