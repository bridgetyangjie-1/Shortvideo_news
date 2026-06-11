"""
题材分布节点 - 基于榜单数据动态聚合题材与标签热度
"""
import logging
from collections.abc import Iterable
from collections import defaultdict
from typing import Any, Dict, List, Set

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import (
    GenreDistributionInput,
    GenreDistributionOutput,
    GenreDistribution,
    GenreStat,
    GenreStats,
    TagHeat,
)

logger = logging.getLogger(__name__)

HEAT_VIEW_WEIGHT = 0.01
GENERIC_LABELS = {"", "其他", "其它", "未知", "未标注", "待补充", "暂无", "无", "N/A", "n/a", "NA", "null", "None"}
LABEL_SEPARATORS = ("、", "，", ",", "/", "|", "｜", "；", ";", "\n")


def _get_field(drama: Any, field_name: str, default: Any = None) -> Any:
    """兼容 Pydantic 对象和少量字典输入，避免对 Pydantic 对象调用 get。"""
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

    if isinstance(value, Iterable):
        for item in value:
            yield from _iter_labels(item)
        return

    label = _normalize_label(value)
    if label and label not in GENERIC_LABELS:
        yield label


def _resolve_genre(drama: Any) -> str:
    """优先使用真实 genre；为空或泛化时再从动态标签中兜底推断。"""
    for genre in _iter_labels(_get_field(drama, "genre", "")):
        return genre

    for fallback_field in ("tags", "core_trope"):
        for label in _iter_labels(_get_field(drama, fallback_field, [])):
            return label

    return "未标注"


def _resolve_trend(trends: List[str]) -> str:
    up_count = trends.count("up")
    down_count = trends.count("down")

    if up_count > down_count and up_count > len(trends) / 2:
        return "up"
    if down_count > up_count and down_count > len(trends) / 2:
        return "down"
    return "same"


def _calculate_heat(count: int, views: int) -> int:
    if count <= 0:
        return 0
    avg_views = views / count
    return int(round(count * 10 + avg_views * HEAT_VIEW_WEIGHT))


def _build_tag_heat(tag_name: str, category: str, stats: Dict[str, int]) -> TagHeat:
    count = stats["count"]
    views = stats["views"]
    avg_views = int(round(views / count)) if count else 0
    return TagHeat(
        name=tag_name,
        category=category,
        count=count,
        avg_views=avg_views,
        heat=_calculate_heat(count, views),
    )


def _sort_tag_heat(tags: List[TagHeat]) -> List[TagHeat]:
    return sorted(tags, key=lambda tag: (tag.heat, tag.count, tag.avg_views), reverse=True)


