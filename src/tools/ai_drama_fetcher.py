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


def load_news_article_ids() -> List[str]:
    """读取用作 AI 短剧/漫剧快讯来源的独立报道 ID 列表。"""
    config_path = os.path.join(_workspace_root(), "config", "ai_drama_articles.json")
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("ai_drama_fetcher: 读取新闻文章配置失败: %s", exc)
        return []
    ids = data.get("news", [])
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


def fetch_related_news_articles() -> List[Dict[str, str]]:
    """抓取配置中作为 AI 短剧/漫剧快讯来源的独立行业报道。"""
    articles: List[Dict[str, str]] = []
    for article_id in load_news_article_ids():
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
    if any(token in raw for token in ("上涨", "增长", "提升", "上升", "走高", "升", "爆发", "攀升")):
        return "up"
    if any(token in raw for token in ("下滑", "下降", "回落", "下跌", "降", "萎缩", "下滑")):
        return "down"
    return "same"


def _split_report_sections(text: str) -> Dict[str, str]:
    """把报告正文按「抖音端原生」和「红果」两块分开。"""
    sections: Dict[str, str] = {"douyin": "", "hongguo": ""}
    # 抖音端原生部分起点
    douyin_start_markers = [
        "抖音端原生百强榜",
        "抖音原生端AI剧/漫剧数据",
        "AI剧/漫剧抖音热播榜",
        "抖音端原生",
    ]
    # 红果部分起点
    hongguo_start_markers = [
        "红果AI剧/漫剧百强榜",
        "红果AI剧/漫剧数据",
        "AI剧/漫剧红果热播榜",
        "红果AI剧",
    ]
    # 结束标记
    end_markers = ["市场观察与总结研判", "原标题", "DataEye短剧观察"]

    def _find_index(markers, default=0):
        for m in markers:
            idx = text.find(m)
            if idx != -1:
                return idx
        return default

    douyin_start = _find_index(douyin_start_markers, default=len(text))
    hongguo_start = _find_index(hongguo_start_markers, default=len(text))

    if hongguo_start <= douyin_start:
        # 没有明确分界，全部视为 douyin
        sections["douyin"] = text
        return sections

    sections["douyin"] = text[douyin_start:hongguo_start]
    tail = text[hongguo_start:]
    end_idx = len(tail)
    for m in end_markers:
        idx = tail.find(m)
        if idx != -1 and idx < end_idx:
            end_idx = idx
    sections["hongguo"] = tail[:end_idx]
    return sections


def _rank_from_context(ctx: str) -> int:
    # 先匹配数字形式：第15/TOP15 -> 15，避免 "第15" 被误判为 1
    match = re.search(r"(?:第|TOP)(\d+)", ctx)
    if match:
        n = int(match.group(1))
        return n if 1 <= n <= 5 else 0
    # 中文数字
    if any(k in ctx for k in ("登顶", "第一", "位居榜首")):
        return 1
    if "第二" in ctx:
        return 2
    if "第三" in ctx:
        return 3
    if "第四" in ctx:
        return 4
    if "第五" in ctx:
        return 5
    return 0


def _heat_from_context(ctx: str) -> str:
    match = re.search(r"([\d.]+[万亿Ww]?)(?:播放增量|热度|最高热度|峰值热度)", ctx)
    if match:
        return match.group(1)
    match = re.search(r"(?:热度|播放增量|峰值).*?([\d.]+[万亿Ww]?)", ctx)
    if match:
        return match.group(1)
    match = re.search(r"([\d.]+[万亿Ww]?)\s*播放", ctx)
    if match:
        return match.group(1)
    return ""


def _studio_from_context(ctx: str) -> str:
    # 匹配 「XXX制作/出品/版权方的《...》」 或 「《...》，由XXX制作」
    match = re.search(r"([\u4e00-\u9fa5]{2,20})(?:制作|出品|版权方)的《", ctx)
    if match:
        return match.group(1)
    match = re.search(r"《[^》]+》[\s，,、；;]*(?:由|来自)([\u4e00-\u9fa5]{2,20})(?:制作|出品|版权方|工作室)", ctx)
    if match:
        return match.group(1)
    match = re.search(r"([\u4e00-\u9fa5]{2,20})的《", ctx)
    if match:
        return match.group(1)
    return ""


