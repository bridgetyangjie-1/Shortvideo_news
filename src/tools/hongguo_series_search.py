"""
红果 series_id 解析：剧名精确匹配 + Kimi 批量搜索 novelquickapp 链接。
周榜剧目通常不在首页推荐 catalog，需按剧名搜索而非模糊匹配推荐列表。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from utils.title_matcher import normalize_title_for_match, title_match_score

logger = logging.getLogger(__name__)

_SERIES_ID_RE = re.compile(
    r"(?:series_id[=:\"'\s]+|detail\?series_id=|/detail/|seriesId[=:\"'\s]+)(\d{16,20})",
    re.I,
)
# 兼容 hongguoduanju.com / novelquickapp.com 完整链接
_SERIES_URL_RE = re.compile(
    r"(?:novelquickapp\.com|hongguoduanju\.com)[^\"'\s<>]*series_id[=:](\d{16,20})",
    re.I,
)

# 剧名搜索时允许的最低相似度（周榜与推荐页标题差异大，0.88 兼顾召回）
_SEARCH_MIN_SCORE = 0.88

_ACTOR_LINE_RE = re.compile(
    r"(?:(?:女主|女主角|女主演|女演员)[:：]\s*([^\n,，；;]+))|"
    r"(?:(?:男主|男主角|男主演|男演员)[:：]\s*([^\n,，；;]+))",
    re.I,
)


def extract_series_id_from_text(text: str) -> str:
    """从搜索/API 文本中提取红果 series_id。"""
    if not text:
        return ""
    match = _SERIES_URL_RE.search(text) or _SERIES_ID_RE.search(text)
    return match.group(1) if match else ""


def extract_series_id_map_from_text(text: str, titles: List[str]) -> Dict[str, str]:
    """
    从批量 Kimi 搜索结果中按剧名块提取 series_id。
    优先匹配「剧名 + 链接」同一段落，否则在剧名附近窗口内查找。
    """
    if not text or not titles:
        return {}

    result: Dict[str, str] = {}
    normalized_blocks: List[tuple[str, str]] = []
    for block in re.split(r"\n\s*【", text):
        block = block.strip()
        if not block:
            continue
        normalized_blocks.append((block, f"【{block}" if not block.startswith("【") else block))

    for title in titles:
        if not title or title in result:
            continue
        title_norm = normalize_title_for_match(title)
        best_sid = ""
        for _, block in normalized_blocks:
            if title not in block and title_norm not in normalize_title_for_match(block):
                continue
            sid = extract_series_id_from_text(block)
            if sid:
                best_sid = sid
                break
        if not best_sid:
            # 在剧名出现位置前后 400 字符内查找链接
            for match in re.finditer(re.escape(title), text):
                window = text[max(0, match.start() - 80) : match.end() + 400]
                sid = extract_series_id_from_text(window)
                if sid:
                    best_sid = sid
                    break
        if best_sid:
            result[title] = best_sid
    return result


def _clean_actor_name(raw: str) -> str:
    text = (raw or "").strip()
    text = re.split(r"[,，、/;；|\s]{2,}", text)[0].strip()
    text = re.sub(r"[（(].*?[）)]", "", text).strip()
    invalid = {
        "", "未找到", "未知", "无", "暂无", "待定", "待补充", "n/a", "none",
        "不详", "查无", "未公布",
    }
    if text.lower() in invalid or text in invalid:
        return ""
    # 过长多半是整句说明，不可靠
    if len(text) > 12:
        return ""
    return text


def parse_actors_from_batch_text(text: str, titles: List[str]) -> Dict[str, Dict[str, str]]:
    """从批量演员搜索结果中解析每部剧的女主/男主。"""
    if not text or not titles:
        return {}

    result: Dict[str, Dict[str, str]] = {}
    blocks = re.split(r"(?=【[^】]+】)", text)
    for title in titles:
        female = ""
        male = ""
        for block in blocks:
            if title not in block:
                continue
            for match in _ACTOR_LINE_RE.finditer(block):
                if match.group(1) and not female:
                    female = _clean_actor_name(match.group(1))
                if match.group(2) and not male:
                    male = _clean_actor_name(match.group(2))
            if female or male:
                break
        if female or male:
            result[title] = {"female_lead": female, "male_lead": male}
    return result


def build_batch_series_id_query(titles: List[str]) -> str:
    """构造单次 Kimi 批量 series_id 搜索查询。"""
    lines = "\n".join(f"{idx}. 《{title}》" for idx, title in enumerate(titles[:20], 1))
    return (
        "请联网搜索以下红果短剧的官方详情页链接。\n"
        "优先查找 novelquickapp.com 或 hongguoduanju.com 的 detail?series_id= 数字链接。\n"
        "每部剧单独一段，必须包含完整 URL，格式：\n"
        "【剧名】\n链接: https://novelquickapp.com/detail?series_id=19位数字\n\n"
        "若某部剧搜不到链接，写【剧名】\n链接: 未找到\n\n"
        f"{lines}"
    )


def build_batch_actor_query(titles: List[str]) -> str:
    """构造单次 Kimi 批量演员搜索查询。"""
    lines = "\n".join(f"{idx}. 《{title}》" for idx, title in enumerate(titles[:20], 1))
    return (
        "请联网搜索以下短剧的主演信息（红果/DataEye/抖音垂类来源，不要编造影视明星）。\n"
        "每部剧单独一段，格式：\n"
        "【剧名】\n女主: xxx\n男主: xxx\n\n"
        "若查无真实主演，写「女主: 未找到」「男主: 未找到」，禁止用一线影视明星或编号假名凑数。\n\n"
        f"{lines}"
    )


def batch_resolve_series_ids_via_search(
    titles: List[str],
    searcher: Callable[[str], str],
) -> Dict[str, str]:
    """单次 Kimi 联网搜索批量解析 series_id。"""
    clean_titles = [t for t in titles if t]
    if not clean_titles or not searcher:
        return {}
    try:
        result = searcher(build_batch_series_id_query(clean_titles))
        mapping = extract_series_id_map_from_text(result, clean_titles)
        for title, sid in mapping.items():
            logger.info("Kimi 批量解析 series_id: %s -> %s", title, sid)
        return mapping
    except Exception as exc:
        logger.warning("Kimi 批量 series_id 搜索失败: %s", exc)
        return {}


def batch_resolve_actors_via_search(
    titles: List[str],
    searcher: Callable[[str], str],
) -> str:
    """单次 Kimi 联网搜索批量获取演员上下文文本。"""
    clean_titles = [t for t in titles if t]
    if not clean_titles or not searcher:
        return ""
    try:
        result = searcher(build_batch_actor_query(clean_titles))
        if result:
            logger.info("Kimi 批量演员搜索完成: %d 部", len(clean_titles))
        return result or ""
    except Exception as exc:
        logger.warning("Kimi 批量演员搜索失败: %s", exc)
        return ""


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
