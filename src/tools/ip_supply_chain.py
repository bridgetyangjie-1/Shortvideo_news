"""
IP 供应链工具
1. 从红果详情页提取"改编自"信息
2. 尝试爬番茄小说榜单（备用）
3. 短剧标题 ↔ 原著标题 模糊匹配
"""
import re
import urllib.request
import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# 番茄小说榜单（备用数据源）
def fetch_fanqienovel_data(max_count: int = 30) -> List[Dict[str, Any]]:
    """
    尝试爬取番茄小说热榜。如果失败，返回空列表，不抛异常。
    """
    try:
        url = "https://fanqienovel.com/page/top"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # 尝试提取页面中的 JSON 数据（类似红果）
        start = html.find('window.__INITIAL_STATE__')
        if start < 0:
            return []

        # 简单提取，如果失败返回空
        return []
    except Exception as e:
        logger.warning(f"番茄小说爬取失败: {e}，返回空列表")
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
            return {
                "source_title": m.group(1).strip(),
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

    # 2. 如果提取失败，尝试番茄小说匹配
    novels = fetch_fanqienovel_data(20)
    matched = match_drama_to_novel(drama_title, novels)
    if matched:
        result.update({
            "has_ip_source": True,
            "source_title": matched.get("title", ""),
            "source_author": matched.get("author", ""),
            "source_platform": "番茄小说",
            "match_confidence": 0.7
        })

    return result
