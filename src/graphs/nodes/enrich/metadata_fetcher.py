"""
红果详情页爬虫：获取演员、工作室、上线时间等元数据。
"""
import json
import logging
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class HongguoDetailFetcher:
    """红果短剧详情页元数据获取器"""

    def fetch(self, series_id: str) -> Optional[Dict[str, Any]]:
        """
        尝试从红果详情页获取演员/工作室信息
        返回: {"actors": [...], "studio": "...", "release_date": "..."} 或 None
        """
        if not series_id:
            return None

        try:
            url = f"https://novelquickapp.com/series/{series_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")

            start = html.find('window._ROUTER_DATA = ')
            end = html.find('</script>', start)
            if start < 0 or end < 0:
                return None

            json_str = html[start + len('window._ROUTER_DATA = '):end].strip().rstrip(';')
            data = json.loads(json_str)

            page_data = data.get('loaderData', {}).get('page', {})

            detail_data = None
            for key in ['detail', 'seriesDetail', 'dramaDetail']:
                if key in page_data:
                    detail_data = page_data[key]
                    break

            if not detail_data:
                return None

            result: Dict[str, Any] = {
                "actors": [],
                "studio": "",
                "release_date": ""
            }

            if 'actors' in detail_data:
                result["actors"] = detail_data['actors']
            elif 'performer' in detail_data:
                result["actors"] = detail_data['performer']
            elif 'cast' in detail_data:
                result["actors"] = detail_data['cast']

            for studio_key in ['studio', 'production', 'company', 'production_company']:
                if studio_key in detail_data and detail_data[studio_key]:
                    result["studio"] = detail_data[studio_key]
                    break

            for date_key in ['release_date', 'online_time', 'publish_date', 'create_time']:
                if date_key in detail_data and detail_data[date_key]:
                    result["release_date"] = str(detail_data[date_key])
                    break

            if result["actors"] or result["studio"]:
                logger.info("红果详情页爬取成功: series_id=%s", series_id)
                return result

            return None

        except Exception as exc:
            logger.warning("爬取红果详情页失败: %s", exc)
            return None

    def format_context(self, title: str, detail: Dict[str, Any]) -> str:
        """将详情数据格式化为搜索上下文文本。"""
        actors_str = ", ".join(detail.get("actors", [])) if detail.get("actors") else "未知"
        studio_str = detail.get("studio", "未知")
        release_str = detail.get("release_date", "")

        context = f"\n【剧目：《{title}》红果详情页数据】:\n"
        context += f"主演列表（按顺序，第一位为女主、第二位为男主）: {actors_str}\n"
        context += f"工作室: {studio_str}\n"
        if release_str:
            context += f"上线时间: {release_str}\n"
        return context
