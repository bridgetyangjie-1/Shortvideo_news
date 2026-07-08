"""
数据质量门禁节点。

在 push_node 之前执行统一校验，防止低质量数据覆盖线上页面。
方向 A：关键数据缺失或来源不真实时不发布。
"""
import logging
import re
from typing import Dict, Any, List

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from coze_coding_utils.runtime_ctx.context import Context
from graphs.state import QualityGateInput, QualityGateOutput
from tools.actor_name_utils import is_placeholder_actor_name
from utils.data_quality import (
    count_ranking_hallucinations,
    is_unreliable_actor_name,
    is_suspicious_studio_name,
    is_trusted_news_url,
)

logger = logging.getLogger(__name__)

REQUIRED_TOP_RANKING_COUNT = 20
REQUIRED_FEMALE_ACTORS = 10
REQUIRED_MALE_ACTORS = 10
MAX_DAILY_NEWS_COUNT = 6
MIN_QUALITY_SCORE = 60

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

BLACKLISTED_ACTOR_NAMES = {"未知", "待定", "未识别", "unknown", "none", "n/a", "待核实"}
MAX_HALLUCINATED_ACTOR_RANKINGS = 2
MAX_SUSPICIOUS_STUDIO_RANKINGS = 3

# 被视为不真实/失败的数据来源说明（避免过于宽泛的「失败」误伤）
UNREALIABLE_SOURCE_PATTERNS = [
    re.compile(r"获取失败"),
    re.compile(r"暂无真实来源"),
    re.compile(r"本地规则估算"),
    re.compile(r"行业数据获取失败"),
    re.compile(r"连续两月未获取"),
]

# 硬性门禁：未通过则拒绝发布
HARD_BLOCK_CHECKS = {
    "rankings_count",
    "ranking_field_integrity",
    "api_errors",
    "ranking_hallucination",
}

# 行业数据中的占位/无效值，遇到时视为缺失
_PLACEHOLDER_VALUES = {
    "未知", "暂无", "无", "N/A", "n/a", "null", "None", "-", "—", "未提供",
    "not found", "not available", "unknown", "none",
}


def _is_unreliable_source(source: str) -> bool:
    """判断数据来源是否为失败/估算来源"""
    if not source:
        return True
    return any(p.search(source) for p in UNREALIABLE_SOURCE_PATTERNS)


def _is_meaningful_text(value: Any) -> bool:
    """判断文本字段是否为有效值（非空且非占位符）"""
    if value is None:
        return False
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    return bool(stripped) and stripped not in _PLACEHOLDER_VALUES


