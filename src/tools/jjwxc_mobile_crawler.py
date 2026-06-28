"""
晋江文学城手机站爬虫
抓取霸王票日榜，并进入详情页获取完整信息。
"""
import gzip
import html as ihtml
import logging
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://m.jjwxc.net"
PC_BASE_URL = "https://www.jjwxc.net"
RANK_URL = f"{BASE_URL}/ranks/kingticket"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": BASE_URL,
    "Connection": "keep-alive",
}

PC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def _fetch_html(url: str, timeout: int = 20) -> str:
    """获取页面 HTML 并解码"""
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        # 晋江手机站返回 gzip
        try:
            html = gzip.decompress(data).decode("gb18030", errors="ignore")
        except (OSError, gzip.BadGzipFile):
            html = data.decode("gb18030", errors="ignore")
    return html


def _parse_rank_list(html: str, max_count: int) -> List[Dict[str, Any]]:
    """从霸王票日榜页面解析书名和 novel_id"""
    items = []
    # 榜单结构：<a href="/book2/{novel_id}" ...>书名</a>
    matches = re.findall(
        r'<a\s+href="/book2/(\d+)"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )
    seen = set()
    for novel_id, title_html in matches:
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        if not title or title in seen or len(title) < 2:
            continue
        seen.add(title)
        items.append({
            "novel_id": novel_id,
            "title": title,
            "original_url": f"{BASE_URL}/book2/{novel_id}",
        })
        if len(items) >= max_count:
            break
    return items


def _parse_detail(html: str, novel_id: str) -> Dict[str, Any]:
    """解析详情页，提取作者、标签、类型、简介等"""
    result: Dict[str, Any] = {
        "author": "",
        "category": "",
        "tags": [],
        "summary": "",
        "one_line": "",
    }

    # 作者
    author_match = re.search(r'<meta name="author" content="([^,]+)', html)
    if author_match:
        result["author"] = author_match.group(1).strip()

    # 标签：从 keywords meta 提取
    keywords_match = re.search(
        r'<meta name="keywords" content="《[^》]+》,[^,]+,([^,]+),',
        html,
    )
    if keywords_match:
        tags_text = keywords_match.group(1).strip()
        result["tags"] = [t.strip() for t in tags_text.split() if t.strip()]

    # 类型：原创-言情-近代现代-爱情-女主视角
    type_match = re.search(r'<li>类型：([^<]+)</li>', html)
    if type_match:
        result["category"] = type_match.group(1).strip()

    # 一句话简介
    one_line_match = re.search(r'<li>一句话简介：([^<]+)</li>', html)
    if one_line_match:
        result["one_line"] = one_line_match.group(1).strip()

    # 完整简介
    intro_match = re.search(
        r'<[^>]*id="novelintro_whole"[^>]*>(.*?)</span>',
        html,
        re.DOTALL,
    )
    if intro_match:
        intro = re.sub(r"<[^>]+>", "", intro_match.group(1))
        intro = re.sub(r"\s+", " ", intro).strip()
        # 晋江简介后面常有"下本开..."等广告，截断
        intro = _truncate_after_marker(intro)
        result["summary"] = intro
    else:
        # 备用：从 novelintro 读取截断版
        intro_match = re.search(
            r'<[^>]*id="novelintro"[^>]*>(.*?)</div>',
            html,
            re.DOTALL,
        )
        if intro_match:
            intro = re.sub(r"<[^>]+>", "", intro_match.group(1))
            intro = re.sub(r"\s+", " ", intro).strip()
            result["summary"] = _truncate_after_marker(intro)

    return result


def _truncate_after_marker(text: str) -> str:
    """截断简介后面的作者广告/下本预告"""
    markers = [
        "___________________",
        "下本开",
        "预收",
        "预收文",
        "下一本",
        "求收藏",
        "微博",
        "专栏",
        "接档",
    ]
    for marker in markers:
        idx = text.find(marker)
        if idx != -1 and idx > 50:
            text = text[:idx].strip()
            break
    return text


def _fetch_pc_html(novel_id: str, timeout: int = 20) -> str:
    """获取晋江 PC 版详情页 HTML"""
    url = f"{PC_BASE_URL}/onebook.php?novelid={novel_id}"
    req = urllib.request.Request(url, headers=PC_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        try:
            html = gzip.decompress(data).decode("gb18030", errors="ignore")
        except (OSError, gzip.BadGzipFile):
            html = data.decode("gb18030", errors="ignore")
    return html


def _parse_pc_detail(html: str) -> Dict[str, Any]:
    """解析 PC 版详情页，提取封面图和完整简介"""
    result: Dict[str, Any] = {
        "cover_url": "",
        "summary": "",
    }

    # 锁文/提示页通常很短，直接跳过
    if len(html) < 5000 or "暂时还不能看" in html:
        return result

    # 封面图：novelimage.php
    cover_match = re.search(
        r'(https?://[^"\s]+novelimage\.php\?novelid=\d+[^"\s]*)',
        html,
        re.I,
    )
    if cover_match:
        result["cover_url"] = cover_match.group(1)

    # PC 版简介
    intro_match = re.search(
        r'<div[^>]*id="novelintro"[^>]*>(.*?)</div>',
        html,
        re.DOTALL | re.I,
    )
    if intro_match:
        intro = re.sub(r"<[^>]+>", "", intro_match.group(1))
        intro = re.sub(r"\s+", " ", intro).strip()
        intro = ihtml.unescape(intro)
        result["summary"] = _truncate_after_marker(intro)

    return result


class JjwxcMobileCrawler:
    """晋江文学城手机站爬虫"""

    def __init__(self, timeout: int = 20, detail_delay: float = 0.5):
        self.timeout = timeout
        self.detail_delay = detail_delay

    def fetch_hot_books(self, max_count: int = 10) -> List[Dict[str, Any]]:
        """
        抓取霸王票日榜 Top N，并进入详情页补充信息。
        同时用 PC 版详情页补封面图和更完整简介。
        """
        logger.info(f"开始抓取晋江手机站霸王票日榜，目标数量: {max_count}")

        rank_html = _fetch_html(RANK_URL, self.timeout)
        rank_items = _parse_rank_list(rank_html, max_count)
        logger.info(f"榜单页解析到 {len(rank_items)} 本书")

        books = []
        for idx, item in enumerate(rank_items, start=1):
            rank_str = f"[{idx}/{len(rank_items)}]"
            try:
                # 1. mobile 详情页：作者、标签、分类、简介
                detail_html = _fetch_html(item["original_url"], self.timeout)
                detail = _parse_detail(detail_html, item["novel_id"])

                # 2. PC 版详情页：封面图 + 更完整简介
                cover_url = ""
                pc_summary = ""
                try:
                    pc_html = _fetch_pc_html(item["novel_id"], self.timeout)
                    pc_detail = _parse_pc_detail(pc_html)
                    cover_url = pc_detail.get("cover_url", "")
                    pc_summary = pc_detail.get("summary", "")
                    logger.info(f"{rank_str} PC 版补充: cover={bool(cover_url)}, summary_len={len(pc_summary)}")
                except Exception as e:
                    logger.warning(f"{rank_str} PC 版详情页失败: {e}")

                # 优先使用更长的简介
                mobile_summary = detail.get("summary", "")
                summary = pc_summary if len(pc_summary) > len(mobile_summary) else mobile_summary

                books.append({
                    "rank": idx,
                    "title": item["title"],
                    "novel_id": item["novel_id"],
                    "original_url": item["original_url"],
                    "author": detail["author"],
                    "category": detail["category"],
                    "tags": detail["tags"],
                    "summary": summary,
                    "one_line": detail["one_line"],
                    "cover_url": cover_url,
                    "heat": idx,
                    "heat_text": f"霸王票日榜第{idx}名",
                })
                logger.info(f"{rank_str} {item['title']}")
                if idx < len(rank_items):
                    time.sleep(self.detail_delay)
            except Exception as e:
                logger.error(f"抓取详情页失败 {item['title']}: {e}")
                # 即使详情页失败，也保留榜单基础信息
                books.append({
                    "rank": idx,
                    "title": item["title"],
                    "novel_id": item["novel_id"],
                    "original_url": item["original_url"],
                    "author": "",
                    "category": "",
                    "tags": [],
                    "summary": "",
                    "one_line": "",
                    "cover_url": "",
                    "heat": idx,
                    "heat_text": f"霸王票日榜第{idx}名",
                })

        return books


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = JjwxcMobileCrawler()
    data = crawler.fetch_hot_books(max_count=10)
    for book in data:
        print(f"{book['rank']}. {book['title']} - {book['author']}")
        print(f"   标签: {', '.join(book['tags'])}")
        print(f"   简介: {book['summary'][:100]}...")
