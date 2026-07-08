"""
演员解析器：组合缓存查询、红果详情页爬虫、Kimi 批量搜索，生成搜索上下文。
"""
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from utils.title_matcher import build_title_metadata_indexes, lookup_hongguo_metadata

from .cache_adapter import DramaCache
from .metadata_fetcher import HongguoDetailFetcher

logger = logging.getLogger(__name__)

# 短剧演员搜索词（按 AGENTS.md 多轮检索策略，聚焦垂类平台）
_SHORT_DRAMA_ACTOR_QUERIES = (
    "短剧《{title}》主演女演员男主角 红果",
    "《{title}》短剧演员阵容 DataEye 红果",
    "短剧 {title} 主演是谁 抖音 小红书",
)


class DramaSearcher(Protocol):
    """短剧搜索器协议"""

    def __call__(self, query: str) -> str:
        """返回搜索结果文本"""
        ...


class ActorResolver:
    """
    演员/元数据解析器。

    解析策略（按优先级）：
    1. 本地 SQLite 缓存
    2. 红果剧名匹配 series_id → 详情页爬虫（/detail?series_id=）
    3. Kimi 短剧垂类搜索（按剧逐条，禁止泛化明星）
    """

    def __init__(
        self,
        cache: DramaCache,
        fetcher: HongguoDetailFetcher,
        searcher: Optional[DramaSearcher] = None,
        max_process: int = 20,
        max_search: int = 8,
        sleep_seconds: float = 0.5,
        hongguo_catalog: Optional[List[Dict[str, Any]]] = None,
    ):
        self.cache = cache
        self.fetcher = fetcher
        self.searcher = searcher
        self.max_process = max_process
        self.max_search = max_search
        self.sleep_seconds = sleep_seconds
        self._hongguo_catalog = hongguo_catalog
        self._hongguo_indexes: Optional[
            Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], list]
        ] = None

    def resolve(self, rankings: List[Any]) -> tuple[str, List[Dict[str, Any]], Dict[str, int]]:
        """
        解析演员/元数据。

        Returns:
            (search_context, missing_dramas, stats)
        """
        search_context = ""
        missing_dramas: List[Dict[str, Any]] = []
        stats = {
            "cache_hits": 0,
            "crawler_hits": 0,
            "series_id_resolved": 0,
            "missing": 0,
        }

        for idx, drama in enumerate(rankings[: self.max_process]):
            title, series_id, tags = self._extract_drama_info(drama)
            if not title:
                continue

            if not series_id:
                resolved_id = self._resolve_series_id(title)
                if resolved_id:
                    series_id = resolved_id
                    stats["series_id_resolved"] += 1
                    logger.info("《%s》通过红果剧名匹配到 series_id=%s", title, series_id)

            # 1. 本地缓存
            cached = self.cache.get(series_id) if series_id else None
            if cached:
                stats["cache_hits"] += 1
                search_context += self.cache.format_context(title, cached)
                logger.info("《%s》缓存命中", title)
                continue

            # 2. 红果详情页爬虫
            if series_id:
                detail = self.fetcher.fetch(series_id)
                if detail:
                    stats["crawler_hits"] += 1
                    self._save_detail_to_cache(series_id, title, detail, tags)
                    search_context += self.fetcher.format_context(title, detail)
                    logger.info("《%s》红果详情页爬取成功", title)
                    time.sleep(self.sleep_seconds)
                    continue

            missing_dramas.append({"title": title, "rank": idx + 1, "series_id": series_id})
            search_context += f"\n【剧目：《{title}》演员信息缺失，待短剧垂类搜索补充】\n"

        if missing_dramas and self.searcher:
            search_context += self._search_missing_dramas(missing_dramas)

        stats["missing"] = len(missing_dramas)
        logger.info(
            "演员解析完成: 缓存=%s, 爬虫=%s, series_id回填=%s, 待搜索=%s",
            stats["cache_hits"],
            stats["crawler_hits"],
            stats["series_id_resolved"],
            stats["missing"],
        )
        return search_context, missing_dramas, stats

    def _get_hongguo_indexes(self):
        if self._hongguo_indexes is not None:
            return self._hongguo_indexes
        if not self._hongguo_catalog:
            return None
        self._hongguo_indexes = build_title_metadata_indexes(self._hongguo_catalog)
        return self._hongguo_indexes

    def _resolve_series_id(self, title: str) -> str:
        indexes = self._get_hongguo_indexes()
        if not indexes:
            return ""
        meta = lookup_hongguo_metadata(title, *indexes)
        if meta and meta.get("series_id"):
            return str(meta["series_id"])
        return ""

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
        """对缺失演员信息的剧目进行短剧垂类搜索（小批量、多轮 query）。"""
        chunks: List[str] = []
        for drama in missing_dramas[: self.max_search]:
            title = drama.get("title", "")
            if not title:
                continue
            drama_context = f"\n【《{title}》短剧演员搜索结果】\n"
            for template in _SHORT_DRAMA_ACTOR_QUERIES[:2]:
                query = template.format(title=title)
                try:
                    result = self.searcher(query)
                    if result:
                        drama_context += f"- 查询「{query}」:\n{result[:1200]}\n"
                        break
                except Exception as exc:
                    logger.warning("短剧演员搜索失败 《%s》: %s", title, exc)
            chunks.append(drama_context)

        if chunks:
            logger.info("Kimi 短剧演员搜索完成: %d 部", len(chunks))
        return "".join(chunks)
