"""
数据质量校验工具：演员/厂牌幻觉检测、快讯 URL 校验等。
供 enrich、news、quality_gate 等节点复用。
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from tools.actor_name_utils import is_placeholder_actor_name

# 姓 + 编号式幻觉演员名，如「李十三」「王十四」「钱二十一」
_HALLUCINATED_ACTOR_PATTERN = re.compile(
    r"^(?:张|李|王|赵|钱|孙|周|吴|郑|陈|刘|黄|杨|朱|秦|许|何|吕|施|马|白|徐|曾|甄|鹿|滕|贾|余|杨)"
    r"(?:十[一二三四五六七八九]?|二十[一二三四五六七八九]?|三十|四十|五十|[0-9]{1,3})$"
)

# 颜色/意象 + 影视 + 工作室/公司/厂牌 的模板化幻觉厂牌
_COLOR_CHARS = "蓝红绿黄白黑紫金银青灰橙粉棕翠墨碧"
_NATURE_CHARS = "海岛屿石雀霞月鼎星云枫松竹梅兰菊鹤鹰狼豹狮虎龙凤马牛羊鹿熊象鸟羽泉溪川江光风雷雨"
_SUSPICIOUS_STUDIO_PATTERN = re.compile(
    rf"^[{_COLOR_CHARS}][{_NATURE_CHARS}]*影视(?:工作室|公司|厂牌)$"
)

KNOWN_STUDIOS = frozenset({
    "九州", "点众", "麦芽", "蜜糖", "容量", "天桥", "花生", "映客", "番茄", "网易",
    "华策", "柠萌", "正午", "长信", "冬漫", "掌阅", "中文在线", "趣丸", "碧海",
    "海看", "六翼", "硕才", "硕才传媒", "硕才文化", "海看影业", "海看网络",
    "独立厂牌", "待核实",
})

BLOCKED_NEWS_DOMAINS = frozenset({
    "example.com", "example.org", "example.net", "test.com", "localhost",
    "127.0.0.1", "placeholder.com",
})

BLOCKED_NEWS_URL_PATTERNS = [
    re.compile(r"google\.com/search", re.I),
    re.compile(r"baidu\.com/s\?", re.I),
    re.compile(r"bing\.com/search", re.I),
]

_PLACEHOLDER_STUDIO = frozenset({
    "", "未知", "待补充", "待定", "独立厂牌", "待核实", "n/a", "none", "null",
})


def is_hallucinated_actor_name(name: Any) -> bool:
    """判断是否为 LLM 编造的编号式演员名或占位名。"""
    text = str(name or "").strip()
    if not text:
        return False
    if is_placeholder_actor_name(text):
        return True
    return bool(_HALLUCINATED_ACTOR_PATTERN.fullmatch(text))


def is_suspicious_studio_name(name: Any) -> bool:
    """判断厂牌是否为模板化幻觉名称。"""
    text = str(name or "").strip()
    if not text or text in _PLACEHOLDER_STUDIO:
        return False
    if text in KNOWN_STUDIOS:
        return False
    return bool(_SUSPICIOUS_STUDIO_PATTERN.fullmatch(text))


def sanitize_production_house(name: Any) -> str:
    """清洗可疑厂牌，无信源或幻觉时返回空字符串。"""
    text = str(name or "").strip()
    if not text or text in _PLACEHOLDER_STUDIO:
        return ""
    if is_suspicious_studio_name(text):
        return ""
    return text


def is_trusted_news_url(url: Any) -> bool:
    """快讯来源 URL 是否通过可信度校验。"""
    text = str(url or "").strip()
    if not text.startswith(("http://", "https://")):
        return False
    for pattern in BLOCKED_NEWS_URL_PATTERNS:
        if pattern.search(text):
            return False
    try:
        host = (urlparse(text).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host in BLOCKED_NEWS_DOMAINS:
        return False
    for blocked in BLOCKED_NEWS_DOMAINS:
        if host == blocked or host.endswith(f".{blocked}"):
            return False
    return True


def extract_insight_from_content(content: str) -> str:
    """从四段式 content 中提取商业洞察作为 insight 兜底。"""
    if not content:
        return ""
    normalized = content.replace("\\n", "\n")
    match = re.search(r"【商业洞察】[：:]\s*(.+?)(?:\n【|$)", normalized, re.DOTALL)
    if match:
        return match.group(1).strip()[:150]
    return normalized.strip()[:150]


def count_ranking_hallucinations(rankings: list) -> dict[str, int]:
    """统计榜单中的幻觉演员与可疑厂牌数量。"""
    actor_hits = 0
    studio_hits = 0
    for r in rankings:
        title = getattr(r, "title", "") or (r.get("title") if isinstance(r, dict) else "")
        female = getattr(r, "female_lead", "") if not isinstance(r, dict) else r.get("female_lead", "")
        male = getattr(r, "male_lead", "") if not isinstance(r, dict) else r.get("male_lead", "")
        studio = getattr(r, "production_house", "") if not isinstance(r, dict) else r.get("production_house", "")
        if is_hallucinated_actor_name(female) or is_hallucinated_actor_name(male):
            actor_hits += 1
        if is_suspicious_studio_name(studio):
            studio_hits += 1
    return {"actor_hits": actor_hits, "studio_hits": studio_hits, "titles_checked": len(rankings)}
