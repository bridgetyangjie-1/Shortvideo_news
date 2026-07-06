#!/usr/bin/env python3
"""
GitHub Actions 专用入口文件
用于在GitHub Actions环境中运行短剧看板工作流
"""
import os
import sys
import json
import logging
from datetime import datetime
from typing import Any, Dict, Tuple

# 设置路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置环境变量
os.environ['COZE_WORKSPACE_PATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _normalize_result(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return dict(result)


def _get_field(result: Dict[str, Any], key: str, default: Any = None) -> Any:
    if not isinstance(result, dict):
        return default
    return result.get(key, default)


def evaluate_run_result(result: Dict[str, Any]) -> Tuple[bool, str]:
    """
    评估工作流是否算「成功发布」。

    返回 (success, reason)。硬性门禁失败、未发布榜单、异常均视为失败。
    """
    if not result:
        return False, "工作流返回空结果"

    quality_report = _get_field(result, "quality_report", {}) or {}
    if not isinstance(quality_report, dict):
        quality_report = {}

    passed = quality_report.get("passed", _get_field(result, "success", True))
    publish_mode = quality_report.get("publish_mode", "unknown")
    workflow_success = bool(_get_field(result, "success", False))

    rankings = _get_field(result, "rankings", []) or []
    output_path = os.path.join(
        os.environ.get("COZE_WORKSPACE_PATH", os.getcwd()),
        "assets",
        "data",
        "latest.json",
    )
    published = os.path.exists(output_path) and len(rankings) >= 20

    if not passed or not workflow_success:
        reason = _get_field(result, "error_message", "") or "质量门禁未通过，已拒绝发布"
        return False, reason.strip()

    if not published:
        return False, f"未检测到有效发布（榜单 {len(rankings)} 条，publish_mode={publish_mode}）"

    if publish_mode == "degraded":
        logger.warning("本次为降级发布，部分次要模块可能不完整")

    return True, ""


def main():
    """主函数 - 运行工作流"""
    try:
        logger.info("开始运行短剧看板工作流...")

        from graphs.graph import create_graph

        graph = create_graph()

        today = datetime.now().strftime("%Y-%m-%d")
        input_data = {"data_date": today}

        logger.info(f"数据日期: {today}")

        config = {
            "configurable": {
                "thread_id": "github_actions_run"
            }
        }

        result = graph.invoke(input_data, config)

        logger.info("工作流执行完成！")

        if result:
            normalized = _normalize_result(result)
            logger.info(f"生成数据日期: {_get_field(normalized, 'data_date', 'N/A')}")
            rankings = _get_field(normalized, "rankings", []) or []
            logger.info(f"榜单数量: {len(rankings)}")
            if rankings:
                first_ranking = rankings[0]
                if hasattr(first_ranking, "title"):
                    logger.info(f"TOP1: {first_ranking.title}")
                elif isinstance(first_ranking, dict):
                    logger.info(f"TOP1: {first_ranking.get('title', 'N/A')}")

            quality_report = _get_field(normalized, "quality_report", {}) or {}
            if isinstance(quality_report, dict):
                logger.info(
                    "质量门禁: passed=%s score=%s mode=%s",
                    quality_report.get("passed"),
                    quality_report.get("score"),
                    quality_report.get("publish_mode"),
                )

            output_path = os.path.join(
                os.environ.get("COZE_WORKSPACE_PATH", os.getcwd()),
                "assets",
                "data",
                "latest.json",
            )
            if os.path.exists(output_path):
                logger.info(f"数据已保存到: {output_path}")

            success, reason = evaluate_run_result(normalized)
            if not success:
                logger.error("工作流未成功发布: %s", reason)
            return success

        logger.error("工作流返回空结果")
        return False

    except Exception as e:
        logger.error(f"工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
