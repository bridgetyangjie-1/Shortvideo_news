"""
番茄小说官网爬虫
抓取首页本周推荐(editorList + weekList)数据。
"""
import gzip
import json
import logging
import re
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HOME_URL = "https://fanqienovel.com"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
}


def _fetch_html(url: str, timeout: int = 20) -> str:
    """获取页面 HTML"""
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        try:
            html = gzip.decompress(data).decode("utf-8", errors="ignore")
        except (OSError, gzip.BadGzipFile):
            html = data.decode("utf-8", errors="ignore")
    return html


def _extract_initial_state(html: str) -> Optional[Dict[str, Any]]:
    """从 HTML 中提取 window.__INITIAL_STATE__"""
    start_idx = html.find("window.__INITIAL_STATE__")
    if start_idx == -1:
        logger.error("未找到 window.__INITIAL_STATE__")
        return None

    script_start = html.find("=", start_idx) + 1
    json_str = html[script_start:].strip().lstrip("=").strip().rstrip(";")

    # 用括号匹配找到第一个完整 JSON 对象
    bracket_count = 0
    in_string = False
    escape = False
    start = 0
    for i, c in enumerate(json_str):
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"' and (i == 0 or json_str[i - 1] != "\\"):
            in_string = not in_string
            continue
        if not in_string:
            if c == "{":
                if bracket_count == 0:
                    start = i
                bracket_count += 1
            elif c == "}":
                bracket_count -= 1
                if bracket_count == 0:
                    json_str = json_str[start : i + 1]
                    break

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"解析 __INITIAL_STATE__ 失败: {e}")
        return None


def _format_cover_url(thumb_uri: str) -> str:
    """格式化封面 URL"""
    if not thumb_uri:
        return ""
    # 番茄封面 URL 中常有转义的斜杠
    thumb_uri = thumb_uri.replace("\\u002F", "/")
    if thumb_uri.startswith("http"):
        return thumb_uri
    return thumb_uri


def _parse_book_item(raw: Dict[str, Any], rank: int, source: str) -> Dict[str, Any]:
    """统一格式化单本书籍数据"""
    book_id = raw.get("bookId", "")
    return {
        "rank": rank,
        "title": raw.get("bookName", ""),
        "author": raw.get("author", ""),
        "category": raw.get("category", ""),
        "cover_url": _format_cover_url(raw.get("thumbUri", "")),
        "original_url": f"{HOME_URL}/page/{book_id}" if book_id else "",
        "summary": raw.get("abstract", "").replace("\\n", "\n").strip(),
        "tags": [],  # 番茄首页数据没有独立 tags，可用 category 作为标签
        "heat": rank,
        "heat_text": f"{source}第{rank}名",
        "extra": {
            "source": source,
            "book_id": book_id,
        },
    }


class FanqieCrawler:
    """番茄小说官网爬虫"""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def fetch_hot_books(
        self,
        week_count: int = 8,
        editor_count: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        抓取番茄首页热门内容。
        默认 weekList 取 8 本，editorList 取前 2 本补足 10 本。
        """
        total = week_count + editor_count
        logger.info(f"开始抓取番茄首页热门，目标 {total} 本（weekList {week_count} + editorList {editor_count}）")

        html = _fetch_html(HOME_URL, self.timeout)
        state = _extract_initial_state(html)
        if not state:
            return []

        home = state.get("home", {})
        week_list = home.get("weekList", [])[:week_count]
        editor_list = home.get("editorList", [])[:editor_count]

        logger.info(f"weekList: {len(week_list)} 本，editorList: {len(editor_list)} 本")

        books = []
        rank = 1
        for book in week_list:
            books.append(_parse_book_item(book, rank, "本周推荐"))
            rank += 1

        for book in editor_list:
            books.append(_parse_book_item(book, rank, "编辑推荐"))
            rank += 1

        return books


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = FanqieCrawler()
    data = crawler.fetch_hot_books()
    for book in data:
        print(f"{book['rank']}. {book['title']} - {book['author']} - {book['category']}")
        print(f"   简介: {book['summary'][:80]}...")
