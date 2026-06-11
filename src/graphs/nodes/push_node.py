"""
数据输出节点 - 生成JSON数据文件（纯本地文件系统版本）
适用于GitHub Actions环境，不依赖任何Coze内部SDK
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.state import (
    PushNodeInput, 
    PushNodeOutput,
    DramaRanking,
    ActorsData,
    IndustryData,
    PlatformData,
    Insight,
    DailyNews,
    AudienceProfile,
    GenreDistribution,
    PlayTrend,
    OverviewStats,
    PlatformShare
)

# 初始化日志
logger = logging.getLogger(__name__)

# 输出文件路径 - 使用当前工作目录
WORKSPACE_PATH = os.getcwd()
DATA_DIR = os.path.join(WORKSPACE_PATH, "assets", "data")
DATA_FILE_PATH = os.path.join(DATA_DIR, "latest.json")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
ALL_HISTORY_PATH = os.path.join(DATA_DIR, "all_history.json")


def _ensure_dirs() -> None:
    """确保数据目录存在"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)


def _save_json_file(data: Dict[str, Any], file_path: str) -> bool:
    """
    保存JSON数据到本地文件
    """
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"数据已保存到: {file_path}")
        return True
    except Exception as e:
        logger.error(f"保存文件失败: {e}")
        return False


def _load_all_history() -> Dict[str, Any]:
    """加载所有历史数据"""
    if os.path.exists(ALL_HISTORY_PATH):
        try:
            with open(ALL_HISTORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"dates": [], "data": {}}


def push_node(state: PushNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> PushNodeOutput:
    """
    title: 数据输出
    desc: 将处理完成的数据保存为JSON文件，支持历史数据归档
    """
    ctx = runtime.context
    _ensure_dirs()
    
    # 获取数据日期
    data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
    generated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    
    # 构建完整数据结构
    output_data = {
        "success": True,
        "generated_at": generated_at,
        "data_date": data_date,
        "genre_distribution": state.genre_distribution.model_dump() if state.genre_distribution else {},
        "industry": state.industry.model_dump() if state.industry else {},
        "rankings": [r.model_dump() for r in state.enriched_rankings] if state.enriched_rankings else [],
        "actors": state.actors.model_dump() if state.actors else {"female": [], "male": []},
        "platform": state.platform.model_dump() if state.platform else {},
        "audience_profile": state.audience_profile.model_dump() if state.audience_profile else {},
        "play_trend": state.play_trend.model_dump() if state.play_trend else {},
        "daily_news": [n.model_dump() for n in state.daily_news] if state.daily_news else [],
        "insights": [i.model_dump() for i in state.insights] if state.insights else [],
        "quality_score": state.quality_score or 60.0,
        "error_message": state.error_message or ""
    }
    
    # 保存最新数据
    error_messages: List[str] = []
    if not _save_json_file(output_data, DATA_FILE_PATH):
        error_messages.append(f"push_node: 保存最新数据失败: {DATA_FILE_PATH}")
    
    # 保存历史数据（按日期归档）
    history_file = os.path.join(HISTORY_DIR, f"{data_date}.json")
    if not _save_json_file(output_data, history_file):
        error_messages.append(f"push_node: 保存历史数据失败: {history_file}")
    
    # 更新历史索引
    all_history = _load_all_history()
    if data_date not in all_history.get("dates", []):
        all_history.setdefault("dates", []).append(data_date)
    all_history.setdefault("data", {})[data_date] = output_data
    
    # 保留最近30天的数据
    if len(all_history.get("dates", [])) > 30:
        old_dates = all_history["dates"][:-30]
        for old_date in old_dates:
            all_history["data"].pop(old_date, None)
        all_history["dates"] = all_history["dates"][-30:]
    
    # 保存历史索引
    if not _save_json_file(all_history, ALL_HISTORY_PATH):
        error_messages.append(f"push_node: 保存历史索引失败: {ALL_HISTORY_PATH}")
    
    logger.info(f"✅ 数据输出完成 - 最新数据已保存，历史数据已归档")
    
    # 返回完整数据，确保GraphOutput包含所有数据
    return PushNodeOutput(
        success=True,
        output_path=DATA_FILE_PATH,
        data_date=data_date,
        generated_at=generated_at,
        industry=state.industry,
        rankings=[r for r in state.enriched_rankings] if state.enriched_rankings else [],
        actors=state.actors,
        platform=state.platform,
        daily_news=state.daily_news,
        insights=state.insights,
        audience_profile=state.audience_profile,
        genre_distribution=state.genre_distribution,
        play_trend=state.play_trend,
        quality_score=state.quality_score or 60.0,
        error_message=(state.error_message or "") + (("\n".join(error_messages) + "\n") if error_messages else "")
    )