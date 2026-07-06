"""
质量门禁失败处理节点

当硬性门禁未通过、拒绝发布时：
1. 发送飞书告警（原仅在 push_node 拒绝路径触发，但图在门禁失败时不会到达 push_node）
2. 落盘诊断文件供 CI / 人工排查
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from coze_coding_utils.runtime_ctx.context import Context
from graphs.state import AlertNodeInput, QualityGateOutput
from tools.feishu_pusher import push_alert

logger = logging.getLogger(__name__)


def _workspace_root() -> str:
    return os.getenv("COZE_WORKSPACE_PATH", os.getcwd())


def _save_gate_diagnostic(state: AlertNodeInput, report: Dict[str, Any]) -> str:
    data_dir = os.path.join(_workspace_root(), "assets", "data")
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "quality_gate_last_run.json")
    payload = {
        "data_date": state.data_date,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "passed": False,
        "publish_mode": report.get("publish_mode", "blocked"),
        "quality_score": report.get("score", 0),
        "quality_report": report,
        "error_message": state.error_message,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def gate_fail_node(
    state: AlertNodeInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> QualityGateOutput:
    """
    title: 质量门禁失败通知
    desc: 硬性门禁未通过时发送飞书告警并保存诊断文件，不覆盖 latest.json
    """
    report: Dict[str, Any] = dict(state.quality_report or {}) if isinstance(state.quality_report, dict) else {}
    if not report:
        report = {"passed": False, "publish_mode": "blocked", "score": state.quality_score or 0}

    alert_message = (
        f"数据日期：{state.data_date or '未知'}\n"
        f"质量分：{state.quality_score or 0}\n"
        f"发布模式：{report.get('publish_mode', 'blocked')}\n"
        f"详情：\n{state.error_message or '质量门禁硬性校验未通过'}"
    )
    try:
        push_alert("质量门禁未通过 · 已拒绝发布", alert_message)
        logger.info("gate_fail_node: 飞书告警已发送")
    except Exception as exc:
        logger.warning("gate_fail_node: 飞书告警推送失败: %s", exc)

    try:
        diag_path = _save_gate_diagnostic(state, report)
        logger.info("gate_fail_node: 诊断文件已保存 %s", diag_path)
    except Exception as exc:
        logger.warning("gate_fail_node: 诊断文件保存失败: %s", exc)

    return QualityGateOutput(
        success=False,
        quality_score=state.quality_score or 0.0,
        quality_report=report,
        error_message=(state.error_message or "") + "gate_fail_node: 已拒绝发布并发送告警\n",
    )
