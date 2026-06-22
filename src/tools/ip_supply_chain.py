"""
IP 供应链工具
1. 从红果详情页提取"改编自"信息
2. 尝试爬番茄小说榜单（备用）
3. 短剧标题 ↔ 原著标题 模糊匹配
"""
import re
import json
import logging
from typing import Dict, List, Any, Optional

import httpx

logger = logging.getLogger(__name__)

# 模块级缓存：一个进程内只拉取一次番茄榜单，避免 push_node 为每部剧重复请求
_FANQIE_RANK_CACHE: Optional[List[Dict[str, Any]]] = None
_FANQIE_TITLE_CACHE: Dict[str, Dict[str, Optional[str]]] = {}

_FANQIE_RANK_URL = "https://fanqienovel.com/rank"
_FANQIE_PAGE_URL = "https://fanqienovel.com/page/{book_id}"
_FANQIE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _parse_initial_state(html: str) -> Optional[Dict[str, Any]]:
    """从页面 HTML 中提取 window.__INITIAL_STATE__ JSON。"""
    start = html.find("window.__INITIAL_STATE__=")
    if start < 0:
        return None
    start += len("window.__INITIAL_STATE__=")

    # SSR 中该 JSON 以多个可能的标记结尾，依次尝试
    for marker in (";\n            }\n        )()", ";\n        })()", ";</script>"):
        end = html.find(marker, start)
        if end >= 0:
            break
    else:
        return None

    try:
        return json.loads(html[start:end])
    except json.JSONDecodeError:
        return None


def _extract_book_meta_from_detail(html: str) -> Dict[str, Optional[str]]:
    """
    从书籍详情页提取真实书名与作者。
    排行榜 JSON 中的书名/作者被自定义字体混淆为 PUA 字符，详情页 meta 信息为明文。
    """
    result: Dict[str, Optional[str]] = {"title": None, "author": None}

    # 从 <title> 提取书名："惹金枝完整版在线免费阅读_惹金枝小说_番茄小说官网"
    m = re.search(r"<title>([^<]+)</title>", html)
    if m:
        title = m.group(1).strip()
        clean = re.split(r"(?:完整版|在线免费|免费阅读|小说|_)", title)[0]
        result["title"] = clean.strip() or None

    # 从 keywords meta 提取作者："攀高枝,攀高枝免费阅读,...,白鹭成双小说攀高枝,..."
    km = re.search(
        r'<meta[^>]+name=["\']keywords["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )
    if not km:
        km = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']keywords["\']',
            html,
        )
    if km:
        keywords = km.group(1)
        # 匹配 "作者名小说书名"
        title = result["title"] or ""
        am = re.search(rf"([\u4e00-\u9fa5]+)小说{re.escape(title)}", keywords)
        if am:
            result["author"] = am.group(1).strip()

    return result


def _fetch_book_meta(book_id: str) -> Dict[str, Optional[str]]:
    """获取单本书的真实标题与作者，带缓存。"""
    if book_id in _FANQIE_TITLE_CACHE:
        return _FANQIE_TITLE_CACHE[book_id]

    try:
        with httpx.Client(timeout=10, headers=_FANQIE_HEADERS, follow_redirects=True) as client:
            resp = client.get(_FANQIE_PAGE_URL.format(book_id=book_id))
            resp.raise_for_status()
            meta = _extract_book_meta_from_detail(resp.text)
    except Exception as exc:
        logger.debug("番茄小说详情页获取失败 book_id=%s: %s", book_id, exc)
        meta = {"title": None, "author": None}

    _FANQIE_TITLE_CACHE[book_id] = meta
    return meta


