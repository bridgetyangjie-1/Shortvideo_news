"""
红果详情页爬虫：获取演员、工作室、上线时间等元数据。
"""
import json
import logging
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DETAIL_URLS = (
    "https://novelquickapp.com/detail?series_id={series_id}",
    "https://hongguoduanju.com/detail?series_id={series_id}",
)
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Encoding": "identity",
}

# 红果详情页 HTML 中「演员名 + 饰 + 角色名」结构
_CAST_HTML_PATTERN = re.compile(
    r">([^<]{2,24})</[^>]+>\s*<[^>]+>饰\s*([^<]{1,16})</"
)
# _ROUTER_DATA / JSON 中常见的 nickname + sub_title:"饰 角色"
_CAST_JSON_PATTERN = re.compile(
    r'"nickname"\s*:\s*"([^"]{1,30})"\s*,\s*"sub_title"\s*:\s*"饰\s*([^"]{1,40})"'
)
_FEMALE_ROLE_HINTS = (
    "女", "娘", "妃", "小姐", "夫人", "妻", "妈", "母", "姐", "妹", "婆",
    "姗", "娇", "妮", "苗", "公主", "皇后", "媳", "嫂", "姑", "阿姨",
)
_MALE_ROLE_HINTS = (
    "男", "爷", "总", "哥", "夫", "爸", "父", "弟", "叔", "伯", "郎",
    "少", "王", "将", "侯", "爹", "爷们",
)


def _role_suggests_female(role: str) -> bool:
    return any(h in role for h in _FEMALE_ROLE_HINTS)


def _role_suggests_male(role: str) -> bool:
    return any(h in role for h in _MALE_ROLE_HINTS)


def parse_cast_from_html(html: str) -> List[Tuple[str, str]]:
    """从红果 /detail 页面 HTML / 内嵌 JSON 解析演职员表。"""
    if not html:
        return []
    pairs: List[Tuple[str, str]] = []
    seen: set[str] = set()

    for pattern in (_CAST_HTML_PATTERN, _CAST_JSON_PATTERN):
        for actor, role in pattern.findall(html):
            actor = actor.strip()
            role = role.strip()
            if not actor or actor in seen:
                continue
            # 过滤明显非演员字段
            if actor in {"红果", "抖音", "快手"} or len(actor) > 20:
                continue
            seen.add(actor)
            pairs.append((actor, role))
            # 详情页主演通常在前部；取前 12 对足够推断男女主
            if len(pairs) >= 12:
                return pairs
    return pairs