def quality_gate_node(
    state: QualityGateInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> QualityGateOutput:
    """
    title: 数据质量门禁
    desc: 在推送前统一校验榜单、演员、快讯、行业数据质量及数据来源真实性
    """
    report: Dict[str, Any] = {
        "checks": [],
        "score": 0,
        "passed": False,
    }
    errors: List[str] = []
    warnings: List[str] = []

    rankings = state.enriched_rankings or []
    actors = state.actors or {}
    daily_news = state.daily_news or []
    industry = state.industry or {}
    platform = state.platform or {}
    audience_profile = state.audience_profile or {}

    # 1. 榜单数量
    ranking_count = len(rankings)
    ranking_count_ok = ranking_count >= REQUIRED_TOP_RANKING_COUNT
    report["checks"].append({
        "name": "rankings_count",
        "passed": ranking_count_ok,
        "value": ranking_count,
        "required": REQUIRED_TOP_RANKING_COUNT,
    })
    if not ranking_count_ok:
        errors.append(f"榜单数量不足：当前 {ranking_count} 条，要求至少 {REQUIRED_TOP_RANKING_COUNT} 条")

    # 2. 榜单字段完整性
    valid_rankings = 0
    invalid_rankings: List[str] = []
    for r in rankings:
        title = getattr(r, "title", "") or ""
        views_num = getattr(r, "views_num", 0) or 0
        platform_name = getattr(r, "platform", "") or ""
        if title and views_num >= 0 and platform_name:
            valid_rankings += 1
        else:
            invalid_rankings.append(title or "<空剧名>")

    field_integrity_ok = valid_rankings >= REQUIRED_TOP_RANKING_COUNT
    report["checks"].append({
        "name": "ranking_field_integrity",
        "passed": field_integrity_ok,
        "valid": valid_rankings,
        "invalid_samples": invalid_rankings[:5],
    })
    if not field_integrity_ok:
        errors.append(f"有效榜单字段不完整：仅 {valid_rankings}/{ranking_count} 条通过校验")

    # 2.1 榜单幻觉检测（演员/厂牌）
    hallucination_stats = count_ranking_hallucinations(rankings)
    actor_hallucination_hits = hallucination_stats["actor_hits"]
    studio_hallucination_hits = hallucination_stats["studio_hits"]
    hallucination_samples: List[str] = []
    for r in rankings:
        title = getattr(r, "title", "") or ""
        female = getattr(r, "female_lead", "") or ""
        male = getattr(r, "male_lead", "") or ""
        studio = getattr(r, "production_house", "") or ""
        if (female and is_unreliable_actor_name(female)) or (male and is_unreliable_actor_name(male)):
            hallucination_samples.append(f"{title}({female}/{male})")
        elif is_suspicious_studio_name(studio):
            hallucination_samples.append(f"{title}[{studio}]")

    ranking_hallucination_ok = (
        actor_hallucination_hits <= MAX_HALLUCINATED_ACTOR_RANKINGS
        and studio_hallucination_hits <= MAX_SUSPICIOUS_STUDIO_RANKINGS
    )
    report["checks"].append({
        "name": "ranking_hallucination",
        "passed": ranking_hallucination_ok,
        "actor_hits": actor_hallucination_hits,
        "studio_hits": studio_hallucination_hits,
        "max_actor_hits": MAX_HALLUCINATED_ACTOR_RANKINGS,
        "max_studio_hits": MAX_SUSPICIOUS_STUDIO_RANKINGS,
        "samples": hallucination_samples[:5],
    })
    if not ranking_hallucination_ok:
        errors.append(
            f"榜单存在幻觉数据：可疑演员 {actor_hallucination_hits} 部、"
            f"可疑厂牌 {studio_hallucination_hits} 部"
            f"（阈值 {MAX_HALLUCINATED_ACTOR_RANKINGS}/{MAX_SUSPICIOUS_STUDIO_RANKINGS}）"
        )

    # 3. 演员榜单
    female_actors = getattr(actors, "female", []) or []
    male_actors = getattr(actors, "male", []) or []

    def _valid_actor(actor) -> bool:
        name = getattr(actor, "name", "") or ""
        if not name or name.lower() in BLACKLISTED_ACTOR_NAMES:
            return False
        if is_placeholder_actor_name(name) or is_unreliable_actor_name(name):
            return False
        return True

    female_valid = sum(1 for a in female_actors if _valid_actor(a))
    male_valid = sum(1 for a in male_actors if _valid_actor(a))

    female_ok = female_valid >= REQUIRED_FEMALE_ACTORS
    male_ok = male_valid >= REQUIRED_MALE_ACTORS

    report["checks"].append({
        "name": "female_actors",
        "passed": female_ok,
        "valid": female_valid,
        "required": REQUIRED_FEMALE_ACTORS,
    })
    report["checks"].append({
        "name": "male_actors",
        "passed": male_ok,
        "valid": male_valid,
        "required": REQUIRED_MALE_ACTORS,
    })
    if not female_ok:
        warnings.append(f"女频演员有效数量不足：{female_valid}/{REQUIRED_FEMALE_ACTORS}")
    if not male_ok:
        warnings.append(f"男频演员有效数量不足：{male_valid}/{REQUIRED_MALE_ACTORS}")

    # 4. 每日快讯（0-6条均可，每条须有可信 URL）
    news_count = len(daily_news)
    news_count_ok = 0 <= news_count <= MAX_DAILY_NEWS_COUNT
    news_with_url = sum(
        1 for n in daily_news
        if (getattr(n, "source_url", "") or "").startswith(("http://", "https://"))
    )
    news_trusted_url = sum(
        1 for n in daily_news
        if is_trusted_news_url(getattr(n, "source_url", "") or "")
    )
    news_with_insight = sum(
        1 for n in daily_news
        if _is_meaningful_text(getattr(n, "insight", "") or "")
    )
    news_url_ok = news_with_url == news_count and news_count > 0
    news_trust_ok = news_trusted_url == news_count and news_count > 0
    news_insight_ok = news_count == 0 or news_with_insight == news_count

    report["checks"].append({
        "name": "daily_news_count",
        "passed": news_count_ok,
        "value": news_count,
        "max": MAX_DAILY_NEWS_COUNT,
    })
    report["checks"].append({
        "name": "daily_news_url",
        "passed": news_url_ok,
        "value": news_with_url,
        "total": news_count,
    })
    report["checks"].append({
        "name": "daily_news_url_trust",
        "passed": news_trust_ok or news_count == 0,
        "trusted": news_trusted_url,
        "total": news_count,
    })
    report["checks"].append({
        "name": "daily_news_insight",
        "passed": news_insight_ok,
        "with_insight": news_with_insight,
        "total": news_count,
    })
    if not news_count_ok:
        warnings.append(f"快讯数量异常：当前 {news_count} 条，超过上限 {MAX_DAILY_NEWS_COUNT}")
    if news_count > 0 and not news_url_ok:
        warnings.append(f"快讯 source_url 不完整：{news_with_url}/{news_count}")
    if news_count > 0 and not news_trust_ok:
        warnings.append(f"快讯含不可信来源 URL：{news_trusted_url}/{news_count} 条通过")
    if news_count > 0 and not news_insight_ok:
        warnings.append(f"快讯 insight 缺失：{news_with_insight}/{news_count}")

    # 5. 行业数据来源真实性（方向 A：缺失/失败时不发布）
    app_mau = getattr(industry, "app_mau", "") or ""
    drama_count = getattr(industry, "drama_count", "") or ""
    ai_ratio = getattr(industry, "ai_ratio", 0) or 0
    industry_source = getattr(industry, "data_source", "") or ""

    industry_has_data = _is_meaningful_text(app_mau) and _is_meaningful_text(drama_count)
    ratio_ok = 0 <= ai_ratio <= 100
    industry_source_ok = not _is_unreliable_source(industry_source)

    report["checks"].append({
        "name": "industry_data",
        "passed": industry_has_data,
        "app_mau": app_mau,
        "drama_count": drama_count,
    })
    report["checks"].append({
        "name": "ai_ratio",
        "passed": ratio_ok,
        "value": ai_ratio,
    })
    report["checks"].append({
        "name": "industry_source",
        "passed": industry_source_ok,
        "source": industry_source,
    })
    if not industry_has_data:
        warnings.append("行业宏观数据缺失 app_mau 或 drama_count")
    if not ratio_ok:
        warnings.append(f"AI短剧占比异常：{ai_ratio}%")
    if not industry_source_ok:
        warnings.append(f"行业数据来源不真实：{industry_source}")

    # 6. 平台数据（可选，仅告警）
    platform_apps = getattr(platform, "apps", []) or []
    platform_source = getattr(platform, "data_source", "") or ""
    if not platform_apps:
        warnings.append("平台 APP 数据为空")
    if _is_unreliable_source(platform_source):
        warnings.append(f"平台数据来源不真实：{platform_source}")

    # 7. 观众画像数据来源真实性
    audience_source = getattr(audience_profile, "data_source", "") or ""
    audience_gender = getattr(audience_profile, "gender", {}) or {}
    has_audience_data = bool(audience_gender.get("female") or audience_gender.get("male"))
    audience_source_ok = not has_audience_data or not _is_unreliable_source(audience_source)
    report["checks"].append({
        "name": "audience_profile_source",
        "passed": audience_source_ok,
        "source": audience_source,
    })
    if has_audience_data and not audience_source_ok:
        warnings.append(f"观众画像数据来源不真实：{audience_source}")

    # 8. API 错误检测
    upstream_error = state.error_message or ""
    api_errors = [p for p in API_ERROR_PATTERNS if p.search(upstream_error)]
    api_error_ok = len(api_errors) == 0

    report["checks"].append({
        "name": "api_errors",
        "passed": api_error_ok,
        "matched_patterns": len(api_errors),
    })
    if not api_error_ok:
        errors.append("上游节点存在 API 鉴权、限流或解析失败错误，禁止推送")

    # 8.1 AI 短剧看板（软性告警，不阻断发布）
    ai_dashboard = state.ai_drama_dashboard
    ai_rankings = {}
    if ai_dashboard is not None:
        ai_rankings = getattr(ai_dashboard, "rankings", None) or {}
        if not isinstance(ai_rankings, dict):
            ai_rankings = {}
    ai_has_data = bool(
        (getattr(ai_dashboard, "kpis", None) or [])
        or (ai_rankings.get("ai_drama") or [])
        or (ai_rankings.get("ai_comic") or [])
        or (getattr(ai_dashboard, "trends", None) or [])
        or (getattr(ai_dashboard, "news", None) or [])
    )
    report["checks"].append({
        "name": "ai_drama_dashboard",
        "passed": ai_has_data,
        "has_data": ai_has_data,
    })
    if not ai_has_data:
        warnings.append("AI 短剧/漫剧看板核心数据为空")

    # 9. 计算质量分与发布模式
    check_results = [c["passed"] for c in report["checks"]]
    passed_checks = sum(check_results)
    total_checks = len(check_results)
    base_score = int((passed_checks / total_checks) * 100) if total_checks else 0

    # 硬性失败项直接封顶；软性告警仅扣分
    if errors:
        final_score = min(base_score, 59)
        publish_mode = "blocked"
    elif warnings:
        final_score = max(min(base_score - len(warnings) * 5, 95), 60)
        publish_mode = "degraded"
    else:
        final_score = base_score
        publish_mode = "full"

    report["score"] = final_score
    report["publish_mode"] = publish_mode
    report["passed"] = len(errors) == 0 and final_score >= MIN_QUALITY_SCORE

    error_message = ""
    if errors:
        error_message += "【质量门禁未通过】\n" + "\n".join(f"- {e}" for e in errors) + "\n"
    if warnings:
        error_message += "【质量门禁告警】\n" + "\n".join(f"- {w}" for w in warnings) + "\n"
    if publish_mode == "degraded":
        error_message += "【发布模式】降级发布：榜单已更新，部分次要模块数据不完整\n"

    success = report["passed"]

    logger.info(
        "quality_gate_node: score=%s success=%s errors=%s warnings=%s",
        final_score,
        success,
        len(errors),
        len(warnings),
    )

    return QualityGateOutput(
        success=success,
        quality_score=final_score,
        quality_report=report,
        error_message=error_message,
    )