def fetch_fanqienovel_data(max_count: int = 30) -> List[Dict[str, Any]]:
    """
    尝试爬取番茄小说热榜。如果失败，返回空列表，不抛异常。
    使用 /rank 页面（返回 200 且 SSR 注入榜单数据），而非已 404 的 /page/top。
    """
    global _FANQIE_RANK_CACHE
    if _FANQIE_RANK_CACHE is not None:
        return _FANQIE_RANK_CACHE[:max_count]

    try:
        with httpx.Client(timeout=15, headers=_FANQIE_HEADERS, follow_redirects=True) as client:
            resp = client.get(_FANQIE_RANK_URL)
            resp.raise_for_status()
            html = resp.text

        state = _parse_initial_state(html)
        if not state:
            logger.warning("番茄小说榜单页未找到 __INITIAL_STATE__，返回空列表")
            _FANQIE_RANK_CACHE = []
            return []

        book_list = state.get("rank", {}).get("book_list") or []
        if not book_list:
            logger.warning("番茄小说榜单页 book_list 为空，返回空列表")
            _FANQIE_RANK_CACHE = []
            return []

        novels: List[Dict[str, Any]] = []
        for book in book_list[:max_count]:
            book_id = book.get("bookId")
            # 排行榜 JSON 中的 bookName/author 被自定义字体混淆，取详情页真实元数据
            raw_title = book.get("bookName", "")
            raw_author = book.get("author", "")
            meta = _fetch_book_meta(book_id) if book_id else {"title": None, "author": None}
            novels.append(
                {
                    "title": meta.get("title") or raw_title,
                    "author": meta.get("author") or raw_author,
                    "book_id": book_id,
                    "raw_title": raw_title,
                }
            )

        _FANQIE_RANK_CACHE = novels
        logger.info("番茄小说榜单获取成功，共 %d 本", len(novels))
        return novels[:max_count]
    except Exception as e:
        logger.warning("番茄小说爬取失败: %s，返回空列表", e)
        _FANQIE_RANK_CACHE = []
        return []


def extract_adaptation_from_html(html: str) -> Optional[Dict[str, str]]:
    """
    从红果详情页 HTML 提取"改编自"信息
    返回: {"source_title": "原著书名", "author": "作者", "platform": "番茄小说"}
    """
    if not html:
        return None

    patterns = [
        r'改编自[番茄小说]*[《"](.+?)[》"]',
        r'原著[：:]\s*番茄小说[《"](.+?)[》"]',
        r'IP[来源]*[：:]\s*[《"](.+?)[》"]',
        r'改编自.*?《(.+?)》',
    ]

    for p in patterns:
        m = re.search(p, html)
        if m:
            source_title = m.group(1).strip()
            if source_title:
                return {
                    "source_title": source_title,
                    "author": "",
                    "platform": "番茄小说"
                }

    return None


def jaccard_similarity(title1: str, title2: str) -> float:
    """计算两个标题的 Jaccard 相似度"""
    set1 = set(title1)
    set2 = set(title2)
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def match_drama_to_novel(drama_title: str, novels: List[Dict]) -> Optional[Dict]:
    """
    用模糊匹配找短剧对应的原著小说
    """
    if not novels:
        return None

    best_match = None
    best_score = 0.0

    for novel in novels:
        novel_title = novel.get("title", "")
        if not novel_title:
            continue

        score = jaccard_similarity(drama_title, novel_title)
        # 如果标题包含关系，额外加分
        if novel_title in drama_title or drama_title in novel_title:
            score += 0.2

        if score > best_score and score > 0.5:
            best_score = score
            best_match = novel

    return best_match


def build_supply_chain(drama_title: str, series_id: str, fetch_detail_func) -> Dict[str, Any]:
    """
    构建单部剧的供应链信息
    fetch_detail_func: 传入一个函数，用于获取红果详情页 HTML
    """
    result = {
        "has_ip_source": False,
        "source_title": "",
        "source_author": "",
        "source_platform": "",
        "match_confidence": 0.0
    }

    # 1. 尝试从红果详情页提取
    try:
        html = fetch_detail_func(series_id)
        adaptation = extract_adaptation_from_html(html)
        if adaptation:
            result.update({
                "has_ip_source": True,
                "source_title": adaptation["source_title"],
                "source_author": adaptation["author"],
                "source_platform": adaptation["platform"],
                "match_confidence": 1.0
            })
            return result
    except Exception:
        pass

    # 2. 如果提取失败，尝试番茄小说榜单模糊匹配
    novels = fetch_fanqienovel_data(20)
    matched = match_drama_to_novel(drama_title, novels)
    if matched and matched.get("title"):
        result.update({
            "has_ip_source": True,
            "source_title": matched.get("title", ""),
            "source_author": matched.get("author", ""),
            "source_platform": "番茄小说",
            "match_confidence": 0.7
        })

    return result
