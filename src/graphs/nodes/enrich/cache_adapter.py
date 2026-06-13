"""
本地 SQLite 缓存适配器：封装 tools/cache_db 的读写。
"""
import logging
from typing import Any, Dict, Optional

from tools.cache_db import get_drama, save_drama

logger = logging.getLogger(__name__)


class DramaCache:
    """短剧信息本地缓存封装"""

    def get(self, series_id: str) -> Optional[Dict[str, Any]]:
        """查询缓存，返回缓存记录或 None。"""
        if not series_id:
            return None
        return get_drama(series_id)

    def save(
        self,
        series_id: str,
        title: str,
        actors: Dict[str, str],
        studio: str,
        release_date: str,
        tags: list,
        data_source: str = "hongguo",
    ) -> None:
        """保存短剧信息到缓存。"""
        if not series_id:
            return
        try:
            save_drama(
                series_id=series_id,
                title=title,
                actors=actors,
                studio=studio,
                release_date=release_date,
                tags=tags,
                data_source=data_source,
            )
        except Exception as exc:
            logger.warning("保存缓存失败 series_id=%s: %s", series_id, exc)

    def format_context(self, title: str, record: Dict[str, Any]) -> str:
        """将缓存记录格式化为搜索上下文文本。"""
        actors = record.get("actors") or {}
        actors_str = ", ".join(actors.values()) if actors else "未知"
        studio_str = record.get("studio", "未知")
        release_str = record.get("release_date", "")

        context = f"\n【剧目：《{title}》本地缓存数据】:\n"
        context += f"主演列表（按顺序，第一位为女主、第二位为男主）: {actors_str}\n"
        context += f"工作室: {studio_str}\n"
        if release_str:
            context += f"上线时间: {release_str}\n"
        return context
