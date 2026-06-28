"""
热门内容频道完整生成脚本
1. 抓取三个平台原始数据
2. 用 DeepSeek/本地规则生成 200 字摘要和标签
3. 输出到 assets/data/hot_content/
"""
import gzip
import json
import logging
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# 将 src 加入路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tools.hot_content_fetcher import fetch_all_raw
from tools.hot_content_analyzer import HotContentAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_index(hot_content_dir: Path) -> dict:
    """加载历史索引"""
    index_file = hot_content_dir / "index.json"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"weeks": []}


def _safe_filename(title: str, max_len: int = 40) -> str:
    """把标题转换成安全的文件名"""
    title = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", title)
    title = re.sub(r"_+", "_", title).strip("_")
    if len(title) > max_len:
        title = title[:max_len]
    return title or "cover"


def _guess_ext(content_type: str, url: str) -> str:
    """根据 Content-Type 或 URL 推断图片扩展名"""
    if content_type:
        ct = content_type.lower()
        if "png" in ct:
            return ".png"
        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"
    # 从 URL 推断
    path = urlparse(url).path.lower()
    for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        if path.endswith(ext):
            return ".png" if ext == ".jpeg" else ext
    return ".jpg"


def _download_cover(cover_url: str, platform_key: str, rank: int, title: str, covers_dir: Path, timeout: int = 20) -> str:
    """
    下载封面图到本地 covers 目录，返回相对路径（相对于 assets/index.html）。
    下载失败则返回原始 URL。
    """
    if not cover_url:
        return ""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }
    # 晋江图片需要 Referer
    if "jjwxc" in cover_url:
        headers["Referer"] = "https://www.jjwxc.net/"

    try:
        req = urllib.request.Request(cover_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
            if not data or response.status != 200:
                return cover_url

        # 晋江图片服务器可能返回 gzip 压缩的图片，需要解压
        if data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
                logger.info(f"封面数据已 gzip 解压: {len(data)} bytes")
            except Exception as e:
                logger.warning(f"gzip 解压失败: {e}")

        # 根据实际文件魔数校正扩展名
        ext = _guess_ext(content_type, cover_url)
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif data[:2] == b"\xff\xd8":
            ext = ".jpg"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = ".webp"

        safe_title = _safe_filename(title)
        filename = f"{platform_key}_{rank:02d}_{safe_title}{ext}"
        cover_path = covers_dir / filename
        with open(cover_path, "wb") as f:
            f.write(data)

        logger.info(f"封面已下载: {filename} ({len(data)} bytes)")
        # 相对路径：相对于 assets/index.html
        return f"./data/hot_content/covers/{filename}"
    except Exception as e:
        logger.warning(f"封面下载失败，保留原 URL: {cover_url}, 错误: {e}")
        return cover_url


def download_covers(final_data: dict, hot_content_dir: Path) -> dict:
    """遍历数据并下载所有封面图到本地"""
    covers_dir = hot_content_dir / "covers"
    covers_dir.mkdir(exist_ok=True)

    for section in final_data.get("sections", []):
        platform_key = section.get("platform_key", "unknown")
        for item in section.get("items", []):
            cover_url = item.get("cover_url", "")
            if not cover_url or cover_url.startswith("./data/"):
                continue
            local_url = _download_cover(
                cover_url,
                platform_key,
                item.get("rank", 0),
                item.get("title", ""),
                covers_dir,
            )
            item["cover_url"] = local_url

    return final_data


def save_index(hot_content_dir: Path, data_date: str, week_label: str):
    """更新历史索引"""
    index = load_index(hot_content_dir)
    weeks = index.get("weeks", [])

    # 去重：如果已有该周，先移除
    weeks = [w for w in weeks if w.get("data_date") != data_date]

    # 插入到最前面
    weeks.insert(0, {
        "data_date": data_date,
        "week_label": week_label,
        "file": f"weekly/{data_date}.json",
    })

    # 保留最近 52 周
    weeks = weeks[:52]

    index["weeks"] = weeks

    index_file = hot_content_dir / "index.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    logger.info(f"索引已更新: {index_file}")


def main():
    """主入口"""
    # 1. 抓取原始数据
    logger.info("== 步骤 1/3: 抓取原始数据 ==")
    raw_data = fetch_all_raw()

    # 2. LLM 分析
    logger.info("== 步骤 2/3: 生成摘要和标签 ==")
    analyzer = HotContentAnalyzer(batch_size=5)

    analyzed_sections = []
    for section in raw_data["sections"]:
        analyzed_items = analyzer.analyze_items(section["items"])
        analyzed_sections.append({
            **section,
            "items": analyzed_items,
        })

    final_data = {
        **raw_data,
        "sections": analyzed_sections,
    }

    # 3. 准备输出目录并下载封面图到本地（避免外链防盗链，如晋江）
    logger.info("== 步骤 3/4: 下载封面图到本地 ==")
    hot_content_dir = PROJECT_ROOT / "assets" / "data" / "hot_content"
    hot_content_dir.mkdir(parents=True, exist_ok=True)
    final_data = download_covers(final_data, hot_content_dir)

    # 4. 输出到 assets/data/hot_content/
    logger.info("== 步骤 4/4: 保存最终 JSON ==")
    weekly_dir = hot_content_dir / "weekly"
    weekly_dir.mkdir(exist_ok=True)

    data_date = final_data["data_date"]

    # latest.json
    latest_file = hot_content_dir / "latest.json"
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    logger.info(f"latest.json 已保存: {latest_file}")

    # weekly/YYYY-MM-DD.json
    weekly_file = weekly_dir / f"{data_date}.json"
    with open(weekly_file, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    logger.info(f"周归档已保存: {weekly_file}")

    # index.json
    save_index(hot_content_dir, data_date, final_data["week_label"])

    logger.info("\n热门内容频道生成完成:")
    logger.info(f"  data_date: {data_date}")
    logger.info(f"  week_label: {final_data['week_label']}")
    logger.info(f"  total_items: {final_data['total_items']}")
    for section in final_data["sections"]:
        logger.info(f"  - {section['platform']}: {section['item_count']} 条")

    return final_data


if __name__ == "__main__":
    main()