def genre_distribution_node(
    state: GenreDistributionInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> GenreDistributionOutput:
    """
    title: 📊 统计题材分布与标签热度
    desc: 基于 enriched_rankings 自下而上动态聚合题材、标签和核心爽点热度
    integrations: 无
    """
    try:
        rankings = state.enriched_rankings if state.enriched_rankings else []
        input_error_message = ""
        if not rankings:
            input_error_message = "genre_distribution_node: enriched_rankings 为空，题材分布无法统计；请检查 enrich_node。\n"
            logger.error(input_error_message.strip())

        logger.info("题材分布节点输入: 榜单数=%s", len(rankings))

        genre_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "views": 0,
                "trends": [],
                "ai_count": 0,
                "female_count": 0,
                "male_count": 0,
            }
        )
        tag_stats_by_category: Dict[str, Dict[str, Dict[str, int]]] = {
            "背景": defaultdict(lambda: {"count": 0, "views": 0}),
            "主题": defaultdict(lambda: {"count": 0, "views": 0}),
            "设定": defaultdict(lambda: {"count": 0, "views": 0}),
        }

        total_views = 0

        for drama in rankings:
            views = int(_get_field(drama, "views_num", 0) or 0)
            trend = _get_field(drama, "trend_type", "same") or "same"
            is_ai = bool(_get_field(drama, "is_ai", False))
            category = _get_field(drama, "category", "female") or "female"
            genre = _resolve_genre(drama)

            genre_stats[genre]["count"] += 1
            genre_stats[genre]["views"] += views
            genre_stats[genre]["trends"].append(trend)

            if is_ai:
                genre_stats[genre]["ai_count"] += 1
            if category == "female":
                genre_stats[genre]["female_count"] += 1
            elif category == "male":
                genre_stats[genre]["male_count"] += 1

            total_views += views

            # 每部剧内先去重，保证同一个标签在同一部剧中只贡献一次 count。
            theme_labels: Set[str] = set(_iter_labels(_get_field(drama, "genre", "")))
            theme_labels.update(_iter_labels(_get_field(drama, "tags", [])))
            setting_labels: Set[str] = set(_iter_labels(_get_field(drama, "core_trope", [])))

            for label in theme_labels - setting_labels:
                tag_stats_by_category["主题"][label]["count"] += 1
                tag_stats_by_category["主题"][label]["views"] += views

            for label in setting_labels:
                tag_stats_by_category["设定"][label]["count"] += 1
                tag_stats_by_category["设定"][label]["views"] += views

        result_genres: List[GenreStat] = []
        for genre_name, stats in genre_stats.items():
            share = round(stats["views"] / total_views * 100, 1) if total_views > 0 else 0
            result_genres.append(
                GenreStat(
                    name=genre_name,
                    count=stats["count"],
                    views=stats["views"],
                    share=share,
                    trend=_resolve_trend(stats["trends"]),
                    ai_count=stats["ai_count"],
                    female_count=stats["female_count"],
                    male_count=stats["male_count"],
                )
            )

        result_genres.sort(key=lambda genre: (genre.views, genre.count), reverse=True)

        background_tags = _sort_tag_heat(
            [
                _build_tag_heat(tag_name, "背景", stats)
                for tag_name, stats in tag_stats_by_category["背景"].items()
                if stats["count"] > 0
            ]
        )
        theme_tags = _sort_tag_heat(
            [
                _build_tag_heat(tag_name, "主题", stats)
                for tag_name, stats in tag_stats_by_category["主题"].items()
                if stats["count"] > 0
            ]
        )
        setting_tags = _sort_tag_heat(
            [
                _build_tag_heat(tag_name, "设定", stats)
                for tag_name, stats in tag_stats_by_category["设定"].items()
                if stats["count"] > 0
            ]
        )

        all_tags = _sort_tag_heat(background_tags + theme_tags + setting_tags)
        top_tag = all_tags[0].name if all_tags else ""
        rising_tag = all_tags[1].name if len(all_tags) > 1 else ""
        rising_genre = next((genre.name for genre in result_genres if genre.trend == "up"), "")
        if not rising_genre and len(result_genres) > 1:
            rising_genre = result_genres[1].name

        logger.info(
            "题材分布统计完成: %s个题材, %s个背景标签, %s个主题标签, %s个设定标签",
            len(result_genres),
            len(background_tags),
            len(theme_tags),
            len(setting_tags),
        )

        genre_distribution = GenreDistribution(
            genres=[
                GenreStats(name=genre.name, count=genre.count, total_views=str(genre.views), trend=genre.trend)
                for genre in result_genres[:10]
            ],
            top_genre=result_genres[0].name if result_genres else "",
            rising_genre=rising_genre,
            background_tags=background_tags[:10],
            theme_tags=theme_tags[:10],
            setting_tags=setting_tags[:10],
            top_tag=top_tag,
            rising_tag=rising_tag,
        )

        return GenreDistributionOutput(
            genre_distribution=genre_distribution,
            total_count=len(rankings),
            total_views=total_views,
            error_message=input_error_message,
        )

    except Exception as e:
        error_message = f"genre_distribution_node: 统计题材分布失败: {e}"
        logger.error(error_message, exc_info=True)
        return GenreDistributionOutput(
            genre_distribution=GenreDistribution(),
            total_count=0,
            total_views=0,
            error_message=error_message + "\n",
        )
