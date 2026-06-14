"""
异常监测节点（Alerts）

在质量门禁之后、数据推送之前，自动扫描当日数据，生成可展示的业务告警。
"""
import re
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from coze_coding_utils.runtime_ctx.context import Context
from graphs.state import AlertNodeInput, AlertNodeOutput, AlertItem, DramaRanking

API_ERROR_PATTERNS = [
    re.compile(r"api\s*key", re.I),
    re.compile(r"unauthorized", re.I),
    re.compile(r"rate\s*limit", re.I),
    re.compile(r"429", re.I),
    re.compile(r"解析失败", re.I),
    re.compile(r"鉴权", re.I),
    re.compile(r"余额不足", re.I),
    re.compile(r"budget", re.I),
]

CRITICAL_QUALITY_CHECKS = {
    "rankings_count",
    "ranking_field_integrity",
    "daily_news_count",
    "daily_news_url",
    "api_errors",
}

WARNING_QUALITY_CHECKS = {
    "female_actors",
    "male_actors",
    "industry_data",
    "ai_ratio",
}


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """兼容 Pydantic 模型与字典的取值"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _severity_for_check(name: str) -> str:
    if name in CRITICAL_QUALITY_CHECKS:
        return "critical"
    if name in WARNING_QUALITY_CHECKS:
        return "warning"
    return "info"


def _check_quality_report(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """将质量门禁中的失败项转化为告警"""
    report = state.quality_report or {}
    score = state.quality_score or 0
    checks = report.get("checks", []) if isinstance(report, dict) else []

    for check in checks:
        if isinstance(check, dict) and not check.get("passed"):
            name = check.get("name", "unknown")
            alerts.append(
                AlertItem(
                    severity=_severity_for_check(name),
                    category="quality",
                    title=f"质量门禁未通过：{name}",
                    message=f"质量检查项 [{name}] 未通过，详见 quality_report。",
                    metric=name,
                    value=check,
                )
            )

    if score < 60:
        alerts.append(
            AlertItem(
                severity="critical",
                category="quality",
                title="质量分低于 60",
                message=f"当前质量分 {score}，已触发推送阻断阈值。",
                metric="quality_score",
                value=score,
                threshold=60,
                suggestion="检查上游节点日志，修复榜单/演员/快讯/行业数据问题后再重试。",
            )
        )
    elif score < 80:
        alerts.append(
            AlertItem(
                severity="warning",
                category="quality",
                title="质量分偏低",
                message=f"当前质量分 {score}，低于 80 分建议关注。",
                metric="quality_score",
                value=score,
                threshold=80,
                suggestion="关注 quality_report 中的 warning 项。",
            )
        )


def _check_rankings(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描榜单异常"""
    rankings = state.enriched_rankings or []
    total = len(rankings)

    if total < 20:
        alerts.append(
            AlertItem(
                severity="critical",
                category="ranking",
                title="榜单数量不足",
                message=f"当前仅 {total} 部剧入榜，未达到 TOP20 展示要求。",
                metric="rankings_count",
                value=total,
                threshold=20,
                suggestion="检查红果/DataEye 爬虫结果或启用历史数据补齐。",
            )
        )

    low_confidence = [
        r for r in rankings
        if _get(r, "confidence_score", 1.0) is not None and _get(r, "confidence_score", 1.0) < 0.6
    ]
    if len(low_confidence) >= 3:
        alerts.append(
            AlertItem(
                severity="warning",
                category="ranking",
                title="多部剧目置信度偏低",
                message=f"发现 {len(low_confidence)} 部剧置信度低于 60%，数据可信度下降。",
                metric="low_confidence_count",
                value=len(low_confidence),
                threshold=3,
                suggestion="对低置信度剧目补充红果详情页或 Kimi 交叉验证。",
            )
        )

    # 演员信息缺失
    missing_actors = [
        r for r in rankings
        if not (_get(r, "female_lead") or _get(r, "male_lead"))
    ]
    if total and len(missing_actors) > total * 0.3:
        alerts.append(
            AlertItem(
                severity="warning",
                category="actor",
                title="演员信息大面积缺失",
                message=f"{len(missing_actors)}/{total} 部剧缺少主演信息。",
                metric="missing_actor_ratio",
                value=round(len(missing_actors) / total * 100, 1),
                threshold=30,
                suggestion="检查 enrich_node 演员解析逻辑或启用缓存兜底。",
            )
        )

    # 排名大幅波动
    big_moves = [
        r for r in rankings
        if abs(_get(r, "rank_change", 0) or 0) >= 5
    ]
    if big_moves:
        alerts.append(
            AlertItem(
                severity="info",
                category="ranking",
                title="榜单出现大幅排名波动",
                message=f"{len(big_moves)} 部剧排名较昨日变化超过 5 位。",
                metric="big_move_count",
                value=len(big_moves),
                threshold=5,
            )
        )

    new_entries = [
        r for r in rankings
        if (_get(r, "rank_change", 0) == -1)
        or (_get(r, "change_type", "") == "new")
        or (_get(r, "change", "") == "new")
    ]
    if len(new_entries) >= 5:
        alerts.append(
            AlertItem(
                severity="warning",
                category="ranking",
                title="新上榜剧目占比高",
                message=f"今日新上榜/昨日不在榜剧目共 {len(new_entries)} 部，榜单稳定性低。",
                metric="new_entry_count",
                value=len(new_entries),
                threshold=5,
            )
        )


