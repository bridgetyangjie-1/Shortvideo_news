"""
演员解析器：组合缓存查询、红果详情页爬虫、剧名搜索、Kimi 批量搜索。
"""
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Protocol

from tools.hongguo_series_search import (
    batch_resolve_actors_via_search,
    batch_resolve_series_ids_via_search,
    resolve_series_id_from_catalog,
)

from .cache_adapter import DramaCache
from .metadata_fetcher import HongguoDetailFetcher

logger = logging.getLogger(__name__)


class DramaSearcher(Protocol):
    def __call__(self, query: str) -> str:
        ...

    def has_budget(self, min_calls: int = 4) -> bool:
        ...


class ActorResolver:
    """
    解析策略：
    1. 本地缓存（series_id / 剧名）
    2. 红果 catalog 剧名精确匹配
    3. 红果 /detail?series_id= 演职员表
    4. Kimi 批量搜索 series_id（最多 1 次）
    5. Kimi 批量搜索演员（最多 1 次）
    """

    def __init__(
        self,
        cache: DramaCache,
        fetcher: HongguoDetailFetcher,
        searcher: Optional[DramaSearcher] = None,
        max_process: int = 20,
        max_batch_titles: int = 12,
        sleep_seconds: float = 0.5,
        hongguo_catalog: Optional[List[Dict[str, Any]]] = None,
    ):
        self.cache = cache
        self.fetcher = fetcher
        self.searcher = searcher
        self.max_process = max_process
        self.max_batch_titles = max_batch_titles
        self.sleep_seconds = sleep_seconds
        self._hongguo_catalog = hongguo_catalog or []

    def resolve(self, rankings: List[Any]) -> tuple[str, List[Dict[str, Any]], Dict[str, int]]:
        search_context = ""
        missing_by_title: Dict[str, Dict[str, Any]] = {}
        stats = {
            "cache_hits": 0,
            "crawler_hits": 0,
            "series_id_resolved": 0,
            "series_id_search": 0,
            "actor_search": 0,
            "missing": 0,
        }

        processed = rankings[: self.max_process]

        for idx, drama in enumerate(processed):
            title, series_id, tags = self._extract_drama_info(drama)
            if not title:
                continue

            if not series_id:
                series_id = self._resolve_series_id_local(title, stats)
                if series_id:
                    self._write_series_id(drama, series_id)

            if series_id:
                detail_ctx = self._try_cache_or_crawl(title, series_id, tags, stats)
                if detail_ctx:
                    search_context += detail_ctx
                    continue

            missing_by_title[title] = {"title": title, "rank": idx + 1, "series_id": series_id}
            search_context += f"\n【剧目：《{title}》演员信息缺失，禁止编造演员名】\n"

        # 批量 Kimi 解析 series_id（最多 1 次）
        if missing_by_title and self._can_search():
            titles_need_sid = [
                title
                for title, item in missing_by_title.items()
                if not item.get("series_id")
            ]
            if titles_need_sid:
                stats["series_id_search"] = 1
                sid_map = batch_resolve_series_ids_via_search(
                    titles_need_sid[: self.max_batch_titles],
                    self.searcher,  # type: ignore[arg-type]
                )
                for drama in processed:
                    title, series_id, tags = self._extract_drama_info(drama)
                    if not title or series_id:
                        continue
                    new_sid = sid_map.get(title, "")
                    if not new_sid:
                        continue
                    stats["series_id_resolved"] += 1
                    self._write_series_id(drama, new_sid)
                    if title in missing_by_title:
                        missing_by_title[title]["series_id"] = new_sid
                    detail_ctx = self._try_cache_or_crawl(title, new_sid, tags, stats)
                    if detail_ctx:
                        search_context += detail_ctx
                        missing_by_title.pop(title, None)

        # 批量 Kimi 演员搜索（最多 1 次）
        if missing_by_title and self._can_search():
            titles = list(missing_by_title.keys())[: self.max_batch_titles]
            if titles:
                batch_ctx = batch_resolve_actors_via_search(titles, self.searcher)  # type: ignore[arg-type]
                if batch_ctx:
                    stats["actor_search"] = 1
                    search_context += f"\n【批量短剧演员搜索结果】\n{batch_ctx}\n"

        still_missing = list(missing_by_title.values())
        stats["missing"] = len(still_missing)
        logger.info("演员解析完成: %s", stats)
        return search_context, still_missing, stats

    def _can_search(self) -> bool:
        if not self.searcher:
            return False
        has_budget = getattr(self.searcher, "has_budget", None)
        if callable(has_budget):
            return bool(has_budget(4))
        return True

    def _resolve_series_id_local(self, title: str, stats: Dict[str, int]) -> str:
        """本地免费路径：剧名缓存 → catalog 精确匹配。"""
        cached = self.cache.get_by_title(title)
        if cached and cached.get("series_id"):
            stats["series_id_resolved"] += 1
            logger.info("《%s》剧名缓存命中 series_id=%s", title, cached["series_id"])
            return str(cached["series_id"])

        sid = resolve_series_id_from_catalog(title, self._hongguo_catalog)
        if sid:
            stats["series_id_resolved"] += 1
            logger.info("《%s》catalog 剧名搜索 series_id=%s", title, sid)
        return sid

    def _try_cache_or_crawl(
        self,
        title: str,
        series_id: str,
        tags: List[str],
        stats: Dict[str, int],
    ) -> str:
        cached = self.cache.get(series_id)
        if cached:
            stats["cache_hits"] += 1
            return self.cache.format_context(title, cached)

        detail = self.fetcher.fetch(series_id)
        if not detail:
            return ""

        stats["crawler_hits"] += 1
        self._save_detail_to_cache(series_id, title, detail, tags)
        time.sleep(self.sleep_seconds)
        return self.fetcher.format_context(title, detail)

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
