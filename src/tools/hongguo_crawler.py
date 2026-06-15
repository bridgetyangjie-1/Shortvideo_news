"""
红果短剧官网爬虫工具
直接抓取 novelquickapp.com 获取实时榜单数据
"""
import urllib.request
import urllib.error
import gzip
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 红果官网URL
HONGGUO_URL = "https://novelquickapp.com/"

# 请求头（模拟浏览器，避免反爬）
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


class HongguoCrawler:
    """红果短剧官网爬虫"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.headers = DEFAULT_HEADERS.copy()
    
    def fetch_homepage_list(self, max_count: int = 100) -> List[Dict[str, Any]]:
        """
        抓取红果官网首页榜单数据
        
        Args:
            max_count: 最大抓取数量，默认100条
            
        Returns:
            短剧列表，包含基础信息（剧名、封面、标签、集数等）
        """
        logger.info(f"开始抓取红果官网首页数据，目标数量: {max_count}")
        
        try:
            # 发送HTTP请求（不请求压缩，避免gzip解压问题）
            headers = self.headers.copy()
            headers["Accept-Encoding"] = "identity"  # 不压缩
            req = urllib.request.Request(HONGGUO_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                html = response.read().decode("utf-8", errors="ignore")
            
            logger.info(f"首页HTML获取成功，长度: {len(html)} 字符")
            
            # 提取 window._ROUTER_DATA
            router_data = self._extract_router_data(html)
            if not router_data:
                logger.error("无法提取 window._ROUTER_DATA")
                return []
            
            # 解析榜单数据
            drama_list = self._parse_drama_list(router_data, max_count)
            
            logger.info(f"成功解析 {len(drama_list)} 条短剧数据")
            return drama_list
            
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP错误: {e.code} - {e.reason}")
            return []
        except urllib.error.URLError as e:
            logger.error(f"URL错误: {e.reason}")
            return []
        except Exception as e:
            logger.error(f"抓取红果首页失败: {e}", exc_info=True)
            return []
    
    def _extract_router_data(self, html: str) -> Optional[Dict[str, Any]]:
        """从HTML中提取 window._ROUTER_DATA"""
        try:
            # 查找 window._ROUTER_DATA 的位置
            start_pattern = 'window._ROUTER_DATA = '
            start = html.find(start_pattern)
            if start == -1:
                logger.error("未找到 window._ROUTER_DATA")
                return None
            
            # 提取JSON字符串
            json_start = start + len(start_pattern)
            
            # 查找结束位置（</script> 标签前）
            end = html.find('</script>', json_start)
            if end == -1:
                logger.error("未找到 _ROUTER_DATA 结束位置")
                return None
            
            json_str = html[json_start:end].strip().rstrip(';')
            
            # 解析JSON
            data = json.loads(json_str)
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"解析JSON失败: {e}")
            return None
        except Exception as e:
            logger.error(f"提取 _ROUTER_DATA 失败: {e}")
            return None
    
    def _parse_drama_list(self, router_data: Dict[str, Any], max_count: int) -> List[Dict[str, Any]]:
        """解析榜单数据"""
        dramas = []
        
        try:
            # 数据路径: loaderData.page.homeData.detail.list
            list_data = (
                router_data.get("loaderData", {})
                .get("page", {})
                .get("homeData", {})
                .get("detail", {})
                .get("list", [])
            )
            
            if not list_data:
                logger.warning("榜单数据为空")
                return []
            
            logger.info(f"找到 {len(list_data)} 条原始数据")
            
            # 解析每条数据
            for i, item in enumerate(list_data[:max_count]):
                if not isinstance(item, dict):
                    continue
                
                drama = {
                    "rank": i + 1,
                    "series_id": item.get("series_id", ""),
                    "title": item.get("series_name", ""),
                    "cover": item.get("series_cover", ""),
                    "tags": item.get("tags", []),
                    "episodes": item.get("episode_right_text", ""),
                    "platform": "红果",
                    "source": "hongguo_direct",
                    # 详情字段（需要后续补充）
                    "female_lead": "",
                    "male_lead": "",
                    "studio": "",
                    "release_date": "",
                }
                dramas.append(drama)
            
            return dramas
            
        except Exception as e:
            logger.error(f"解析榜单数据失败: {e}", exc_info=True)
            return []
    
    def fetch_series_html(self, series_id: str) -> str:
        """获取详情页 HTML（供供应链提取使用）"""
        try:
            url = f"https://novelquickapp.com/series/{series_id}"
            headers = self.headers.copy()
            headers["Accept-Encoding"] = "identity"  # 不请求压缩，避免 gzip 解压问题
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def try_fetch_detail_api(self, series_id: str) -> Optional[Dict[str, Any]]:
        """
        尝试通过API获取详情（如果存在）

        Args:
            series_id: 剧集ID

        Returns:
            详情数据，如果不存在API则返回None
        """
        # 尝试几种可能的API格式
        api_urls = [
            f"https://novelquickapp.com/api/series/detail?series_id={series_id}",
            f"https://api.novelquickapp.com/series/detail/{series_id}",
            f"https://novelquickapp.com/api/v1/series/{series_id}",
        ]
        
        for api_url in api_urls:
            try:
                req = urllib.request.Request(api_url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    logger.info(f"成功通过API获取详情: {api_url}")
                    return data
            except Exception:
                continue
        
        # API不存在，返回None
        return None


def fetch_hongguo_data(max_count: int = 100) -> List[Dict[str, Any]]:
    """
    直接爬取红果官网数据（便捷函数）
    
    Args:
        max_count: 最大抓取数量，默认100条
        
    Returns:
        短剧列表
    """
    crawler = HongguoCrawler()
    return crawler.fetch_homepage_list(max_count)


def enrich_drama_detail(
    drama: Dict[str, Any],
    search_func,
    delay: float = 1.5
) -> Dict[str, Any]:
    """
    补充剧集详情（主演、工作室、上线时间）
    
    Args:
        drama: 剧集基础数据
        search_func: 搜索函数（如 Kimi 的 client.search）
        delay: 每次搜索后的延迟（秒），避免API限制
        
    Returns:
        补充详情后的剧集数据
    """
    title = drama.get("title", "")
    if not title:
        return drama
    
    logger.info(f"补充详情: 《{title}》")
    
    # 1. 尝试获取主演信息
    actor_query = f"短剧《{title}》主演女演员男主角女主角"
    try:
        actor_result = search_func(query=actor_query, max_results=3)
        drama["actor_search_result"] = actor_result[:500]  # 保留搜索结果供后续解析
        time.sleep(delay)
    except Exception as e:
        logger.warning(f"搜索演员信息失败: {e}")
    
    # 2. 尝试获取制作公司
    studio_query = f"短剧《{title}》制作公司工作室出品方"
    try:
        studio_result = search_func(query=studio_query, max_results=2)
        drama["studio_search_result"] = studio_result[:300]
        time.sleep(delay)
    except Exception as e:
        logger.warning(f"搜索工作室信息失败: {e}")
    
    # 3. 尝试获取上线时间
    date_query = f"短剧《{title}》上线时间首播日期播出时间"
    try:
        date_result = search_func(query=date_query, max_results=2)
        drama["date_search_result"] = date_result[:300]
        time.sleep(delay)
    except Exception as e:
        logger.warning(f"搜索上线时间失败: {e}")
    
    return drama


if __name__ == "__main__":
    # 测试爬虫
    print("测试红果爬虫...")
    dramas = fetch_hongguo_data(10)
    print(f"获取到 {len(dramas)} 条数据")
    if dramas:
        print("第一条数据:")
        print(json.dumps(dramas[0], ensure_ascii=False, indent=2))