def _category_from_context(ctx: str, section_key: str) -> str:
    ctx_lower = ctx.lower()
    if "仿真人" in ctx or "ai仿真人" in ctx or "ai剧" in ctx:
        return "AI仿真人剧"
    if "3d漫" in ctx_lower or "3d" in ctx_lower:
        return "3D AI漫剧"
    if "2d漫" in ctx_lower or "2d" in ctx_lower:
        return "2D AI漫剧"
    if "aigc" in ctx_lower or "漫剧" in ctx:
        return "AIGC漫剧"
    return "AI仿真人剧" if section_key == "douyin" else "AIGC漫剧"


def _heat_for_title(title: str, section_text: str) -> str:
    """在剧名附近的短窗口中搜索热度/播放增量数值（必须带单位）。"""
    marker = f"《{title}》"
    idx = section_text.find(marker)
    if idx == -1:
        return ""
    # 先向后看 160 字符
    after = section_text[idx : idx + 160]
    match = re.search(r"(?:播放增量|热度|峰值).*?([\d.]+[万亿Ww])", after)
    if match:
        return match.group(1)
    # 再向前看 120 字符
    before = section_text[max(0, idx - 120) : idx]
    match2 = re.search(r"([\d.]+[万亿Ww])[^。；\n]{0,80}?" + re.escape(marker), before + marker)
    if match2:
        return match2.group(1)
    return ""


# 常见非制作方词汇，避免被误识别为 studio
_STUDIO_BLACKLIST = {"上线", "播出", "发布", "出品", "制作", "改编", "连载", "更新", "位居", "排名"}


def _clean_studio(raw: str) -> str:
    raw = raw.strip()
    if not raw or len(raw) < 2 or raw in _STUDIO_BLACKLIST:
        return ""
    return raw


def _studio_for_title(title: str, section_text: str) -> str:
    """在全段中搜索与该剧名最近的制作方/工作室。"""
    for window_size in (60, 120):
        # 制作方《title》
        pattern = rf"([\u4e00-\u9fa5]{{2,20}})(?:制作|出品|版权方)的《{re.escape(title)}》"
        match = re.search(pattern, section_text)
        if match:
            studio = _clean_studio(match.group(1))
            if studio:
                return studio
        # title》由XXX制作
        pattern2 = rf"《{re.escape(title)}》[^。；\n]{{0,{window_size}}}?(?:由|来自)([\u4e00-\u9fa5]{{2,20}})(?:制作|出品|版权方|工作室)"
        match2 = re.search(pattern2, section_text)
        if match2:
            studio = _clean_studio(match2.group(1))
            if studio:
                return studio
        # XXX的《title》（兜底）
        pattern3 = rf"([\u4e00-\u9fa5]{{2,20}})的《{re.escape(title)}》"
        match3 = re.search(pattern3, section_text)
        if match3:
            studio = _clean_studio(match3.group(1))
            if studio:
                return studio
    return ""


def _split_sentences(text: str) -> List[str]:
    """按中文标点切分句子。"""
    return [s.strip() for s in re.split(r"[。；;！!？?\n]", text) if s.strip()]


