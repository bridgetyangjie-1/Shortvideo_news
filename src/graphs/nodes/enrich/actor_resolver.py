"""
演员解析器：组合缓存查询、红果详情页爬虫、剧名搜索、Kimi 批量搜索。
"""
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Protocol

from tools.hongguo_series_search import extract_series_id_from_text, resolve_series_id

from .cache_adapter import DramaCache
from .metadata_fetcher import HongguoDetailFetcher

logger = logging.getLogger(__name__)

_SHORT_DRAMA_ACTOR_QUERIES = (
    "短剧《{title}》主演女演员男主角 红果 DataEye",
    "《{title}》短剧演员阵容 红果 抖音",
)

_SERIES_ID_QUERIES = (
    "红果短剧《{title}》 novelquickapp.com detail series_id",
    "《{title}》短剧 红果 详情页 链接",
)


class DramaSearcher(Protocol):
    def __call__(self, query: str) -> str:
        ...


class ActorResolver:
    """
    解析策略：
    1. 本地缓存
    2. 剧名搜索 series_id（catalog 精确匹配 → Kimi 搜链接）
    3. 红果 /detail?series_id= 演职员表
    4. Kimi 短剧垂类演员搜索
    """

    def __init__(
        self,
        cache: DramaCache,
        fetcher: HongguoDetailFetcher,
        searcher: Optional[DramaSearcher] = None,
        max_process: int = 20,
        max_search: int = 10,
        max_series_search: int = 8,
        sleep_seconds: float = 0.5,
        hongguo_catalog: Optional[List[Dict[str, Any]]] = None,
    ):
        self.cache = cache
        self.fetcher = fetcher
        self.searcher = searcher
        self.max_process = max_process
        self.max_search = max_search
        self.max_series_search = max_series_search
        self.sleep_seconds = sleep_seconds
        self._hongguo_catalog = hongguo_catalog or []

    def resolve(self, rankings: List[Any]) -> tuple[str, List[Dict[str, Any]], Dict[str, int]]:
        search_context = ""
        missing_dramas: List[Dict[str, Any]] = []
        stats = {
            "cache_hits": 0,
            "crawler_hits": 0,
            "series_id_resolved": 0,
            "series_id_search": 0,
            "missing": 0,
        }

        for idx, drama in enumerate(rankings[: self.max_process]):
            title, series_id, tags = self._extract_drama_info(drama)
            if not title:
                continue

            if not series_id:
                series_id = self._resolve_series_id(title, stats)
                if series_id:
                    self._write_series_id(drama, series_id)

            if series_id:
                cached = self.cache.get(series_id)
                if cached:
                    stats["cache_hits"] += 1
                    search_context += self.cache.format_context(title, cached)
                    continue

                detail = self.fetcher.fetch(series_id)
                if detail:
                    stats["crawler_hits"] += 1
                    self._save_detail_to_cache(series_id, title, detail, tags)
                    search_context += self.fetcher.format_context(title, detail)
                    time.sleep(self.sleep_seconds)
                    continue

            missing_dramas.append({"title": title, "rank": idx + 1, "series_id": series_id})
            search_context += f"\n【剧目：《{title}》演员信息缺失，禁止编造演员名】\n"

        if missing_dramas and self.searcher:
            search_context += self._search_missing_dramas(missing_dramas)

        stats["missing"] = len(missing_dramas)
        logger.info("演员解析完成: %s", stats)
        return search_context, missing_dramas, stats

    def _resolve_series_id(self, title: str, stats: Dict[str, int]) -> str:
        # 优先 Kimi 剧名搜索（周榜剧通常不在推荐 catalog）
        if self.searcher and stats["series_id_search"] < self.max_series_search:
            for template in _SERIES_ID_QUERIES:
                try:
                    result = self.searcher(template.format(title=title))
                    stats["series_id_search"] += 1
                    sid = extract_series_id_from_text(result)
                    if sid:
                        stats["series_id_resolved"] += 1
                        logger.info("《%s》Kimi 解析 series_id=%s", title, sid)
                        return sid
                except Exception as exc:
                    logger.warning("Kimi series_id 搜索失败 《%s》: %s", title, exc)

        sid = resolve_series_id(title, catalog=self._hongguo_catalog, searcher=None)
        if sid:
            stats["series_id_resolved"] += 1
            logger.info("《%s》catalog 剧名搜索 series_id=%s", title, sid)
        return sid

    @staticmethod
    def _write_series_id(drama: Any, series_id: str) -> None:
        if isinstance(drama, dict):
            drama["series_id"] = series_id
        elif hasattr(drama, "series_id"):
            setattr(drama, "series_id", series_id)

    def _extract_drama_info(self, drama: Any) -> tuple[str, str, List[str]]:
        title = ""
        series_id = ""
        tags: List[str] = []
        if hasattr(drama, "title"):
            title = getattr(drama, "title", "") or ""
            series_id = getattr(drama, "series_id", "") or ""
            tags = getattr(drama, "tags", []) or []
        elif isinstance(drama, dict):
            title = drama.get("title", "") or ""
            series_id = drama.get("series_id", "") or ""
            tags = drama.get("tags", []) or []
        return title, series_id, tags

    def _save_detail_to_cache(
        self,
        series_id: str,
        title: str,
        detail: Dict[str, Any],
        tags: List[str],
    ) -> None:
        actors_dict: Dict[str, str] = {
            "female_lead": detail.get("female_lead", "") or "",
            "male_lead": detail.get("male_lead", "") or "",
        }
        actors_list = detail.get("actors")
        if isinstance(actors_list, list) and actors_list:
            if not actors_dict["female_lead"]:
                actors_dict["female_lead"] = str(actors_list[0])
            if not actors_dict["male_lead"] and len(actors_list) > 1:
                actors_dict["male_lead"] = str(actors_list[1])

        self.cache.save(
            series_id=series_id,
            title=title,
            actors=actors_dict,
            studio=detail.get("studio", ""),
            release_date=detail.get("release_date", ""),
            tags=tags,
            data_source="hongguo",
        )

    def _search_missing_dramas(self, missing_dramas: List[Dict[str, Any]]) -> str:
        chunks: List[str] = []
        for drama in missing_dramas[: self.max_search]:
            title = drama.get("title", "")
            if not title:
                continue
            block = f"\n【《{title}》短剧演员搜索结果】\n"
            for template in _SHORT_DRAMA_ACTOR_QUERIES:
                query = template.format(title=title)
                try:
                    result = self.searcher(query)
                    if result:
                        block += f"- {query}:\n{result[:1500]}\n"
                except Exception as exc:
                    logger.warning("演员搜索失败 《%s》: %s", title, exc)
            chunks.append(block)
        if chunks:
            logger.info("Kimi 短剧演员搜索完成: %d 部", len(chunks))
        return "".join(chunks)
