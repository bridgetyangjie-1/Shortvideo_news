"""
短剧工程 (duanjugongcheng.com) 榜单爬虫
基于红果短剧官方周榜数据，每周一更新 TOP50。
"""
import re
import json
import urllib.request
import urllib.error
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://www.duanjugongcheng.com"
HOMEPAGE_URL = f"{BASE_URL}/cn/bangdan/"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}


def _fetch_html(url: str, timeout: int = 20) -> str:
    """获取页面 HTML"""
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP错误 {e.code}: {url}")
        raise
    except urllib.error.URLError as e:
        logger.error(f"URL错误: {url}, {e.reason}")
        raise
    except Exception as e:
        logger.error(f"请求失败: {url}, {e}")
        raise


def _has_ranking_data(html: str) -> bool:
    """检查页面是否包含有效榜单数据"""
    return "榜单数据暂时无法加载" not in html and "<table" in html


def _parse_table(html: str, week_date: str) -> List[Dict[str, Any]]:
    """解析榜单表格（含剧目 slug）"""
    rankings = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    
    for row in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
        if not cells:
            continue
        
        # 去除 HTML 标签和空白
        texts = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        
        # 跳过表头
        if not texts or texts[0] in ("排名", "") or not re.match(r'^\d+$', str(texts[0])):
            continue
        
        try:
            rank = int(texts[0])
        except (ValueError, IndexError):
            continue
        
        slug_match = re.search(r'/cn/bangdan/ju/([^"/?#]+)', row)
        slug = slug_match.group(1) if slug_match else ""
        
        # 短剧名称字段通常包含"新上架/上架"和日期
        raw_title = texts[2] if len(texts) > 2 else ""
        title_info = _parse_title(raw_title)
        
        genre = texts[3] if len(texts) > 3 else ""
        weekly_index = _parse_number(texts[4]) if len(texts) > 4 else 0
        total_index = _parse_number(texts[5]) if len(texts) > 5 else 0
        
        rankings.append({
            "rank": rank,
            "title": title_info["title"],
            "slug": slug,
            "genre": genre,
            "weekly_index": weekly_index,
            "total_index": total_index,
            "release_date": title_info["release_date"],
            "is_new": title_info["is_new"],
            "platform": "红果",
            "source": "duanjugongcheng",
            "week_date": week_date,
            "raw_title": raw_title,
        })
    
    return rankings


def _parse_title(raw_title: str) -> Dict[str, Any]:
    """
    解析标题字段，提取剧名、是否新剧、上架日期。
    示例：
        "少夫人来自东北2上架 2026-06-06"
        "顾先生，搭个伙新上架 2026-06-08"
    """
    result = {"title": raw_title, "is_new": False, "release_date": ""}
    if not raw_title:
        return result
    
    # 匹配"新上架"或"上架"前缀的日期
    m = re.search(r'(.*?)(新上架|上架)\s*(\d{4}-\d{2}-\d{2})', raw_title)
    if m:
        result["title"] = m.group(1).strip()
        result["is_new"] = m.group(2) == "新上架"
        result["release_date"] = m.group(3)
    
    return result


def _parse_number(text: str) -> int:
    """提取数字"""
    if not text:
        return 0
    nums = re.findall(r'\d+', str(text).replace(',', ''))
    return int(nums[0]) if nums else 0


def fetch_homepage_top10() -> List[Dict[str, Any]]:
    """爬取短剧工程首页周榜 TOP10"""
    logger.info("开始爬取短剧工程首页周榜 TOP10")
    html = _fetch_html(HOMEPAGE_URL)
    
    if not _has_ranking_data(html):
        logger.warning("短剧工程首页暂无榜单数据")
        return []
    
    # 首页不指定具体 week_date，使用页面中最新日期或当前日期
    week_date = _extract_latest_week_date(html) or datetime.now().strftime("%Y-%m-%d")
    rankings = _parse_table(html, week_date)
    logger.info(f"短剧工程首页解析完成，获取 {len(rankings)} 条数据")
    return rankings


def fetch_week_ranking(week_date: str) -> List[Dict[str, Any]]:
    """
    爬取指定日期周的完整 TOP50 榜单
    
    Args:
        week_date: 周一日期，格式 YYYY-MM-DD
    """
    url = f"{BASE_URL}/cn/bangdan/{week_date}"
    logger.info(f"开始爬取短剧工程周榜: {url}")
    html = _fetch_html(url)
    
    if not _has_ranking_data(html):
        logger.warning(f"短剧工程 {week_date} 暂无榜单数据")
        return []
    
    rankings = _parse_table(html, week_date)
    logger.info(f"短剧工程 {week_date} 解析完成，获取 {len(rankings)} 条数据")
    return rankings


