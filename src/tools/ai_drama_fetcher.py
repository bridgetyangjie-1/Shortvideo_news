"""
AI 短剧/漫剧看板数据抓取

主渠道：澎湃新闻 thepaper.cn 上的 DataEye 月报/百强榜（可直爬，不依赖 Kimi 联网质量）。
备用：从 Kimi 搜索文本中提取 thepaper 文章 ID。
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

THEPAPER_MOBILE_URL = "https://m.thepaper.cn/newsDetail_forward_{article_id}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _workspace_root() -> str:
    return os.getenv("COZE_WORKSPACE_PATH", os.getcwd())


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "\n", html or "")
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def extract_thepaper_ids(text: str) -> List[str]:
    return list(dict.fromkeys(re.findall(r"newsDetail_forward_(\d+)", text or "")))


def load_article_ids(report_month: str) -> List[str]:
    """读取 config/ai_drama_articles.json 中该报告月份的文章 ID 列表。"""
    config_path = os.path.join(_workspace_root(), "config", "ai_drama_articles.json")
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("ai_drama_fetcher: 读取文章配置失败: %s", exc)
        return []
    ids = data.get(report_month, [])
    if not isinstance(ids, list):
        return []
    return [str(item) for item in ids if str(item).isdigit()]


def fetch_thepaper_article(article_id: str, timeout: float = 25.0) -> Optional[Dict[str, str]]:
    """抓取单篇澎湃新闻文章，返回 title / text / url。"""
    article_id = str(article_id).strip()
    if not article_id.isdigit():
        return None
    url = THEPAPER_MOBILE_URL.format(article_id=article_id)
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("ai_drama_fetcher: 抓取 thepaper 文章 %s 失败: %s", article_id, exc)
        return None

    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        response.text,
        re.S,
    )
    if not match:
        logger.warning("ai_drama_fetcher: 文章 %s 未找到 __NEXT_DATA__", article_id)
        return None

    try:
        payload = json.loads(match.group(1))
        detail = payload["props"]["pageProps"]["detailData"]["contentDetail"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("ai_drama_fetcher: 解析文章 %s JSON 失败: %s", article_id, exc)
        return None

    title = str(detail.get("name", "") or "").strip()
    content_html = str(detail.get("content", "") or "")
    text = strip_html(content_html)
    if len(text) < 80:
        logger.warning("ai_drama_fetcher: 文章 %s 正文过短，可能抓取失败", article_id)
        return None

    logger.info("ai_drama_fetcher: 成功抓取 thepaper 文章 %s，标题=%s，正文=%d 字", article_id, title[:40], len(text))
    return {"article_id": article_id, "title": title, "text": text, "url": url}


def fetch_report_articles(report_month: str) -> List[Dict[str, str]]:
    """按报告月份抓取配置中的全部 thepaper 文章。"""
    articles: List[Dict[str, str]] = []
    for article_id in load_article_ids(report_month):
        article = fetch_thepaper_article(article_id)
        if article:
            articles.append(article)
    return articles


def fetch_articles_by_ids(article_ids: List[str]) -> List[Dict[str, str]]:
    articles: List[Dict[str, str]] = []
    for article_id in article_ids:
        article = fetch_thepaper_article(article_id)
        if article:
            articles.append(article)
    return articles


def _parse_trend(raw: str) -> str:
    if any(token in raw for token in ("上涨", "增长", "提升", "上升", "走高", "升")):
        return "up"
    if any(token in raw for token in ("下滑", "下降", "回落", "下跌", "降")):
        return "down"
    return "same"


def regex_extract_dashboard(articles: List[Dict[str, str]], report_month: str) -> Dict[str, Any]:
    """
    从 thepaper 正文用规则提取 KPI / 榜单 / 趋势（无 LLM 兜底）。
    数据不完整但优于全空。
    """
    combined = "\n".join(f"{a.get('title', '')}\n{a.get('text', '')}" for a in articles)
    if not combined.strip():
        return {}

    kpis: List[Dict[str, Any]] = []
    trends: List[Dict[str, str]] = []
    news: List[Dict[str, str]] = []
    ai_drama: List[Dict[str, Any]] = []
    ai_comic: List[Dict[str, Any]] = []

    patterns = [
        (r"新增AI剧/?漫剧约([\d.]+)万部", "月新增AI剧/漫剧", "万部"),
        (r"播放破亿的有(\d+)部", "月播放破亿剧目数", "部"),
        (r"破百万率([\d.]+)%", "破百万率", "%"),
        (r"播放增量破100万的有(\d+)部", "播放破百万剧目数", "部"),
        (r"新剧在.*?贡献了超([\d.]+)亿播放增量", "新剧播放增量", "亿"),
        (r"播放增量达([\d.]+)亿", "头部剧目播放增量", "亿"),
    ]
    for pattern, label, unit in patterns:
        match = re.search(pattern, combined)
        if match:
            kpis.append(
                {
                    "label": label,
                    "value": match.group(1),
                    "unit": unit,
                    "trend": "same",
                    "period": "环比",
                    "note": "",
                }
            )

    rank_patterns = [
        r"《([^》]{2,30})》[^。\n]{0,40}?(?:播放增量|热度|位居第[一二三四五1-5])[达为]?([\d.]+[亿万Ww]?(?:播放增量|热度)?|[\d.]+亿)",
        r"(?:登顶|第一|TOP1)[^《\n]{0,20}《([^》]{2,30})》",
        r"《([^》]{2,30})》[^。\n]{0,30}?(?:第二|第三|第四|第五)",
    ]
    seen_titles: set[str] = set()
    rank = 1
    for pattern in rank_patterns:
        for match in re.finditer(pattern, combined):
            title = match.group(1).strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            heat = match.group(2).strip() if match.lastindex and match.lastindex >= 2 else ""
            category = "AI仿真人剧"
            if any(token in combined[max(0, match.start() - 80): match.end() + 80] for token in ("3D漫", "2D漫", "漫剧", "AIGC")):
                category = "AIGC漫剧"
                target = ai_comic
            else:
                target = ai_drama
            target.append(
                {
                    "rank": rank,
                    "title": title,
                    "platform": "抖音/红果",
                    "category": category,
                    "heat": heat,
                    "is_new": "新剧" in combined[max(0, match.start() - 40): match.end() + 40],
                }
            )
            rank += 1
            if rank > 5:
                break
        if rank > 5:
            break

    trend_snippets = re.findall(r"[^。\n]{12,80}(?:趋势|监管|出海|分成|上新|回落|增长)[^。\n]{0,60}", combined)
    for idx, snippet in enumerate(trend_snippets[:5]):
        trends.append({"title": f"趋势洞察{idx + 1}", "summary": snippet.strip()})

    for article in articles:
        news.append(
            {
                "title": article.get("title", "")[:80],
                "source": "澎湃新闻 / DataEye",
                "date": report_month + "-01",
                "url": article.get("url", ""),
            }
        )

    source_urls = ", ".join(a.get("url", "") for a in articles if a.get("url"))
    return {
        "report_month": report_month,
        "kpis": kpis[:6],
        "rankings": {"ai_drama": ai_drama[:5], "ai_comic": ai_comic[:5]},
        "trends": trends[:5],
        "news": news[:5],
        "data_source": f"澎湃新闻 DataEye 月报直爬（{source_urls[:120]}）",
        "update_frequency": "monthly",
    }


def combine_articles_text(articles: List[Dict[str, str]], max_chars: int = 12000) -> str:
    chunks: List[str] = []
    for article in articles:
        chunk = f"【来源】{article.get('title', '')}\n{article.get('url', '')}\n{article.get('text', '')}"
        chunks.append(chunk)
    text = "\n\n---\n\n".join(chunks)
    if len(text) > max_chars:
        return text[:max_chars] + "\n...(正文截断)"
    return text
