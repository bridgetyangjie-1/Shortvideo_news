"""
热门内容频道完整生成脚本
1. 抓取三个平台原始数据
2. 用 DeepSeek/本地规则生成 200 字摘要和标签
3. 输出到 assets/data/hot_content/
"""
import json
import logging
import sys
from pathlib import Path

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

    # 3. 输出到 assets/data/hot_content/
    logger.info("== 步骤 3/3: 保存最终 JSON ==")
    hot_content_dir = PROJECT_ROOT / "assets" / "data" / "hot_content"
    hot_content_dir.mkdir(parents=True, exist_ok=True)
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
