"""
近一周热门标签节点 - 基于近7天榜单数据聚合标签热度

优化点：
1. 从"仅统计今日"升级为"近7天加权聚合"，时间越近权重越高。
2. 引入本地标签 taxonomy，将标签按题材/人设/爽点/情感/时代等维度分类展示。
3. 计算标签环比趋势（今日 vs 昨日），突出上升/新晋标签。
4. 不依赖外网爬虫，完全基于本地已有时效榜单数据，避免过期内容。
"""
import json
import logging
import os
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import (
    GenreDistribution,
    GenreDistributionInput,
    GenreDistributionOutput,
    GenderTagSplit,
    TagItem,
    TagCategory,
    TrendingTag,
)
from tools.tag_normalizer import canonicalize_tag, normalize_tags

logger = logging.getLogger(__name__)

GENERIC_LABELS = {
    "",
    "其他",
    "其它",
    "未知",
    "未标注",
    "待补充",
    "暂无",
    "无",
    "N/A",
    "n/a",
    "NA",
    "null",
    "None",
}
LABEL_SEPARATORS = ("、", "，", ",", "/", "|", "｜", "；", ";", "\n")

# 本地标签分类体系（按优先级排序，一个标签只归入最先命中的类别）
TAG_TAXONOMY: List[Tuple[str, List[str]]] = [
    (
        "爽点",
        [
            "打脸", "虐渣", "复仇", "逆袭", "马甲", "掉马", "火葬场", "追妻", "追夫",
            "带球跑", "萌宝", "身份揭晓", "实力碾压", "扮猪吃虎", "翻身", "上位", "夺回",
            "复仇打脸", "逆袭打脸",
        ],
    ),
    (
        "题材",
        [
            "都市", "古装", "穿越", "重生", "年代", "民国", "职场", "校园", "悬疑",
            "玄幻", "奇幻", "仙侠", "科幻", "武侠", "历史", "宫廷", "权谋", "商战",
            "医疗", "军旅", "家庭", "农村", "甜宠", "虐恋", "都市爱情", "古风爱情",
        ],
    ),
    (
        "情感关系",
        [
            "甜宠", "虐恋", "先婚后爱", "先婚厚爱", "闪婚", "离婚", "复婚", "替身", "暗恋",
            "双向奔赴", "强取豪夺", "契约婚姻", "豪门恩怨", "日久生情", "破镜重圆",
            "青梅竹马", "契约", "追爱", "错嫁", "替嫁", "禁欲", "高甜", "高虐",
        ],
    ),
    (
        "人设",
        [
            "总裁", "霸总", "千金", "嫡女", "庶女", "王妃", "皇后", "贵妃", "公主",
            "小娇妻", "大叔", "弟弟", "保镖", "秘书", "医生", "律师", "战神", "神医",
            "厨神", "学霸", "学渣", "千金小姐", "灰姑娘", "替身", "前妻", "前夫",
            "继女", "养女", "真千金", "假千金", "白月光", "朱砂痣", "青梅竹马",
            "赘婿", "奶爸", "保镖", "特工", "重生女", "重生男", "穿越女", "穿越男",
            "嫡长子", "庶子", "王爷", "太子", "皇子", "世子", "将军", "谋士",
        ],
    ),
    (
        "时代背景",
        [
            "现代", "古代", "民国", "八零", "九零", "七零", "六零", "末世", "未来",
        ],
    ),
]


def _get_field(drama: Any, field_name: str, default: Any = None) -> Any:
    """兼容 Pydantic 对象和字典输入。"""
    if isinstance(drama, dict):
        return drama.get(field_name, default)
    return getattr(drama, field_name, default)


def _normalize_label(label: Any) -> str:
    if label is None:
        return ""
    return str(label).strip().strip("[]()（）【】「」\"' ")


def _split_label_text(text: str) -> Iterable[str]:
    parts = [text]
    for separator in LABEL_SEPARATORS:
        next_parts: List[str] = []
        for part in parts:
            next_parts.extend(part.split(separator))
        parts = next_parts

    for part in parts:
        label = _normalize_label(part)
        if label and label not in GENERIC_LABELS:
            yield label