def find_latest_available_week(
    anchor_date: Optional[datetime] = None,
    lookback_weeks: int = 4
) -> Optional[str]:
    """
    查找最近有数据的周一日期
    
    Args:
        anchor_date: 锚定日期，默认今天
        lookback_weeks: 最多回退几周
    
    Returns:
        有数据的周一日期字符串 YYYY-MM-DD，找不到返回 None
    """
    if anchor_date is None:
        anchor_date = datetime.now()
    
    # 回退到最近的周一
    current = anchor_date - timedelta(days=anchor_date.weekday())
    
    for _ in range(lookback_weeks):
        week_date = current.strftime("%Y-%m-%d")
        try:
            html = _fetch_html(f"{BASE_URL}/cn/bangdan/{week_date}", timeout=15)
            if _has_ranking_data(html):
                return week_date
        except Exception as e:
            logger.warning(f"检查 {week_date} 失败: {e}")
        current -= timedelta(weeks=1)
    
    return None


def fetch_latest_full_ranking(
    anchor_date: Optional[datetime] = None,
    lookback_weeks: int = 4
) -> List[Dict[str, Any]]:
    """
    自动查找最近有数据的周榜并返回完整 TOP50
    """
    latest_week = find_latest_available_week(anchor_date, lookback_weeks)
    if not latest_week:
        logger.warning("未找到可用的短剧工程周榜，降级到首页 TOP10")
        return fetch_homepage_top10()
    
    rankings = fetch_week_ranking(latest_week)
    if not rankings:
        logger.warning("完整周榜为空，降级到首页 TOP10")
        return fetch_homepage_top10()
    
    return rankings


def _extract_latest_week_date(html: str) -> Optional[str]:
    """从首页 HTML 中提取最新周榜日期"""
    # 尝试从历史链接中找最近的周一
    links = re.findall(r'href="(/cn/bangdan/\d{4}-\d{2}-\d{2})"', html)
    dates = [link.split('/')[-1] for link in links]
    if dates:
        # 按日期降序
        dates.sort(reverse=True)
        return dates[0]
    return None


def fetch_drama_detail(slug: str) -> Optional[Dict[str, Any]]:
    """
    通过短剧工程 wind-vane API 获取剧目详情（封面/标签/题材等）。
    不含演员与 series_id。
    """
    if not slug:
        return None
    url = f"{BASE_URL}/api/wind-vane/v1/drama/detail?slug={slug}"
    try:
        req = urllib.request.Request(
            url,
            headers={**DEFAULT_HEADERS, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict) or not data.get("drama_name"):
            return None
        return {
            "slug": slug,
            "title": data.get("drama_name", ""),
            "cover": data.get("cover_url", ""),
            "genre": data.get("genre", ""),
            "tags": list(data.get("tags") or []),
            "online_date": data.get("online_date", ""),
            "stats": data.get("stats") or {},
        }
    except Exception as exc:
        logger.warning("短剧工程详情 API 失败 slug=%s: %s", slug, exc)
        return None


def backfill_rankings_from_detail_api(
    rankings: List[Dict[str, Any]],
    *,
    max_fetch: int = 20,
    sleep_seconds: float = 0.15,
) -> Dict[str, int]:
    """
    用短剧工程 detail API 回填封面/标签/题材。
    Returns: {"detail_hits": int, "slug_missing": int}
    """
    stats = {"detail_hits": 0, "slug_missing": 0}
    for item in rankings[:max_fetch]:
        slug = item.get("slug", "")
        if not slug:
            stats["slug_missing"] += 1
            continue
        detail = fetch_drama_detail(slug)
        if not detail:
            continue
        stats["detail_hits"] += 1
        if not item.get("cover") and detail.get("cover"):
            item["cover"] = detail["cover"]
        if not item.get("tags") and detail.get("tags"):
            item["tags"] = detail["tags"]
        if not item.get("genre") and detail.get("genre"):
            item["genre"] = detail["genre"]
        if not item.get("release_date") and detail.get("online_date"):
            item["release_date"] = detail["online_date"]
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    if stats["detail_hits"]:
        logger.info(
            "短剧工程 detail API 回填: %d/%d 条（slug缺失 %d）",
            stats["detail_hits"],
            min(len(rankings), max_fetch),
            stats["slug_missing"],
        )
    return stats


def build_duanju_metadata_index(
    duanju_data: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """构建以剧名为键的元数据索引"""
    index: Dict[str, Dict[str, Any]] = {}
    for item in duanju_data or []:
        title = item.get("title", "").strip()
        if title:
            index[title] = item
            index[title.replace(" ", "")] = item
    return index


if __name__ == "__main__":
    print("=== 短剧工程首页 TOP10 ===")
    top10 = fetch_homepage_top10()
    for item in top10[:5]:
        print(item)
    
    print("\n=== 最近完整周榜 TOP5 ===")
    full = fetch_latest_full_ranking()
    for item in full[:5]:
        print(item)
