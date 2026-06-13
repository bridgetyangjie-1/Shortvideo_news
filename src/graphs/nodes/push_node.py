"""
数据输出节点 - 生成JSON数据文件（支持TOP20 + Full100双文件存储）
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
from graphs.ranking_quality import RankingCountError, ensure_top_rankings
from tools.ip_supply_chain import build_supply_chain
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
    EmotionalAnalysis,
    PlayTrend,
    OverviewStats,
)

# 初始化日志
logger = logging.getLogger(__name__)

# 输出文件路径 - 使用当前工作目录
WORKSPACE_PATH = os.getcwd()
DATA_DIR = os.path.join(WORKSPACE_PATH, "assets", "data")
DATA_FILE_PATH = os.path.join(DATA_DIR, "latest.json")
DATA_FULL_PATH = os.path.join(DATA_DIR, "latest_full.json")  # 新增：完整100条数据
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


def _generate_statistics(rankings: List[DramaRanking]) -> Dict[str, Any]:
    """生成榜单统计信息"""
    if not rankings:
        return {"total": 0, "avg_confidence": 0, "source_distribution": {}}
    
    # 数据源分布
    source_counts: Dict[str, int] = {}
    confidence_scores = []
    
    for r in rankings:
        source = getattr(r, 'data_source', 'unknown') or 'unknown'
        source_counts[source] = source_counts.get(source, 0) + 1
        confidence = getattr(r, 'confidence_score', 0.8) or 0.8
        confidence_scores.append(confidence)
    
    return {
        "total": len(rankings),
        "avg_confidence": round(sum(confidence_scores) / len(confidence_scores), 2) if confidence_scores else 0,
        "source_distribution": source_counts,
        "with_actors": sum(1 for r in rankings if getattr(r, 'actors', None) and r.actors),
        "with_studio": sum(1 for r in rankings if getattr(r, 'studio', None) and r.studio and r.studio != "未知"),
    }


def _generate_trends(rankings: List[DramaRanking]) -> Dict[str, Any]:
    """生成趋势分析"""
    # 统计排名变化
    new_count = 0
    up_count = 0
    down_count = 0
    stable_count = 0
    
    for r in rankings:
        change = getattr(r, 'rank_change', None)
        if not change:
            new_count += 1
        elif change == "new":
            new_count += 1
        elif change.startswith("up"):
            up_count += 1
        elif change.startswith("down"):
            down_count += 1
        else:
            stable_count += 1
    
    # 统计标签趋势
    tag_counts: Dict[str, int] = {}
    for r in rankings:
        tags = getattr(r, 'tags', []) or []
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # 取TOP10热门标签
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return {
        "rank_changes": {
            "new": new_count,
            "up": up_count,
            "down": down_count,
            "stable": stable_count
        },
        "hot_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "trend_direction": "up" if up_count > down_count else ("down" if down_count > up_count else "stable")
    }


def _generate_anomalies(rankings: List[DramaRanking], industry: Optional[IndustryData]) -> List[Dict[str, Any]]:
    """生成异常检测报告"""
    anomalies = []
    
    # 检测置信度低的剧目
    low_confidence = [r for r in rankings if getattr(r, 'confidence_score', 1.0) < 0.6]
    if low_confidence:
        anomalies.append({
            "type": "low_confidence",
            "severity": "warning",
            "count": len(low_confidence),
            "message": f"发现{len(low_confidence)}部剧置信度低于60%，建议人工核验",
            "items": [{"title": r.title, "confidence": getattr(r, 'confidence_score', 0)} for r in low_confidence[:5]]
        })
    
    # 检测演员缺失
    missing_actors = [r for r in rankings if not getattr(r, 'actors', None) or not r.actors]
    if len(missing_actors) > len(rankings) * 0.3:  # 超过30%缺失
        anomalies.append({
            "type": "missing_actors",
            "severity": "warning",
            "count": len(missing_actors),
            "message": f"{len(missing_actors)}部剧缺少演员信息，占比{round(len(missing_actors)/len(rankings)*100)}%",
            "items": [r.title for r in missing_actors[:5]]
        })
    
    # 检测行业数据异常
    if industry:
        ai_ratio = getattr(industry, 'ai_ratio', 0) or 0
        if ai_ratio > 50:
            anomalies.append({
                "type": "high_ai_ratio",
                "severity": "info",
                "message": f"AI短剧占比达{ai_ratio}%，显著高于行业均值",
                "value": ai_ratio
            })
    
    return anomalies


def push_node(state: PushNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> PushNodeOutput:
    """
    title: 数据输出
    desc: 将处理完成的数据保存为JSON文件（TOP20展示 + Full100归档）
    """
    ctx = runtime.context
    _ensure_dirs()
    
    # 获取数据日期
    data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
    generated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

    # 质量门禁未通过时拒绝覆盖线上数据
    if not getattr(state, "success", True):
        error_message = "push_node: 质量门禁未通过，已拒绝覆盖 latest.json 等线上数据"
        logger.error(error_message)
        return PushNodeOutput(
            success=False,
            output_path=DATA_FILE_PATH,
            data_date=data_date,
            generated_at=generated_at,
            industry=state.industry,
            rankings=[],
            actors=state.actors,
            platform=state.platform,
            daily_news=state.daily_news,
            insights=state.insights,
            audience_profile=state.audience_profile,
            genre_distribution=state.genre_distribution,
            play_trend=state.play_trend,
            quality_score=state.quality_score or 0.0,
            error_message=(state.error_message or "") + error_message + "\n",
        )

    error_messages: List[str] = []
    try:
        ranking_dicts, count_warning = ensure_top_rankings(
            state.enriched_rankings,
            data_date=data_date,
            workspace_path=WORKSPACE_PATH,
        )
        output_rankings = [DramaRanking(**item) for item in ranking_dicts]
        if count_warning:
            logger.warning("push_node: %s", count_warning)
            error_messages.append(f"push_node: {count_warning}")
    except RankingCountError as count_error:
        error_message = f"push_node: {count_error}"
        logger.error(error_message)
        return PushNodeOutput(
            success=False,
            output_path=DATA_FILE_PATH,
            data_date=data_date,
            generated_at=generated_at,
            industry=state.industry,
            rankings=[],
            actors=state.actors,
            platform=state.platform,
            daily_news=state.daily_news,
            insights=state.insights,
            audience_profile=state.audience_profile,
            genre_distribution=state.genre_distribution,
            play_trend=state.play_trend,
            quality_score=0.0,
            error_message=(state.error_message or "") + error_message + "\n"
        )
    
    # ========== 构建TOP20数据（前端展示用） ==========
    top20_rankings = output_rankings[:20]

    # 为 TOP20 榜单附加供应链信息（当前不触发实时网络请求，使用占位结构）
    top20_ranking_dicts = []
    for r in top20_rankings:
        item = r.model_dump()
        series_id = getattr(r, 'series_id', '') or ''
        # 供应链占位：后续可调用 build_supply_chain(r.title, series_id, crawler.fetch_series_html) 批量补充
        item["supply_chain"] = {
            "has_ip_source": False,
            "source_title": "",
            "source_author": "",
            "source_platform": "",
            "match_confidence": 0.0,
            "series_id": series_id
        }
        top20_ranking_dicts.append(item)

    # 顶层供应链汇总（当前为占位，后续随数据补充自动聚合）
    supply_chain_summary = {
        "total_adapted": 0,
        "top_sources": [],
        "sample_matches": []
    }

    # ========== 生成统计/趋势/异常报告 ==========
    statistics = _generate_statistics(output_rankings)
    trends = _generate_trends(output_rankings)
    anomalies = _generate_anomalies(output_rankings, state.industry)

    output_data = {
        "success": True,
        "generated_at": generated_at,
        "data_date": data_date,
        "genre_distribution": state.genre_distribution.model_dump() if state.genre_distribution else {},
        "emotional_analysis": state.emotional_analysis.model_dump() if state.emotional_analysis else {},
        "industry": state.industry.model_dump() if state.industry else {},
        "rankings": top20_ranking_dicts,
        "supply_chain": supply_chain_summary,
        "actors": state.actors.model_dump() if state.actors else {"female": [], "male": []},
        "platform": state.platform.model_dump() if state.platform else {},
        "audience_profile": state.audience_profile.model_dump() if state.audience_profile else {},
        "play_trend": state.play_trend.model_dump() if state.play_trend else {},
        "daily_news": [n.model_dump() for n in state.daily_news] if state.daily_news else [],
        "insights": [i.model_dump() for i in state.insights] if state.insights else [],
        "quality_score": state.quality_score or 60.0,
        "statistics": statistics,
        "trends": trends,
        "anomalies": anomalies,
        "error_message": state.error_message or ""
    }
    
    # ========== 构建Full100数据（历史归档用） ==========
    full_rankings = output_rankings  # 全部榜单
    
    output_data_full = {
        "success": True,
        "generated_at": generated_at,
        "data_date": data_date,
        "genre_distribution": state.genre_distribution.model_dump() if state.genre_distribution else {},
        "emotional_analysis": state.emotional_analysis.model_dump() if state.emotional_analysis else {},
        "industry": state.industry.model_dump() if state.industry else {},
        "rankings": [r.model_dump() for r in full_rankings],
        "rankings_count": len(full_rankings),
        "actors": state.actors.model_dump() if state.actors else {"female": [], "male": []},
        "platform": state.platform.model_dump() if state.platform else {},
        "audience_profile": state.audience_profile.model_dump() if state.audience_profile else {},
        "play_trend": state.play_trend.model_dump() if state.play_trend else {},
        "daily_news": [n.model_dump() for n in state.daily_news] if state.daily_news else [],
        "insights": [i.model_dump() for i in state.insights] if state.insights else [],
        "quality_score": state.quality_score or 60.0,
        "statistics": statistics,
        "trends": trends,
        "anomalies": anomalies,
        "error_message": state.error_message or ""
    }
    
    # 保存最新数据（TOP20）
    if not _save_json_file(output_data, DATA_FILE_PATH):
        error_messages.append(f"push_node: 保存最新数据失败: {DATA_FILE_PATH}")
    
    # 保存完整数据（Full100）- 新增
    if not _save_json_file(output_data_full, DATA_FULL_PATH):
        error_messages.append(f"push_node: 保存完整数据失败: {DATA_FULL_PATH}")
    
    # 保存历史数据（按日期归档）
    history_file = os.path.join(HISTORY_DIR, f"{data_date}.json")
    if not _save_json_file(output_data_full, history_file):  # 历史归档保存完整数据
        error_messages.append(f"push_node: 保存历史数据失败: {history_file}")
    
    # 更新历史索引
    all_history = _load_all_history()
    if data_date not in all_history.get("dates", []):
        all_history.setdefault("dates", []).append(data_date)
    all_history.setdefault("data", {})[data_date] = output_data_full
    
    # 保留最近30天的数据
    if len(all_history.get("dates", [])) > 30:
        old_dates = all_history["dates"][:-30]
        for old_date in old_dates:
            all_history["data"].pop(old_date, None)
        all_history["dates"] = all_history["dates"][-30:]
    
    # 保存历史索引
    if not _save_json_file(all_history, ALL_HISTORY_PATH):
        error_messages.append(f"push_node: 保存历史索引失败: {ALL_HISTORY_PATH}")
    
    logger.info(f"✅ 数据输出完成 - TOP20已保存({len(top20_rankings)}条)，Full100已归档({len(full_rankings)}条)")
    
    # 返回完整数据，确保GraphOutput包含所有数据
    return PushNodeOutput(
        success=True,
        output_path=DATA_FILE_PATH,
        data_date=data_date,
        generated_at=generated_at,
        industry=state.industry,
        rankings=output_rankings,
        actors=state.actors,
        platform=state.platform,
        daily_news=state.daily_news,
        insights=state.insights,
        audience_profile=state.audience_profile,
        genre_distribution=state.genre_distribution,
        emotional_analysis=state.emotional_analysis,
        play_trend=state.play_trend,
        quality_score=state.quality_score or 60.0,
        error_message=(state.error_message or "") + (("\n".join(error_messages) + "\n") if error_messages else "")
    )