def _iter_labels(value: Any) -> Iterable[str]:
    if value is None:
        return

    if isinstance(value, str):
        yield from _split_label_text(value)
        return

    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_labels(item)
        return

    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            yield from _iter_labels(item)
        return

    label = _normalize_label(value)
    if label and label not in GENERIC_LABELS:
        yield label


def _collect_drama_labels(drama: Any) -> List[str]:
    labels: List[str] = []
    for field_name in ("genre", "tags", "core_trope"):
        labels.extend(_iter_labels(_get_field(drama, field_name, [])))
    return normalize_tags(labels)


def _drama_gender_bucket(drama: Any) -> str:
    category = str(_get_field(drama, "category", "female") or "female").lower()
    if category in {"male", "ai"}:
        return "male"
    return "female"


def _classify_tag(tag: str) -> str:
    """按本地 taxonomy 给标签分类，未命中返回'其他'。"""
    canonical = canonicalize_tag(tag)
    text = str(canonical).lower()
    for category, keywords in TAG_TAXONOMY:
        for kw in keywords:
            if kw.lower() == text or kw.lower() in text:
                return category
    return "其他"


def _load_history_rankings(
    data_date: str, workspace_path: str, lookback_days: int = 7
) -> List[Tuple[str, int, List[Any]]]:
    """
    加载近 lookback_days 天的历史榜单（不含今天）。
    返回 [(date_str, offset_days, rankings_list), ...]，offset=1 表示昨天。
    """
    results: List[Tuple[str, int, List[Any]]] = []
    if not data_date:
        return results

    try:
        base_date = datetime.strptime(data_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return results

    workspace = Path(workspace_path or os.getenv("COZE_WORKSPACE_PATH") or Path(__file__).resolve().parents[2])
    history_dir = workspace / "assets" / "data" / "history"
    if not history_dir.exists():
        return results

    for offset in range(1, lookback_days + 1):
        file_date = base_date - timedelta(days=offset)
        file_path = history_dir / f"{file_date.strftime('%Y-%m-%d')}.json"
        if not file_path.exists():
            continue
        try:
            with file_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            rankings = payload.get("rankings") or payload.get("enriched_rankings") or []
            if rankings:
                results.append((file_date.strftime("%Y-%m-%d"), offset, rankings))
        except (OSError, json.JSONDecodeError):
            continue

    return results


def _rankings_to_label_counter(rankings: Iterable[Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for drama in rankings:
        counter.update(_collect_drama_labels(drama))
    return counter


def genre_distribution_node(
    state: GenreDistributionInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> GenreDistributionOutput:
    """
    title: 🏷️ 统计近一周热门标签
    desc: 基于近7天榜单数据加权聚合标签频次，并分类/趋势展示
    integrations: 无
    """
    try:
        rankings = state.enriched_rankings if state.enriched_rankings else []
        input_error_message = ""
        if not rankings:
            input_error_message = "genre_distribution_node: enriched_rankings 为空，热门标签无法统计；请检查 enrich_node。\n"
            logger.error(input_error_message.strip())

        logger.info("热门标签节点输入: 榜单数=%s", len(rankings))

        # 今日标签
        today_counter = _rankings_to_label_counter(rankings)
        total_views = sum(int(_get_field(d, "views_num", 0) or 0) for d in rankings)

        # 近7天历史（含权重：昨天6 -> 7天前1）
        workspace_path = os.getenv("COZE_WORKSPACE_PATH", "")
        history = _load_history_rankings(state.data_date, workspace_path, lookback_days=7)

        weighted_counter: Counter[str] = Counter()
        # 今日权重最高（7）
        for tag, count in today_counter.items():
            weighted_counter[tag] += count * 7

        for _date_str, offset, hist_rankings in history:
            weight = max(7 - offset, 1)
            for tag, count in _rankings_to_label_counter(hist_rankings).items():
                weighted_counter[tag] += count * weight

        # 热门标签 TOP20（全局加权热度，用于总览与趋势）
        sorted_weighted = sorted(weighted_counter.items(), key=lambda item: (-item[1], item[0]))
        top_tags = sorted_weighted[:20]
        hot_tags = [TagItem(name=name, value=int(count)) for name, count in top_tags]

        # 按类别聚合：每个维度独立取 TOP N，避免“全局 TOP20”把某些人/情感标签挤出
        category_groups: Dict[str, List[TagItem]] = {}
        for name, count in weighted_counter.items():
            category = _classify_tag(name)
            category_groups.setdefault(category, []).append(TagItem(name=name, value=int(count)))

        # 各类别展示数量：保证每个核心维度都有足够标签，减少空白
        CATEGORY_TOP_N: Dict[str, int] = {
            "题材": 8,
            "爽点": 6,
            "人设": 6,
            "情感关系": 5,
            "时代背景": 4,
            "其他": 4,
        }
        # 固定展示顺序，符合用户从“题材→爽点→人设→情感→时代”的认知路径
        CATEGORY_ORDER = ["题材", "爽点", "人设", "情感关系", "时代背景", "其他"]

        categories: List[TagCategory] = []
        for category in CATEGORY_ORDER:
            tags = category_groups.get(category, [])
            if not tags:
                continue
            top_n = CATEGORY_TOP_N.get(category, 5)
            sorted_tags = sorted(tags, key=lambda t: (-t.value, t.name))[:top_n]
            categories.append(TagCategory(category=category, tags=sorted_tags))

        # 趋势：今日 vs 昨日
        yesterday_counter = next(
            (_rankings_to_label_counter(hist_rankings) for _d, offset, hist_rankings in history if offset == 1),
            Counter(),
        )
        trending: List[TrendingTag] = []
        for name, today_count in sorted(today_counter.items(), key=lambda item: -item[1])[:15]:
            yesterday_count = yesterday_counter.get(name, 0)
            change = today_count - yesterday_count
            if yesterday_count == 0 and today_count > 0:
                trend = "new"
            elif change > 0:
                trend = "up"
            elif change < 0:
                trend = "down"
            else:
                trend = "same"
            trending.append(TrendingTag(name=name, value=today_count, change=change, trend=trend))

        trending = sorted(trending, key=lambda t: (-abs(t.change), -t.value))[:6]

        # 男女频标签分列（基于当日榜单）
        female_counter: Counter[str] = Counter()
        male_counter: Counter[str] = Counter()
        for drama in rankings:
            labels = _collect_drama_labels(drama)
            bucket = _drama_gender_bucket(drama)
            target = male_counter if bucket == "male" else female_counter
            target.update(labels)
        by_gender = GenderTagSplit(
            female=[
                TagItem(name=name, value=int(count))
                for name, count in female_counter.most_common(8)
            ],
            male=[
                TagItem(name=name, value=int(count))
                for name, count in male_counter.most_common(8)
            ],
        )

        genre_distribution = GenreDistribution(
            hot_tags=hot_tags,
            categories=categories,
            trending=trending,
            by_gender=by_gender,
            data_source="近7天榜单统计",
            update_frequency="weekly",
        )

        logger.info(
            "热门标签统计完成: 榜单数=%s, 标签数=%s, 类别数=%s, 趋势标签数=%s",
            len(rankings),
            len(hot_tags),
            len(categories),
            len(trending),
        )

        return GenreDistributionOutput(
            genre_distribution=genre_distribution,
            total_count=len(rankings),
            total_views=total_views,
            error_message=input_error_message,
        )

    except Exception as e:
        error_message = f"genre_distribution_node: 统计热门标签失败: {e}"
        logger.error(error_message, exc_info=True)
        return GenreDistributionOutput(
            genre_distribution=GenreDistribution(
                data_source="近7天榜单统计失败",
                update_frequency="weekly",
            ),
            total_count=0,
            total_views=0,
            error_message=error_message + "\n",
        )