def _check_actors(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描演员榜单异常"""
    actors = state.actors or {}
    female = _get(actors, "female", []) or []
    male = _get(actors, "male", []) or []

    if len(female) < 10:
        alerts.append(
            AlertItem(
                severity="warning",
                category="actor",
                title="女频演员榜不足 10 人",
                message=f"当前女频演员榜仅 {len(female)} 人。",
                metric="female_actor_count",
                value=len(female),
                threshold=10,
            )
        )
    if len(male) < 10:
        alerts.append(
            AlertItem(
                severity="warning",
                category="actor",
                title="男频演员榜不足 10 人",
                message=f"当前男频演员榜仅 {len(male)} 人。",
                metric="male_actor_count",
                value=len(male),
                threshold=10,
            )
        )


def _check_industry(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描行业宏观数据异常"""
    industry = state.industry or {}
    app_mau = _get(industry, "app_mau", "")
    drama_count = _get(industry, "drama_count", "")
    ai_ratio = _get(industry, "ai_ratio", 0) or 0

    if not app_mau:
        alerts.append(
            AlertItem(
                severity="warning",
                category="industry",
                title="行业 APP 月活缺失",
                message="industry.app_mau 为空，行业宏观面板将显示占位。",
                metric="app_mau",
                value=app_mau,
            )
        )
    if not drama_count:
        alerts.append(
            AlertItem(
                severity="warning",
                category="industry",
                title="行业剧集总量缺失",
                message="industry.drama_count 为空，行业宏观面板将显示占位。",
                metric="drama_count",
                value=drama_count,
            )
        )
    if ai_ratio > 50:
        alerts.append(
            AlertItem(
                severity="info",
                category="industry",
                title="AI 短剧占比显著偏高",
                message=f"AI 短剧占比达 {ai_ratio}%，显著高于常规水位。",
                metric="ai_ratio",
                value=ai_ratio,
                threshold=50,
            )
        )


def _check_platform(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描平台数据异常"""
    platform = state.platform or {}
    apps = _get(platform, "apps", []) or []
    if not apps:
        alerts.append(
            AlertItem(
                severity="info",
                category="platform",
                title="平台 APP 数据为空",
                message="platform.apps 为空，平台竞争格局卡片无法展示。",
                metric="platform_app_count",
                value=0,
            )
        )


def _check_news(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描快讯异常"""
    news = state.daily_news or []
    count = len(news)
    if count != 6:
        alerts.append(
            AlertItem(
                severity="warning",
                category="news",
                title="每日快讯数量异常",
                message=f"当前快讯 {count} 条，要求 6 条。",
                metric="daily_news_count",
                value=count,
                threshold=6,
            )
        )

    missing_url = sum(
        1 for n in news
        if not str(_get(n, "source_url", "") or "").startswith(("http://", "https://"))
    )
    if missing_url:
        alerts.append(
            AlertItem(
                severity="warning",
                category="news",
                title="快讯来源链接缺失",
                message=f"{missing_url} 条快讯缺少有效 source_url。",
                metric="missing_source_url_count",
                value=missing_url,
            )
        )


def _check_genre(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描题材/标签异动"""
    genre = state.genre_distribution or {}
    trending = _get(genre, "trending", []) or []
    spiking = [t for t in trending if abs(_get(t, "change", 0) or 0) >= 5]
    if spiking:
        names = [_get(t, "name", "") for t in spiking[:3]]
        alerts.append(
            AlertItem(
                severity="info",
                category="genre",
                title="热门标签环比异动",
                message=f"{len(spiking)} 个标签较昨日变化超过 5 次，TOP3：{', '.join(names)}。",
                metric="spiking_tag_count",
                value=len(spiking),
                threshold=5,
            )
        )


def _check_emotion(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描情绪分析异常"""
    emotion = state.emotional_analysis or {}
    wordcloud = _get(emotion, "wordcloud", []) or []
    if not wordcloud:
        alerts.append(
            AlertItem(
                severity="info",
                category="emotion",
                title="情绪词云为空",
                message="emotional_analysis.wordcloud 为空，情绪驾驶舱将展示默认数据。",
                metric="wordcloud_count",
                value=0,
            )
        )


def _check_play_trend(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描播放趋势异常"""
    play_trend = state.play_trend or {}
    direction = _get(play_trend, "trend_direction", "stable")
    if direction == "down":
        alerts.append(
            AlertItem(
                severity="warning",
                category="ranking",
                title="大盘播放量环比下降",
                message="近 7 日总播放量趋势向下，需关注榜单整体热度。",
                metric="play_trend_direction",
                value=direction,
            )
        )


def _check_api_errors(state: AlertNodeInput, alerts: List[AlertItem]) -> None:
    """扫描上游 API 错误"""
    error_text = state.error_message or ""
    matched = [p.pattern for p in API_ERROR_PATTERNS if p.search(error_text)]
    if matched:
        alerts.append(
            AlertItem(
                severity="critical",
                category="api",
                title="上游存在 API 错误",
                message=f"错误日志中命中 {len(matched)} 类 API 异常：{', '.join(matched[:3])}。",
                metric="api_error_patterns",
                value=len(matched),
                suggestion="检查 API Key、配额与网络连通性。",
            )
        )


def alert_node(
    state: AlertNodeInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> AlertNodeOutput:
    """
    title: 异常监测
    desc: 基于质量报告与业务规则自动生成 Alerts，供前端异常面板展示
    """
    alerts: List[AlertItem] = []
    error_messages: List[str] = []

    try:
        _check_quality_report(state, alerts)
        _check_rankings(state, alerts)
        _check_actors(state, alerts)
        _check_industry(state, alerts)
        _check_platform(state, alerts)
        _check_news(state, alerts)
        _check_genre(state, alerts)
        _check_emotion(state, alerts)
        _check_play_trend(state, alerts)
        _check_api_errors(state, alerts)
    except Exception as e:
        error_messages.append(f"alert_node: 扫描异常时出错: {e}")

    # 去重：按 (severity, category, title) 去重，保留第一条详情
    seen = set()
    unique_alerts: List[AlertItem] = []
    for alert in alerts:
        key = (alert.severity, alert.category, alert.title)
        if key not in seen:
            seen.add(key)
            unique_alerts.append(alert)

    # 按严重级别排序
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    unique_alerts.sort(key=lambda a: severity_order.get(a.severity, 3))

    return AlertNodeOutput(
        alerts=unique_alerts,
        alert_count=len(unique_alerts),
        error_message="\n".join(error_messages) + "\n" if error_messages else "",
    )
