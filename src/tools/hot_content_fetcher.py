"""
热门内容抓取器
统一抓取红果、晋江、番茄三个平台的热门内容。
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from tools.hongguo_crawler import HongguoCrawler
from tools.jjwxc_mobile_crawler import JjwxcMobileCrawler
from tools.fanqie_crawler import FanqieCrawler

logger = logging.getLogger(__name__)


def get_week_start(date: datetime = None) -> datetime:
    """获取当周周一日期"""
    if date is None:
        date = datetime.now()
    return date - timedelta(days=date.weekday())


def format_week_label(start: datetime, end: datetime) -> str:
    """格式化周标签，如 2026.06.30 - 07.06"""
    start_str = start.strftime("%Y.%m.%d")
    end_str = end.strftime("%m.%d")
    return f"{start_str} - {end_str}"


def fetch_hongguo() -> Dict[str, Any]:
    """抓取红果短剧热门"""
    logger.info("开始抓取红果短剧...")
    crawler = HongguoCrawler()
    dramas = crawler.fetch_homepage_list(max_count=10)

    items = []
    for drama in dramas:
        series_id = drama.get("series_id", "")
        tags = drama.get("tags", []) or []
        episodes = drama.get("episodes", "")

        # 优先使用详情页提取到的真实剧情简介
        summary = (drama.get("summary", "") or "").strip()
        if not summary:
            summary_parts = []
            if tags:
                summary_parts.append(f"题材标签：{', '.join(tags[:5])}。")
            if episodes:
                summary_parts.append(f"{episodes}。")
            summary = " ".join(summary_parts)

        items.append({
            "rank": drama.get("rank", 0),
            "title": drama.get("title", ""),
            "author": "",
            "cover_url": drama.get("cover", ""),
            "original_url": f"https://novelquickapp.com/series/{series_id}" if series_id else "",
            "summary": summary,
            "tags": tags[:5],
            "heat": drama.get("rank", 0),
            "heat_text": f"首页热门第{drama.get('rank', 0)}名",
            "platform_key": "hongguo",
            "extra": {
                "episodes": episodes,
                "series_id": series_id,
            },
        })

    logger.info(f"红果抓取完成: {len(items)} 条")
    return {
        "platform": "红果短剧",
        "platform_key": "hongguo",
        "source_url": "https://novelquickapp.com/",
        "update_frequency": "周更",
        "item_count": len(items),
        "items": items,
    }


def fetch_jjwxc() -> Dict[str, Any]:
    """抓取晋江小说热门"""
    logger.info("开始抓取晋江小说...")
    crawler = JjwxcMobileCrawler(detail_delay=0.5)
    books = crawler.fetch_hot_books(max_count=10)

    items = []
    for book in books:
        tags = book.get("tags", []) or []
        category = book.get("category", "")
        if not tags and category:
            tags = [category.split("-")[-1].strip()] if "-" in category else [category]

        items.append({
            "rank": book.get("rank", 0),
            "title": book.get("title", ""),
            "author": book.get("author", ""),
            "cover_url": book.get("cover_url", ""),
            "original_url": book.get("original_url", ""),
            "summary": book.get("summary", ""),
            "tags": tags[:5],
            "heat": book.get("rank", 0),
            "heat_text": book.get("heat_text", ""),
            "platform_key": "jjwxc",
            "extra": {
                "category": category,
                "one_line": book.get("one_line", ""),
                "novel_id": book.get("novel_id", ""),
            },
        })

    logger.info(f"晋江抓取完成: {len(items)} 条")
    return {
        "platform": "晋江小说",
        "platform_key": "jjwxc",
        "source_url": "https://m.jjwxc.net/ranks/kingticket",
        "update_frequency": "周更（基于日榜快照）",
        "item_count": len(items),
        "items": items,
    }


def fetch_fanqie() -> Dict[str, Any]:
    """抓取番茄小说热门"""
    logger.info("开始抓取番茄小说...")
    crawler = FanqieCrawler()
    books = crawler.fetch_hot_books(week_count=8, editor_count=2)

    items = []
    for book in books:
        category = book.get("category", "")
        tags = book.get("tags", []) or []
        if category and category not in tags:
            tags.insert(0, category)

        items.append({
            "rank": book.get("rank", 0),
            "title": book.get("title", ""),
            "author": book.get("author", ""),
            "cover_url": book.get("cover_url", ""),
            "original_url": book.get("original_url", ""),
            "summary": book.get("summary", ""),
            "tags": tags[:5],
            "heat": book.get("rank", 0),
            "heat_text": book.get("heat_text", ""),
            "platform_key": "fanqie",
            "extra": {
                "category": category,
                "book_id": book.get("extra", {}).get("book_id", ""),
                "source": book.get("extra", {}).get("source", ""),
            },
        })

    logger.info(f"番茄抓取完成: {len(items)} 条")
    return {
        "platform": "番茄小说",
        "platform_key": "fanqie",
        "source_url": "https://fanqienovel.com/",
        "update_frequency": "周更",
        "item_count": len(items),
        "items": items,
    }


def fetch_all_raw() -> Dict[str, Any]:
    """抓取所有平台原始数据并组装"""
    now = datetime.now()
    week_start = get_week_start(now)
    week_end = week_start + timedelta(days=6)
    data_date = week_start.strftime("%Y-%m-%d")
    week_label = format_week_label(week_start, week_end)

    sections = [
        fetch_hongguo(),
        fetch_jjwxc(),
        fetch_fanqie(),
    ]

    total_items = sum(s["item_count"] for s in sections)

    return {
        "data_date": data_date,
        "week_label": week_label,
        "update_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "total_items": total_items,
        "sections": sections,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = fetch_all_raw()
    print(f"data_date: {data['data_date']}")
    print(f"week_label: {data['week_label']}")
    print(f"total_items: {data['total_items']}")
    for section in data["sections"]:
        print(f"  {section['platform']}: {section['item_count']} 条")
