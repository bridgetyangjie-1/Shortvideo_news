"""
剧名模糊匹配工具：用于短剧工程周榜与红果推荐页标题对齐。
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, Optional, Tuple

# 匹配前剥离的噪声后缀
_TITLE_NOISE_SUFFIXES = (
    "新上架", "上架", "第一季", "第二季", "第三季", "完整版", "短剧版", "正版",
)
_TRAILING_SEASON_RE = re.compile(r"([：:])?第?[一二三四五六七八九十\d]+季?$")
_TRAILING_NUMERIC_RE = re.compile(r"([：:])?\d+$")


def normalize_title_for_match(title: str) -> str:
    """剧名归一化：去标点/空白/常见后缀，便于跨源匹配。"""
    if not title:
        return ""
    text = unicodedata.normalize("NFKC", str(title)).strip().lower()
    for ch in ("《", "》", "「", "」", "【", "】", "'", '"', "·", "•", " ", "　"):
        text = text.replace(ch, "")
    for ch in (":", "：", "!", "！", "?", "？", "-", "—", "_", "/", "|"):
        text = text.replace(ch, "")
    for suffix in _TITLE_NOISE_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    text = _TRAILING_SEASON_RE.sub("", text)
    text = _TRAILING_NUMERIC_RE.sub("", text)
    return text.strip()


def title_match_score(left: str, right: str) -> float:
    """计算两个剧名的相似度 [0, 1]。"""
    a = normalize_title_for_match(left)
    b = normalize_title_for_match(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        return max(0.88, len(shorter) / max(len(longer), 1))
    return SequenceMatcher(None, a, b).ratio()


def find_best_title_match(
    query_title: str,
    candidates: Iterable[Tuple[str, Dict[str, Any]]],
    *,
    min_score: float = 0.82,
) -> Optional[Dict[str, Any]]:
    """
    在候选列表中为 query_title 找到最佳匹配元数据。

    Args:
        query_title: 待匹配的剧名
        candidates: (原始标题, 元数据字典) 可迭代对象
        min_score: 最低相似度阈值
    """
    best_item: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for candidate_title, payload in candidates:
        score = title_match_score(query_title, candidate_title)
        if score > best_score:
            best_score = score
            best_item = payload
    if best_score >= min_score:
        return best_item
    return None


def build_title_metadata_indexes(
    items: Iterable[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], list[Tuple[str, Dict[str, Any]]]]:
    """
    构建精确索引、归一化索引与模糊匹配候选列表。

    Returns:
        (exact_index, normalized_index, fuzzy_candidates)
    """
    exact_index: Dict[str, Dict[str, Any]] = {}
    normalized_index: Dict[str, Dict[str, Any]] = {}
    fuzzy_candidates: list[Tuple[str, Dict[str, Any]]] = []

    for item in items:
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        exact_index[title] = item
        exact_index[title.replace(" ", "")] = item
        norm = normalize_title_for_match(title)
        if norm and norm not in normalized_index:
            normalized_index[norm] = item
        fuzzy_candidates.append((title, item))

    return exact_index, normalized_index, fuzzy_candidates


def lookup_hongguo_metadata(
    title: str,
    exact_index: Dict[str, Dict[str, Any]],
    normalized_index: Dict[str, Dict[str, Any]],
    fuzzy_candidates: list[Tuple[str, Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """精确 → 归一化 → 子串 → 模糊相似度 四级匹配。"""
    if not title:
        return None

    meta = exact_index.get(title) or exact_index.get(title.replace(" ", ""))
    if meta:
        return meta

    norm = normalize_title_for_match(title)
    if norm and norm in normalized_index:
        return normalized_index[norm]

    if norm:
        for key, item in normalized_index.items():
            if not key:
                continue
            if norm in key or key in norm:
                return item

    return find_best_title_match(title, fuzzy_candidates)