def assign_leads_from_cast(pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """根据角色名推断女主/男主；红果详情页通常男主在前、女主次之。"""
    leads = pairs[:6]
    female = ""
    male = ""

    for actor, role in leads:
        if not female and _role_suggests_female(role):
            female = actor
        if not male and _role_suggests_male(role):
            male = actor

    if not male and leads:
        male = leads[0][0]
    if not female:
        for actor, _ in leads[1:]:
            if actor != male:
                female = actor
                break
    # 若角色名都无性别线索，退回「前两位」
    if not female and len(leads) >= 2:
        female = leads[1][0]
    if not male and leads:
        male = leads[0][0]

    return {"female_lead": female, "male_lead": male}


class HongguoDetailFetcher:
    """红果短剧详情页元数据获取器（使用 /detail?series_id= 页面）。"""

    def fetch(self, series_id: str) -> Optional[Dict[str, Any]]:
        """
        尝试从红果详情页获取演员/工作室信息。
        返回: {"actors": [...], "female_lead": "", "male_lead": "", "studio": "", "release_date": ""}
        """
        series_id = str(series_id or "").strip()
        if not series_id:
            return None

        last_error: Optional[Exception] = None
        for url_tpl in _DETAIL_URLS:
            try:
                result = self._fetch_one(url_tpl.format(series_id=series_id), series_id)
                if result:
                    return result
            except Exception as exc:
                last_error = exc
                continue

        if last_error:
            logger.warning("爬取红果详情页失败 series_id=%s: %s", series_id, last_error)
        return None

    def _fetch_one(self, url: str, series_id: str) -> Optional[Dict[str, Any]]:
        req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as response:
            html = response.read().decode("utf-8", errors="ignore")

        if len(html) < 500:
            return None

        result = self._extract_from_router_json(html)
        cast_pairs = parse_cast_from_html(html)

        if cast_pairs:
            actor_names = [name for name, _ in cast_pairs]
            leads = assign_leads_from_cast(cast_pairs)
            if not result:
                result = {
                    "actors": actor_names,
                    "female_lead": leads["female_lead"],
                    "male_lead": leads["male_lead"],
                    "studio": "",
                    "release_date": "",
                }
            else:
                result["actors"] = actor_names or result.get("actors", [])
                if not result.get("female_lead"):
                    result["female_lead"] = leads["female_lead"]
                if not result.get("male_lead"):
                    result["male_lead"] = leads["male_lead"]

        if result and (result.get("actors") or result.get("studio") or result.get("female_lead") or result.get("male_lead")):
            logger.info(
                "红果详情页爬取成功: series_id=%s actors=%s",
                series_id,
                (result.get("actors") or [])[:3],
            )
            return result
        return None

    def _extract_from_router_json(self, html: str) -> Optional[Dict[str, Any]]:
        """尝试从 _ROUTER_DATA JSON 提取演员/厂牌（兼容旧结构）。"""
        start = html.find("window._ROUTER_DATA = ")
        end = html.find("</script>", start)
        if start < 0 or end < 0:
            return None

        try:
            json_str = html[start + len("window._ROUTER_DATA = ") : end].strip().rstrip(";")
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return None

        page_data = data.get("loaderData", {}).get("page", {}) or {}
        # 新版可能挂在其他 key
        if not page_data:
            loader = data.get("loaderData") or {}
            for value in loader.values():
                if isinstance(value, dict) and any(
                    k in value for k in ("detail", "seriesDetail", "dramaDetail", "homeData")
                ):
                    page_data = value
                    break

        detail_data = None
        for key in ("detail", "seriesDetail", "dramaDetail"):
            if key in page_data and isinstance(page_data[key], dict):
                detail_data = page_data[key]
                break
        if not detail_data:
            home_detail = (page_data.get("homeData") or {}).get("detail")
            if isinstance(home_detail, dict) and home_detail.keys() - {"list"}:
                detail_data = home_detail

        if not detail_data:
            return None

        result: Dict[str, Any] = {
            "actors": [],
            "female_lead": "",
            "male_lead": "",
            "studio": "",
            "release_date": "",
        }

        for actor_key in ("actors", "performer", "cast", "role_list", "actor_list"):
            raw = detail_data.get(actor_key)
            if isinstance(raw, list) and raw:
                if isinstance(raw[0], dict):
                    names = []
                    for item in raw:
                        name = (
                            item.get("name")
                            or item.get("actor_name")
                            or item.get("nickname")
                            or ""
                        )
                        if name:
                            names.append(str(name))
                    result["actors"] = names
                else:
                    result["actors"] = [str(x) for x in raw if x]
                break

        for studio_key in ("studio", "production", "company", "production_company", "producer"):
            if detail_data.get(studio_key):
                result["studio"] = str(detail_data[studio_key])
                break

        for date_key in ("release_date", "online_time", "publish_date", "create_time"):
            if detail_data.get(date_key):
                result["release_date"] = str(detail_data[date_key])
                break

        if result["actors"]:
            leads = assign_leads_from_cast([(a, "") for a in result["actors"][:4]])
            result["female_lead"] = leads["female_lead"]
            result["male_lead"] = leads["male_lead"]

        if result["actors"] or result["studio"]:
            return result
        return None

    def format_context(self, title: str, detail: Dict[str, Any]) -> str:
        """将详情数据格式化为搜索上下文文本。"""
        actors = detail.get("actors") or []
        female = detail.get("female_lead", "")
        male = detail.get("male_lead", "")
        if not female and actors:
            female = actors[0]
        if not male and len(actors) > 1:
            male = actors[1]
        studio_str = detail.get("studio", "") or "未知"
        release_str = detail.get("release_date", "")

        context = f"\n【剧目：《{title}》红果详情页数据（短剧垂类演员）】:\n"
        context += f"女主: {female or '未标注'}\n"
        context += f"男主: {male or '未标注'}\n"
        if actors:
            context += f"演职员表: {', '.join(str(a) for a in actors[:6])}\n"
        context += f"制片方: {studio_str}\n"
        if release_str:
            context += f"上线时间: {release_str}\n"
        return context
