"""
演员解析器：组合缓存查询、红果详情页爬虫、Kimi 批量搜索，生成搜索上下文。
"""
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Protocol

from .cache_adapter import DramaCache
from .metadata_fetcher import HongguoDetailFetcher

logger = logging.getLogger(__name__)


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
    2. 红果详情页爬虫
    3. Kimi 批量搜索（可选）
    """

    def __init__(
        self,
        cache: DramaCache,
        fetcher: HongguoDetailFetcher,
        searcher: Optional[DramaSearcher] = None,
        max_process: int = 20,
        max_search: int = 10,
        sleep_seconds: float = 0.5,
    ):
        self.cache = cache
        self.fetcher = fetcher
        self.searcher = searcher
        self.max_process = max_process
        self.max_search = max_search
        self.sleep_seconds = sleep_seconds

    def resolve(self, rankings: List[Any]) -> tuple[str, List[Dict[str, Any]], Dict[str, int]]:
        """
        解析演员/元数据。

        Returns:
            (search_context, missing_dramas, stats)
            - search_context: 供 DeepSeek 使用的检索上下文文本
            - missing_dramas: 需要 Kimi 搜索补充的剧目列表
            - stats: {"cache_hits": int, "crawler_hits": int, "missing": int}
        """
        search_context = ""
        missing_dramas: List[Dict[str, Any]] = []
        stats = {"cache_hits": 0, "crawler_hits": 0, "missing": 0}

        for idx, drama in enumerate(rankings[: self.max_process]):
            title, series_id, tags = self._extract_drama_info(drama)
            if not title:
                continue

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
                    logger.info("《%s》爬取成功并缓存", title)
                    time.sleep(self.sleep_seconds)
                    continue

            # 3. 记录待搜索
            missing_dramas.append({"title": title, "rank": idx + 1})
            search_context += f"\n【剧目：《{title}》需要补充演员信息】\n"

        # 4. Kimi 批量搜索补充
        if missing_dramas and self.searcher:
            search_context += self._search_missing(missing_dramas)

        stats["missing"] = len(missing_dramas)
        logger.info(
            "演员解析完成: 缓存命中=%s, 爬虫补充=%s, 待搜索=%s",
            stats["cache_hits"],
            stats["crawler_hits"],
            stats["missing"],
        )
        return search_context, missing_dramas, stats

    def _extract_drama_info(self, drama: Any) -> tuple[str, str, List[str]]:
        """统一从 Pydantic 对象或字典提取剧名、series_id、标签。"""
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
        """将爬虫获取的详情保存到本地缓存。"""
        actors_dict: Dict[str, str] = {}
        actors_list = detail.get("actors")
        if isinstance(actors_list, list) and actors_list:
            actors_dict["female_lead"] = actors_list[0]
            if len(actors_list) > 1:
                actors_dict["male_lead"] = actors_list[1]

        self.cache.save(
            series_id=series_id,
            title=title,
            actors=actors_dict,
            studio=detail.get("studio", ""),
            release_date=detail.get("release_date", ""),
            tags=tags,
            data_source="hongguo",
        )

    def _search_missing(self, missing_dramas: List[Dict[str, Any]]) -> str:
        """对缺失演员信息的剧目进行批量搜索。"""
        titles = [f"《{d['title']}》" for d in missing_dramas[: self.max_search]]
        query = f"短剧演员信息查询，请告诉我以下短剧的主演（女主男主）和制作公司：{', '.join(titles)}"

        try:
            result = self.searcher(query)
            logger.info("Kimi批量搜索成功")
            return f"\n【Kimi批量搜索结果】:\n{result[:3000]}\n"
        except Exception as exc:
            logger.warning("Kimi批量搜索失败: %s", exc)
            return ""
