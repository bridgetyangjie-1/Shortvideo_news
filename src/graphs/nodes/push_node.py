"""
数据输出节点 - 生成JSON数据文件（支持TOP20 + Full100双文件存储）
适用于GitHub Actions环境，不依赖任何Coze内部SDK
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.ranking_quality import RankingCountError, ensure_top_rankings
from tools.ip_supply_chain import build_supply_chain
from tools.hongguo_crawler import HongguoCrawler
from tools.feishu_pusher import push_report, push_alert, determine_report_type
from graphs.state import (
    PushNodeInput,
    PushNodeOutput,
    DramaRanking,
    RankChange,
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
    AlertItem,
    AIDramaDashboard,
)

# 初始化日志
logger = logging.getLogger(__name__)

# 输出文件路径 - 使用当前工作目录
WORKSPACE_PATH = os.getcwd()
DATA_DIR = os.path.join(WORKSPACE_PATH, "assets", "data")
DATA_FILE_PATH = os.path.join(DATA_DIR, "latest.json")
DATA_FULL_PATH = os.path.join(DATA_DIR, "latest_full.json")  # 新增：完整100条数据
HISTORY_DIR = os.path.join(DATA_DIR, "history")
WEEKLY_DIR = os.path.join(DATA_DIR, "weekly")  # 新增：周榜归档
ALL_HISTORY_PATH = os.path.join(DATA_DIR, "all_history.json")


def _ensure_dirs() -> None:
    """确保数据目录存在"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(WEEKLY_DIR, exist_ok=True)
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
        "with_studio": sum(1 for r in rankings if getattr(r, 'production_house', None) and r.production_house and r.production_house != "未知"),
    }


def _generate_trends(rankings: List[DramaRanking]) -> Dict[str, Any]:
    """生成趋势分析"""
    # 统计排名变化
    new_count = 0
    up_count = 0
    down_count = 0
    stable_count = 0
    
    for r in rankings:
        trend_type = getattr(r, 'trend_type', 'same') or 'same'
        if trend_type == "new":
            new_count += 1
        elif trend_type == "up":
            up_count += 1
        elif trend_type == "down":
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


def _attach_rank_changes(rankings: List[DramaRanking], rank_changes: List[RankChange]) -> None:
    """将历史节点计算的排名变化合并到榜单条目中，供前端趋势列展示。"""
    if not rank_changes or not rankings:
        return
    change_map = {rc.title: rc for rc in rank_changes}
    for r in rankings:
        rc = change_map.get(r.title)
        if not rc:
            continue
        r.previous_rank = rc.previous_rank or 0
        if rc.change_type == "new":
            r.rank_change = -1
            r.trend_type = "new"
            r.trend = "new"
            r.change = "new"
        elif rc.change_type == "up":
            r.rank_change = rc.change_value
            r.trend_type = "up"
            r.trend = f"up{rc.change_value}"
            r.change = f"up{rc.change_value}"
        elif rc.change_type == "down":
            r.rank_change = -rc.change_value
            r.trend_type = "down"
            r.trend = f"down{rc.change_value}"
            r.change = f"down{rc.change_value}"
        else:
            r.rank_change = 0
            r.trend_type = "same"
            r.trend = "same"
            r.change = "same"


def _empty_supply_chain(series_id: str = "") -> Dict[str, Any]:
    return {
        "has_ip_source": False,
        "source_title": "",
        "source_author": "",
        "source_platform": "",
        "match_confidence": 0.0,
        "series_id": series_id,
    }


def _build_supply_chain_for_ranking(r: DramaRanking, crawler: HongguoCrawler) -> Dict[str, Any]:
    """为单部剧构建 IP/供应链信息，失败时返回空结构不阻塞流程。"""
    series_id = getattr(r, "series_id", "") or ""
    if not series_id:
        return _empty_supply_chain(series_id)
    try:
        chain = build_supply_chain(r.title, series_id, crawler.fetch_series_html)
        chain["series_id"] = series_id
        return chain
    except Exception as exc:
        logger.warning("push_node: 供应链补充失败 %s: %s", r.title, exc)
        return _empty_supply_chain(series_id)


