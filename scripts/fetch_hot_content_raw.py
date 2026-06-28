"""
热门内容频道统一抓取脚本（阶段二）
抓取红果、晋江、番茄三个平台的近期热门内容，输出原始 JSON 到 tmp/。
"""
import json
import logging
import sys
from pathlib import Path

# 将 src 加入路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tools.hot_content_fetcher import fetch_all_raw

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """主入口"""
    result = fetch_all_raw()

    # 保存到 tmp/
    tmp_dir = PROJECT_ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    output_file = tmp_dir / f"hot_content_raw_{result['data_date']}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"原始热门内容已保存: {output_file}")
    logger.info(f"总条目: {result['total_items']}")
    for section in result["sections"]:
        logger.info(f"  - {section['platform']}: {section['item_count']} 条")

    return output_file


if __name__ == "__main__":
    main()
