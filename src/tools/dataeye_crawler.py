"""
DataEye 短剧热力榜爬虫
用于交叉验证红果数据
"""
import urllib.request
import json
import logging
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

DATAEYE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.dataeye.cn/",
}


def fetch_dataeye_rankings(top_n: int = 30) -> List[Dict[str, Any]]:
    """
    爬取 DataEye 短剧热力榜
    注意：DataEye 可能有反爬，需要测试
    
    Args:
        top_n: 获取前N条数据
        
    Returns:
        榜单数据列表
    """
    try:
        # DataEye 热力榜 API（需要根据实际情况调整）
        # 注意：这个URL可能需要根据DataEye实际接口调整
        url = "https://www.dataeye.cn/api/shortDrama/ranking"
        
        req = urllib.request.Request(url, headers=DATAEYE_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        # 解析DataEye返回的数据结构
        if data.get("success") and data.get("data"):
            rankings = []
            for i, item in enumerate(data["data"].get("list", [])[:top_n]):
                rankings.append({
                    "rank": i + 1,
                    "title": item.get("drama_name", item.get("title", "")),
                    "heat": item.get("heat_index", item.get("heat", 0)),
                    "platform": item.get("platform", "多平台"),
                    "tags": item.get("tags", []),
                    "data_source": "dataeye"
                })
            return rankings
        
        logger.warning(f"DataEye返回数据格式异常: {data}")
        return []
        
    except urllib.error.HTTPError as e:
        logger.warning(f"DataEye HTTP错误: {e.code}")
        return []
    except urllib.error.URLError as e:
        logger.warning(f"DataEye URL错误: {e.reason}")
        return []
    except json.JSONDecodeError as e:
        logger.warning(f"DataEye JSON解析失败: {e}")
        return []
    except Exception as e:
        logger.warning(f"DataEye爬取失败: {e}")
        return []


def fetch_dataeye_via_search(keyword: str = "短剧热力榜", top_n: int = 30) -> List[Dict[str, Any]]:
    """
    通过搜索页面爬取DataEye数据（备用方案）
    
    Args:
        keyword: 搜索关键词
        top_n: 获取前N条数据
        
    Returns:
        榜单数据列表
    """
    try:
        # 尝试访问DataEye的短剧榜单页面
        url = f"https://www.dataeye.cn/shortdrama/ranking"
        
        req = urllib.request.Request(url, headers=DATAEYE_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8")
        
        # 尝试从HTML中提取数据
        # DataEye可能使用SSR，数据在script标签中
        import re
        
        # 查找JSON数据
        json_pattern = r'window\.__INITIAL_STATE__\s*=\s*({.*?});'
        match = re.search(json_pattern, html, re.DOTALL)
        
        if match:
            data = json.loads(match.group(1))
            rankings = []
            list_data = data.get("ranking", {}).get("list", [])
            
            for i, item in enumerate(list_data[:top_n]):
                rankings.append({
                    "rank": i + 1,
                    "title": item.get("dramaName", item.get("title", "")),
                    "heat": item.get("heatIndex", item.get("heat", 0)),
                    "platform": item.get("platform", "多平台"),
                    "tags": item.get("tags", []),
                    "data_source": "dataeye"
                })
            return rankings
        
        logger.warning("DataEye页面未找到数据")
        return []
        
    except Exception as e:
        logger.warning(f"DataEye备用爬取失败: {e}")
        return []


def cross_validate_with_hongguo(
    hongguo_data: List[Dict[str, Any]], 
    dataeye_data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    用DataEye数据交叉验证红果数据
    
    Args:
        hongguo_data: 红果榜单数据
        dataeye_data: DataEye榜单数据
        
    Returns:
        融合后的数据，包含置信度评分
    """
    if not dataeye_data:
        # 没有DataEye数据，保持红果数据不变
        for drama in hongguo_data:
            drama["confidence_score"] = 0.7
            drama["cross_validated"] = False
        return hongguo_data
    
    # 建立DataEye标题索引
    dataeye_titles = {d["title"]: d for d in dataeye_data if d.get("title")}
    
    result = []
    for hg_drama in hongguo_data:
        title = hg_drama.get("title", "")
        
        # 检查是否在DataEye也有排名
        de_drama = dataeye_titles.get(title)
        
        if de_drama:
            # 交叉验证成功，提升置信度
            merged = hg_drama.copy()
            merged["confidence_score"] = 0.95
            merged["cross_validated"] = True
            merged["dataeye_rank"] = de_drama.get("rank")
            merged["dataeye_heat"] = de_drama.get("heat", 0)
            result.append(merged)
        else:
            # 只有红果数据
            merged = hg_drama.copy()
            merged["confidence_score"] = 0.7
            merged["cross_validated"] = False
            result.append(merged)
    
    return result


def get_dataeye_supplement(
    hongguo_data: List[Dict[str, Any]], 
    top_n: int = 30
) -> List[Dict[str, Any]]:
    """
    获取DataEye补充数据（红果榜单中没有的剧）
    
    Args:
        hongguo_data: 红果榜单数据
        top_n: 获取前N条DataEye数据
        
    Returns:
        DataEye独有的榜单数据
    """
    dataeye_data = fetch_dataeye_rankings(top_n)
    
    if not dataeye_data:
        dataeye_data = fetch_dataeye_via_search(top_n=top_n)
    
    if not dataeye_data:
        return []
    
    # 红果已有的标题
    hongguo_titles = {d.get("title", "") for d in hongguo_data if d.get("title")}
    
    # 筛选DataEye独有的数据
    supplement = []
    for de_drama in dataeye_data:
        if de_drama.get("title") not in hongguo_titles:
            de_drama["confidence_score"] = 0.6
            de_drama["cross_validated"] = False
            de_drama["data_source"] = "dataeye"
            supplement.append(de_drama)
    
    return supplement