def _build_weekly_base_info(output_rankings: List[DramaRanking]) -> Dict[str, Any]:
    """构建周榜基准信息（供前端展示本周 TOP1 坐标）"""
    weekly_base_rankings = [
        r for r in output_rankings
        if getattr(r, "data_source", "") == "duanjugongcheng"
    ]
    if not weekly_base_rankings:
        return {"available": False}
    weekly_top = sorted(weekly_base_rankings, key=lambda x: x.rank)[0]
    return {
        "available": True,
        "week_date": getattr(weekly_top, "week_date", "") or "",
        "top1_title": weekly_top.title,
        "top1_genre": weekly_top.genre,
        "top1_index": weekly_top.views_num or weekly_top.heat,
        "total_count": len(weekly_base_rankings),
        "data_source": "duanjugongcheng",
        "description": "基于红果短剧官方周榜数据，每周一更新",
    }


def _build_weekly_archive_data(
    output_rankings: List[DramaRanking],
    data_date: str,
    generated_at: str,
) -> Optional[Tuple[Dict[str, Any], str]]:
    """
    构建周榜归档数据。
    仅当 data_date 为周一且存在短剧工程周榜数据时返回 (weekly_data, week_date)。
    """
    dt = datetime.strptime(data_date, "%Y-%m-%d")
    if dt.weekday() != 0:
        return None

    weekly_rankings = [
        {
            "rank": r.rank,
            "title": r.title,
            "genre": r.genre,
            "weekly_index": r.views_num or r.heat,
            "total_index": getattr(r, "total_index", 0) or 0,
            "release_date": getattr(r, "release_date", "") or "",
            "is_new": getattr(r, "is_new", False),
            "data_source": r.data_source,
            "week_date": getattr(r, "week_date", "") or data_date,
        }
        for r in output_rankings
        if getattr(r, "data_source", "") == "duanjugongcheng"
    ]
    if not weekly_rankings:
        return None

    week_date = getattr(
        next((r for r in output_rankings if getattr(r, "data_source", "") == "duanjugongcheng"), None),
        "week_date",
        ""
    ) or data_date

    weekly_data = {
        "success": True,
        "generated_at": generated_at,
        "week_date": week_date,
        "rankings": weekly_rankings,
        "rankings_count": len(weekly_rankings),
    }
    return weekly_data, week_date


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

    # 质量门禁未通过时拒绝覆盖线上数据，并推送告警
    if not getattr(state, "success", True):
        error_message = "push_node: 质量门禁未通过，已拒绝覆盖 latest.json 等线上数据"
        logger.error(error_message)
        alert_message = (
            f"数据日期：{state.data_date or '未知'}\n"
            f"质量分：{state.quality_score or 0}\n"
            f"错误：{state.error_message or '质量门禁未通过'}\n"
            f"告警数：{state.alert_count or 0}"
        )
        try:
            push_alert("质量门禁未通过", alert_message)
        except Exception as feishu_exc:
            logger.warning("push_node: 飞书告警推送失败（不影响主流程）: %s", feishu_exc)
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
            alerts=state.alerts or [],
            alert_count=state.alert_count or 0,
            quality_report=state.quality_report or {},
            quality_score=state.quality_score or 0.0,
            ai_drama_dashboard=state.ai_drama_dashboard,
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
        # 合并历史节点产出的排名变化到榜单条目
        _attach_rank_changes(output_rankings, state.rank_changes or [])
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
            alerts=state.alerts or [],
            alert_count=state.alert_count or 0,
            quality_report=state.quality_report or {},
            quality_score=0.0,
            ai_drama_dashboard=state.ai_drama_dashboard,
            error_message=(state.error_message or "") + error_message + "\n"
        )
    
    # ========== 构建TOP20数据（前端展示用） ==========
    top20_rankings = output_rankings[:20]

    # 为 TOP20 榜单附加供应链信息
    crawler = HongguoCrawler()
    top20_ranking_dicts = []
    supply_chains: List[Dict[str, Any]] = []
    for r in top20_rankings:
        item = r.model_dump()
        chain = _build_supply_chain_for_ranking(r, crawler)
        item["supply_chain"] = chain
        supply_chains.append(chain)
        top20_ranking_dicts.append(item)

    # 顶层供应链汇总
    adapted_chains = [c for c in supply_chains if c.get("has_ip_source")]
    source_platform_counts: Dict[str, int] = {}
    for c in adapted_chains:
        platform = c.get("source_platform") or "未知平台"
        source_platform_counts[platform] = source_platform_counts.get(platform, 0) + 1
    top_sources = sorted(
        [{"platform": k, "count": v} for k, v in source_platform_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:5]
    supply_chain_summary = {
        "total_adapted": len(adapted_chains),
        "top_sources": top_sources,
        "sample_matches": [
            {
                "title": r.title,
                "source_title": c.get("source_title", ""),
                "source_platform": c.get("source_platform", ""),
            }
            for r, c in zip(top20_rankings, supply_chains)
            if c.get("has_ip_source")
        ][:5],
    }

    # ========== 生成统计/趋势/异常报告 ==========
    statistics = _generate_statistics(output_rankings)
    trends = _generate_trends(output_rankings)
    anomalies = _generate_anomalies(output_rankings, state.industry)

    # ========== 构建周榜基准信息（供前端展示） ==========
    weekly_base_info = _build_weekly_base_info(output_rankings)

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
        "alerts": [a.model_dump() for a in state.alerts] if state.alerts else [],
        "alert_count": state.alert_count or 0,
        "quality_report": state.quality_report or {},
        "weekly_base": weekly_base_info,
        "ai_drama_dashboard": state.ai_drama_dashboard.model_dump() if state.ai_drama_dashboard else {},
        "error_message": state.error_message or ""
    }
    
    # ========== 构建Full100数据（历史归档用） ==========
    full_rankings = output_rankings  # 全部榜单
    full_ranking_dicts = []
    for r in full_rankings:
        item = r.model_dump()
        item["supply_chain"] = _build_supply_chain_for_ranking(r, crawler)
        full_ranking_dicts.append(item)
    
    output_data_full = {
        "success": True,
        "generated_at": generated_at,
        "data_date": data_date,
        "genre_distribution": state.genre_distribution.model_dump() if state.genre_distribution else {},
        "emotional_analysis": state.emotional_analysis.model_dump() if state.emotional_analysis else {},
        "industry": state.industry.model_dump() if state.industry else {},
        "rankings": full_ranking_dicts,
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
        "alerts": [a.model_dump() for a in state.alerts] if state.alerts else [],
        "alert_count": state.alert_count or 0,
        "quality_report": state.quality_report or {},
        "weekly_base": weekly_base_info,
        "ai_drama_dashboard": state.ai_drama_dashboard.model_dump() if state.ai_drama_dashboard else {},
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
    
    # 保存周榜数据（每周一，基于短剧工程周榜数据）
    try:
        archive_result = _build_weekly_archive_data(output_rankings, data_date, generated_at)
        if archive_result:
            weekly_data, week_date = archive_result
            weekly_file = os.path.join(WEEKLY_DIR, f"{week_date}.json")
            if _save_json_file(weekly_data, weekly_file):
                logger.info(f"✅ 周榜数据已归档: {weekly_file} ({weekly_data['rankings_count']} 条)")
            else:
                error_messages.append(f"push_node: 保存周榜数据失败: {weekly_file}")
        else:
            logger.info("push_node: 非周一或无短剧工程周榜数据，跳过周榜归档")
    except Exception as e:
        logger.warning(f"push_node: 周榜归档处理异常: {e}")
    
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

    # 发送飞书日报/周报/月报推送（失败不阻断主流程）
    try:
        report_type = determine_report_type(data_date)
        type_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(report_type, "日报")
        logger.info("push_node: 发送飞书%s", type_label)
        push_report(output_data, report_type=report_type)
    except Exception as feishu_exc:
        logger.warning("push_node: 飞书推送失败（不影响主流程）: %s", feishu_exc)
    
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
        alerts=state.alerts or [],
        alert_count=state.alert_count or 0,
        quality_report=state.quality_report or {},
        quality_score=state.quality_score or 60.0,
        ai_drama_dashboard=state.ai_drama_dashboard,
        error_message=(state.error_message or "") + (("\n".join(error_messages) + "\n") if error_messages else "")
    )