def _extract_rank_items(section_text: str, section_key: str) -> List[Dict[str, Any]]:
    """从报告某一块正文中提取排名条目，尽量还原 rank/title/heat/studio/category。"""
    items: List[Dict[str, Any]] = []
    seen: set = set()

    sentences = _split_sentences(section_text)
    for sentence in sentences:
        titles = re.findall(r"《([^》]{2,30})》", sentence)
        if not titles:
            continue
        for title in titles:
            title = title.strip()
            if title in seen:
                continue
            rank_ctx = sentence.replace(f"《{title}》", "")
            rank = _rank_from_context(rank_ctx)
            if not rank or rank > 5:
                # 该句没有明确排名信息，或排名超出 TOP5，跳过
                continue
            seen.add(title)
            ctx = sentence
            heat = _heat_for_title(title, section_text)
            studio = _studio_for_title(title, section_text)
            category = _category_from_context(ctx, section_key)
            items.append({
                "rank": rank,
                "title": title,
                "platform": "抖音" if section_key == "douyin" else "红果",
                "category": category,
                "heat": heat,
                "is_new": "新剧" in ctx or "本月" in ctx,
                "plot": "",
                "tags": [],
                "studio": studio,
                "url": "",
            })

    # 若显式排名不足 3 条，兜底扫描带「播放增量达/热度达」的书名号剧目
    if len(items) < 3:
        for match in re.finditer(r"《([^》]{2,30})》[^。；\n]{0,40}?(?:播放增量|热度|峰值).*?([\d.]+[万亿Ww]?)", section_text):
            title = match.group(1).strip()
            if title in seen:
                continue
            seen.add(title)
            ctx = section_text[max(0, match.start() - 40):match.end() + 40]
            items.append({
                "rank": 0,
                "title": title,
                "platform": "抖音" if section_key == "douyin" else "红果",
                "category": _category_from_context(ctx, section_key),
                "heat": match.group(2),
                "is_new": "新剧" in ctx,
                "plot": "",
                "tags": [],
                "studio": _studio_for_title(title, section_text),
                "url": "",
            })

    # 去重并按 rank 排序；rank 为 0 的按出现顺序排在后面
    items = sorted(items, key=lambda x: (x["rank"] == 0, x["rank"]))
    # 重新编排 rank
    for idx, item in enumerate(items, start=1):
        if item["rank"] == 0:
            item["rank"] = idx
    return items


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

    patterns = [
        (r"新增AI剧/?漫剧约([\d.]+)万部", "月新增AI剧/漫剧", "万部"),
        (r"播放破亿的有(\d+)部", "月播放破亿剧目数", "部"),
        (r"破百万率([\d.]+)%", "破百万率", "%"),
        (r"播放增量破100万的有(\d+)部", "播放破百万剧目数", "部"),
        (r"新剧在.*?贡献了超([\d.]+)亿播放增量", "新剧播放增量", "亿"),
        (r"播放增量达([\d.]+)亿", "头部剧目播放增量", "亿"),
        (r"新剧贡献了超([\d.]+)亿播放增量", "新剧总播放增量", "亿"),
        (r"峰值热度总计([\d.]+)亿", "红果峰值热度总计", "亿"),
    ]
    for pattern, label, unit in patterns:
        match = re.search(pattern, combined)
        if match:
            kpis.append(
                {
                    "label": label,
                    "value": match.group(1),
                    "unit": unit,
                    "trend": _parse_trend(combined[max(0, match.start() - 40):match.end() + 40]),
                    "period": "环比",
                    "note": "",
                }
            )

    sections = _split_report_sections(combined)
    douyin_items = _extract_rank_items(sections.get("douyin", ""), "douyin")
    hongguo_items = _extract_rank_items(sections.get("hongguo", ""), "hongguo")

    # 抖音段默认归到 ai_drama；红果段中 3D/2D/AIGC 归 ai_comic，AI仿真人剧归 ai_drama
    ai_drama: List[Dict[str, Any]] = []
    ai_comic: List[Dict[str, Any]] = []

    for item in douyin_items[:8]:
        target = ai_comic if "漫" in item["category"] else ai_drama
        target.append(item)

    for item in hongguo_items[:8]:
        if "仿真人" in item["category"]:
            ai_drama.append(item)
        else:
            ai_comic.append(item)

    # 按 rank 去重并截断到前 5
    def _dedupe_and_trim(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_titles: set = set()
        out: List[Dict[str, Any]] = []
        for it in sorted(items, key=lambda x: x["rank"]):
            if it["title"] not in seen_titles:
                seen_titles.add(it["title"])
                out.append(it)
        return out[:5]

    ai_drama = _dedupe_and_trim(ai_drama)
    ai_comic = _dedupe_and_trim(ai_comic)

    # 趋势：优先提取 DataEye研究院认为 / 市场观察段落
    opinion_patterns = [
        r"DataEye研究院认为[：:]\s*([^\n。]{20,200}[。])",
        r"(?:市场观察与总结研判|总结研判)[\s\S]{0,80}?([\u4e00-\u9fa5]{30,200}[。])",
        r"(?:来看|可以看出|值得关注的是)[，:]\s*([^\n。]{20,200}[。])",
    ]
    seen_opinion: set = set()
    for pattern in opinion_patterns:
        for match in re.finditer(pattern, combined):
            snippet = match.group(1).strip()[:160]
            if snippet and snippet not in seen_opinion and len(snippet) >= 20:
                seen_opinion.add(snippet)
                trends.append({
                    "title": f"趋势洞察{len(trends) + 1}",
                    "summary": snippet,
                    "source": "澎湃新闻 / DataEye",
                    "source_url": "",
                })

    # 兜底：找一些含关键词的短句
    if not trends:
        trend_snippets = re.findall(r"[^。\n]{12,80}(?:趋势|监管|出海|分成|上新|回落|增长|转型)[^。\n]{0,60}", combined)
        for idx, snippet in enumerate(trend_snippets[:5]):
            trends.append({"title": f"趋势洞察{idx + 1}", "summary": snippet.strip(), "source": "", "source_url": ""})

    for article in articles:
        url = article.get("url", "")
        if not url:
            continue
        news.append(
            {
                "title": article.get("title", "")[:80],
                "source": "澎湃新闻",
                "date": report_month + "-01",
                "url": url,
                "summary": "",
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
