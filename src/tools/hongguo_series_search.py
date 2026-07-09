"""
红果 series_id 解析：剧名精确匹配 + Kimi 搜索 novelquickapp 链接。
周榜剧目通常不在首页推荐 catalog，需按剧名搜索而非模糊匹配推荐列表。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from utils.title_matcher import normalize_title_for_match, title_match_score

logger = logging.getLogger(__name__)

_SERIES_ID_RE = re.compile(
    r"(?:series_id[=:]\s*|detail\?series_id=)(\d{16,20})",
    re.I,
)

# 剧名搜索时允许的最低相似度（高于推荐 catalog 回填阈值，但仍低于 0.82）
_SEARCH_MIN_SCORE = 0.92


def extract_series_id_from_text(text: str) -> str:
    """从搜索/API 文本中提取红果 series_id。"""
    if not text:
        return ""
    match = _SERIES_ID_RE.search(text)
    return match.group(1) if match else ""


def resolve_series_id_from_catalog(
    title: str,
    catalog: List[Dict[str, Any]],
    *,
    min_score: float = _SEARCH_MIN_SCORE,
) -> str:
    """在红果 catalog 中按剧名搜索 series_id（精确/高相似优先）。"""
    if not title or not catalog:
        return ""

    normalized_query = normalize_title_for_match(title)
    if not normalized_query:
        return ""

    best_id = ""
    best_score = 0.0
    best_title = ""

    for item in catalog:
        candidate_title = item.get("title", "") or ""
        if not candidate_title:
            continue
        if normalize_title_for_match(candidate_title) == normalized_query:
            sid = str(item.get("series_id", "") or "")
            if sid:
                logger.info("红果剧名精确命中: %s -> %s", title, sid)
                return sid
        score = title_match_score(title, candidate_title)
        if score > best_score:
            best_score = score
            best_id = str(item.get("series_id", "") or "")
            best_title = candidate_title

    if best_score >= min_score and best_id:
        logger.info(
            "红果剧名高相似命中: %s -> %s (score=%.2f, candidate=%s)",
            title,
            best_id,
            best_score,
            best_title,
        )
        return best_id
    return ""


def resolve_series_id_via_search(
    title: str,
    searcher: Callable[[str], str],
) -> str:
    """通过 Kimi 联网搜索红果详情页链接获取 series_id。"""
    if not title or not searcher:
        return ""

    queries = (
        f"红果短剧《{title}》 novelquickapp.com detail series_id",
        f"《{title}》短剧 红果 详情页 链接",
    )
    for query in queries:
        try:
            result = searcher(query)
            series_id = extract_series_id_from_text(result)
            if series_id:
                logger.info("Kimi 搜索解析 series_id: %s -> %s", title, series_id)
                return series_id
        except Exception as exc:
            logger.warning("Kimi 搜索 series_id 失败 《%s》: %s", title, exc)
    return ""


def resolve_series_id(
    title: str,
    catalog: Optional[List[Dict[str, Any]]] = None,
    searcher: Optional[Callable[[str], str]] = None,
) -> str:
    """综合剧名 catalog 搜索 + Kimi 搜索解析 series_id。"""
    if catalog:
        sid = resolve_series_id_from_catalog(title, catalog)
        if sid:
            return sid
    if searcher:
        return resolve_series_id_via_search(title, searcher)
    return ""
