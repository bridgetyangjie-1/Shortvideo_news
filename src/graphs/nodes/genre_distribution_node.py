"""
近一周热门标签节点 - 基于榜单数据本地统计标签频次
"""
import logging
from collections import Counter
from collections.abc import Iterable
from typing import Any, List

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import GenreDistribution, GenreDistributionInput, GenreDistributionOutput

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


def _collect_drama_labels(drama: Any) -> List[str]:
    labels: List[str] = []
    for field_name in ("genre", "tags", "core_trope"):
        labels.extend(_iter_labels(_get_field(drama, field_name, [])))
    return labels


def genre_distribution_node(
    state: GenreDistributionInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> GenreDistributionOutput:
    """
    title: 🏷️ 统计近一周热门标签
    desc: 基于 enriched_rankings 的 genre、tags、core_trope 本地统计标签绝对频次
    integrations: 无
    """
    try:
        rankings = state.enriched_rankings if state.enriched_rankings else []
        input_error_message = ""
        if not rankings:
            input_error_message = "genre_distribution_node: enriched_rankings 为空，热门标签无法统计；请检查 enrich_node。\n"
            logger.error(input_error_message.strip())

        logger.info("热门标签节点输入: 榜单数=%s", len(rankings))

        label_counter: Counter[str] = Counter()
        total_views = 0

        for drama in rankings:
            views = int(_get_field(drama, "views_num", 0) or 0)
            total_views += views
            label_counter.update(_collect_drama_labels(drama))

        hot_tags = [
            {"name": name, "value": int(count)}
            for name, count in sorted(label_counter.items(), key=lambda item: (-item[1], item[0]))[:15]
        ]

        logger.info(
            "热门标签统计完成: 榜单数=%s, 标签数=%s",
            len(rankings),
            len(hot_tags),
        )

        genre_distribution = GenreDistribution(hot_tags=hot_tags)

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
            genre_distribution=GenreDistribution(),
            total_count=0,
            total_views=0,
            error_message=error_message + "\n",
        )
