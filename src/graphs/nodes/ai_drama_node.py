"""
🤖 AI 短剧/漫剧看板节点

策略：
1. 优先直爬澎湃新闻 DataEye 月报/百强榜，再用 DeepSeek 结构化抽取。
2. 以自然月为粒度缓存；缓存缺失时依次尝试：thepaper 直爬 → Kimi 搜索 → 上月 → 通用搜索 → 历史 carry-forward。
3. 搜索/解析失败时留空，不返回固定默认值。
"""
import json
import os
import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from coze_coding_utils.runtime_ctx.context import Context

from tools.moonshot_api import MoonshotClient, is_api_budget_error
from tools.deepseek_api import DeepSeekClient
from tools.ai_drama_cache import load_cache, save_cache
from tools.ai_drama_fetcher import (
    combine_articles_text,
    extract_thepaper_ids,
    fetch_articles_by_ids,
    fetch_report_articles,
    regex_extract_dashboard,
)
from graphs.state import AIDramaNodeInput, AIDramaNodeOutput, AIDramaDashboard

logger = logging.getLogger(__name__)


def _load_llm_cfg(config: RunnableConfig) -> Dict[str, Any]:
    """读取 LLM 配置文件"""
    cfg_path = ""
    metadata = config.get("metadata", {}) if config else {}
    if metadata.get("llm_cfg"):
        cfg_path = os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), metadata["llm_cfg"])

    if cfg_path and os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("ai_drama_node: 读取 LLM 配置失败: %s", e)

    default_path = os.path.join(
        os.getenv("COZE_WORKSPACE_PATH", ""), "config", "ai_drama_llm_cfg.json"
    )
    if os.path.exists(default_path):
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("ai_drama_node: 读取默认 LLM 配置失败: %s", e)

    return {}


def _resolve_report_month(data_date: str) -> str:
    """月报通常为次月发布上月数据，因此 report_month 取 data_date 的上个月。"""
    try:
        dt = datetime.strptime(data_date, "%Y-%m-%d")
    except ValueError:
        dt = datetime.now()
    year, month = dt.year, dt.month
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _shift_report_month(report_month: str, offset: int = -1) -> str:
    try:
        dt = datetime.strptime(report_month, "%Y-%m")
    except ValueError:
        return report_month
    month = dt.month + offset
    year = dt.year
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return f"{year}-{month:02d}"


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in {"未知", "暂无", "无", "n/a", "null", "none", "-", "—"}:
            return default
        return stripped if stripped else default
    return str(value) if value is not None else default


def _safe_rank(value: Any) -> int:
    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            match = re.search(r"\d+", value)
            return int(match.group()) if match else 0
    except Exception:
        pass
    return 0


def _unwrap_dashboard_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("dashboard", "data", "result", "月报", "报告"):
        nested = raw.get(key)
        if isinstance(nested, dict) and any(
            nested.get(field) for field in ("kpis", "KPI", "rankings", "榜单", "trends", "趋势", "news", "快讯")
        ):
            return nested
    return raw


def _first_list(data: Dict[str, Any], *keys: str) -> List[Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_kpis(raw_kpis: List[Any]) -> List[Dict[str, Any]]:
    kpis: List[Dict[str, Any]] = []
    for item in raw_kpis[:6]:
        if not isinstance(item, dict):
            continue
        label = _safe_text(item.get("label", item.get("name", item.get("指标", ""))), "")
        value = _safe_text(item.get("value", item.get("数值", "")), "")
        if not label or not value:
            continue
        trend = _safe_text(item.get("trend"), "same").lower()
        if trend not in {"up", "down", "same"}:
            trend = "same"
        kpis.append(
            {
                "label": label,
                "value": value,
                "unit": _safe_text(item.get("unit", item.get("单位", "")), ""),
                "trend": trend,
                "period": _safe_text(item.get("period", item.get("周期", "环比")), "环比"),
                "note": _safe_text(item.get("note", item.get("说明", "")), ""),
            }
        )
    return kpis


def _normalize_rankings(raw_rankings: Any) -> Dict[str, List[Dict[str, Any]]]:
    rankings: Dict[str, List[Dict[str, Any]]] = {"ai_drama": [], "ai_comic": []}
    if not isinstance(raw_rankings, dict):
        return rankings

    drama_list = _first_list(
        raw_rankings,
        "ai_drama",
        "ai_short_drama",
        "ai仿真人剧",
        "仿真人剧",
        "AI仿真人短剧",
        "ai_drama_top5",
    )
    comic_list = _first_list(
        raw_rankings,
        "ai_comic",
        "ai_manga",
        "aigc漫剧",
        "漫剧",
        "AI漫剧",
        "ai_comic_top5",
    )

    for items, key in ((drama_list, "ai_drama"), (comic_list, "ai_comic")):
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items[:5], start=1):
            if not isinstance(item, dict):
                continue
            title = _safe_text(item.get("title", item.get("剧名", "")), "")
            if not title:
                continue
            category = _safe_text(item.get("category", item.get("类型", "")), "")
            if key == "ai_comic" and not category:
                category = "AIGC 漫剧"
            rankings[key].append(
                {
                    "rank": _safe_rank(item.get("rank", idx)) or idx,
                    "title": title,
                    "platform": _safe_text(item.get("platform", item.get("平台", "")), ""),
                    "category": category,
                    "heat": _safe_text(item.get("heat", item.get("热度", "")), ""),
                    "is_new": bool(item.get("is_new", item.get("新剧", False))),
                }
            )
    return rankings


def _normalize_trends(raw_trends: Any) -> List[Dict[str, Any]]:
    trends: List[Dict[str, Any]] = []
    if not isinstance(raw_trends, list):
        return trends
    for item in raw_trends[:5]:
        if isinstance(item, dict):
            title = _safe_text(item.get("title", item.get("标题", "")), "")
            summary = _safe_text(item.get("summary", item.get("摘要", "")), "")
            if title or summary:
                trends.append({"title": title, "summary": summary})
    return trends


def _normalize_news(raw_news: Any) -> List[Dict[str, Any]]:
    news: List[Dict[str, Any]] = []
    if not isinstance(raw_news, list):
        return news
    for item in raw_news[:5]:
        if isinstance(item, dict):
            url = _safe_text(item.get("url", item.get("链接", "")), "")
            title = _safe_text(item.get("title", item.get("标题", "")), "")
            if not title:
                continue
            if url and not url.startswith(("http://", "https://")):
                continue
            news.append(
                {
                    "title": title,
                    "source": _safe_text(item.get("source", item.get("来源", "")), ""),
                    "date": _safe_text(item.get("date", item.get("日期", "")), ""),
                    "url": url,
                }
            )
    return news


def _has_meaningful_dashboard(dashboard: AIDramaDashboard) -> bool:
    if not dashboard:
        return False
    rankings = dashboard.rankings or {}
    return bool(
        dashboard.kpis
        or (rankings.get("ai_drama") or [])
        or (rankings.get("ai_comic") or [])
        or dashboard.trends
        or dashboard.news
    )


def _build_dashboard(raw: Dict[str, Any], report_month: str, data_source: str = "DataEye 月报 + Kimi 搜索") -> AIDramaDashboard:
    dashboard_data = _unwrap_dashboard_payload(raw)

    logger.info(
        "ai_drama_node: 原始数据顶层 keys=%s, dashboard keys=%s",
        list(raw.keys()),
        list(dashboard_data.keys()) if isinstance(dashboard_data, dict) else [],
    )

    kpis = _normalize_kpis(_first_list(dashboard_data, "kpis", "KPI", "核心KPI", "kpi_list", "指标"))
    rankings = _normalize_rankings(dashboard_data.get("rankings", dashboard_data.get("榜单", {})))
    trends = _normalize_trends(_first_list(dashboard_data, "trends", "趋势", "趋势洞察", "insights"))
    news = _normalize_news(_first_list(dashboard_data, "news", "快讯", "行业快讯"))

    if not rankings["ai_drama"] and not rankings["ai_comic"]:
        raw_items = dashboard_data.get("rankings", dashboard_data.get("items", []))
        if isinstance(raw_items, list):
            for item in raw_items[:10]:
                if not isinstance(item, dict):
                    continue
                cat = _safe_text(item.get("category", item.get("类型", "")), "").lower()
                title = _safe_text(item.get("title", item.get("剧名", "")), "")
                if not title:
                    continue
                target = "ai_drama" if any(token in cat for token in ("仿真人", "ai剧", "短剧")) else "ai_comic"
                rankings[target].append(
                    {
                        "rank": _safe_rank(item.get("rank", 0)),
                        "title": title,
                        "platform": _safe_text(item.get("platform", item.get("平台", "")), ""),
                        "category": _safe_text(item.get("category", item.get("类型", "")), ""),
                        "heat": _safe_text(item.get("heat", item.get("热度", "")), ""),
                        "is_new": bool(item.get("is_new", item.get("新剧", False))),
                    }
                )
            rankings["ai_drama"] = sorted(rankings["ai_drama"], key=lambda x: x["rank"])[:5]
            rankings["ai_comic"] = sorted(rankings["ai_comic"], key=lambda x: x["rank"])[:5]

    return AIDramaDashboard(
        report_month=report_month,
        kpis=kpis,
        rankings=rankings,
        trends=trends,
        news=news,
        data_source=data_source,
        update_frequency="monthly",
    )


def _parse_llm_json(raw_text: str) -> Dict[str, Any]:
    parser = MoonshotClient()
    data = parser.extract_json(raw_text, expected_type=dict)
    return data if isinstance(data, dict) else {}


def _extract_dashboard_from_articles(
    articles: List[Dict[str, str]],
    report_month: str,
    cfg: Dict[str, Any],
) -> Optional[AIDramaDashboard]:
    if not articles:
        return None

    year, month = report_month.split("-")
    article_text = combine_articles_text(articles)
    source_note = "澎湃新闻 DataEye 月报直爬 + DeepSeek 抽取"

    extract_template = cfg.get("extract_up", "")
    sp = cfg.get("sp", "")
    if extract_template:
        try:
            prompt = Template(extract_template).render(
                year=year,
                month=int(month),
                report_month=report_month,
                article_text=article_text,
            )
        except Exception as exc:
            logger.warning("ai_drama_node: 渲染 extract_up 失败: %s", exc)
            prompt = f"请从以下原文提取 AI 短剧/漫剧 JSON 数据，report_month={report_month}:\n{article_text}"
    else:
        prompt = f"请从以下原文提取 AI 短剧/漫剧 JSON 数据，report_month={report_month}:\n{article_text}"

    try:
        client = DeepSeekClient()
        raw = client.chat(
            messages=[
                {"role": "system", "content": sp},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        data = _parse_llm_json(raw)
        dashboard = _build_dashboard(data, report_month, data_source=source_note)
        if _has_meaningful_dashboard(dashboard):
            return dashboard
    except Exception as exc:
        logger.warning("ai_drama_node: DeepSeek 抽取 thepaper 原文失败: %s", exc)

    regex_data = regex_extract_dashboard(articles, report_month)
    if regex_data:
        dashboard = _build_dashboard(regex_data, report_month, data_source=regex_data.get("data_source", source_note))
        if _has_meaningful_dashboard(dashboard):
            logger.info("ai_drama_node: 使用规则抽取 thepaper 原文成功")
            return dashboard
    return None


def _discover_thepaper_articles(
    client: MoonshotClient,
    year: int,
    month: int,
) -> List[Dict[str, str]]:
    query = (
        f"请搜索澎湃新闻 thepaper.cn 上 DataEye 发布的 {year}年{month}月 AI剧 漫剧 月报或百强榜文章，"
        "返回可访问的 thepaper 文章链接（newsDetail_forward_数字）。"
    )
    try:
        search_text = client.search(query)
    except Exception as exc:
        logger.warning("ai_drama_node: Kimi 发现 thepaper 文章失败: %s", exc)
        return []
    article_ids = extract_thepaper_ids(search_text)
    if not article_ids:
        return []
    logger.info("ai_drama_node: Kimi 发现 thepaper 文章 ID: %s", article_ids[:5])
    return fetch_articles_by_ids(article_ids[:3])


def _search_ai_drama_data(
    client: MoonshotClient,
    year: int,
    month: int,
    cfg: Dict[str, Any],
    *,
    generic: bool = False,
) -> Dict[str, Any]:
    sp = cfg.get(
        "sp",
        "你是 AI 短剧/漫剧行业数据分析师，擅长从 DataEye 等行业报告和公开信息中提取 AI 短剧、AIGC 漫剧、3D/2D AI 漫剧的 KPI、榜单与趋势。",
    )
    up_template = cfg.get("up", "")

    if generic:
        query = (
            "请联网搜索最新 DataEye AI短剧/漫剧 行业月报或百强榜（优先澎湃新闻 thepaper.cn）。"
            "返回 system prompt 要求的 JSON 结构，字段名必须为英文字段。"
        )
    elif up_template:
        try:
            query = Template(up_template).render(year=year, month=month, date=f"{year}-{month:02d}-01")
        except Exception as exc:
            logger.warning("ai_drama_node: Jinja2 渲染 prompt 失败: %s", exc)
            query = f"请联网搜索 {year}年{month}月 DataEye AI短剧/漫剧 行业月报，返回规定 JSON 结构。"
    else:
        query = f"请联网搜索 {year}年{month}月 DataEye AI短剧/漫剧 行业月报，返回规定 JSON 结构。"

    config_model = cfg.get("config", {})
    temperature = float(config_model.get("temperature", 0.2))
    max_tokens = int(config_model.get("max_completion_tokens", 4000) or 4000)

    try:
        data = client.search_json(
            query=query,
            system_prompt=sp,
            temperature=temperature,
            max_tokens=max_tokens,
            expected_type=dict,
            allow_unknown=False,
        )
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("ai_drama_node: Kimi 搜索失败: %s", exc)
        return {}


def _load_carry_forward_dashboard(report_month: str) -> Optional[AIDramaDashboard]:
    workspace = os.getenv("COZE_WORKSPACE_PATH", os.getcwd())
    latest_path = os.path.join(workspace, "assets", "data", "latest.json")
    if not os.path.exists(latest_path):
        return None
    try:
        with open(latest_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    raw = payload.get("ai_drama_dashboard") or {}
    if not isinstance(raw, dict):
        return None
    try:
        dashboard = AIDramaDashboard(**raw)
    except Exception:
        return None
    if not _has_meaningful_dashboard(dashboard):
        return None
    dashboard.data_source = (
        f"{dashboard.data_source or '历史缓存'}（carry-forward，目标月 {report_month} 暂未获取到新月报）"
    )
    return dashboard


def _try_fetch_dashboard(
    report_month: str,
    cfg: Dict[str, Any],
    client: MoonshotClient,
    *,
    allow_kimi_discovery: bool = True,
) -> Tuple[Optional[AIDramaDashboard], str]:
    year_s, month_s = report_month.split("-")
    year, month = int(year_s), int(month_s)

    articles = fetch_report_articles(report_month)
    if not articles and allow_kimi_discovery:
        articles = _discover_thepaper_articles(client, year, month)

    if articles:
        dashboard = _extract_dashboard_from_articles(articles, report_month, cfg)
        if dashboard:
            return dashboard, ""

    raw_data = _search_ai_drama_data(client, year, month, cfg)
    if raw_data:
        dashboard = _build_dashboard(raw_data, report_month, data_source="DataEye 月报 + Kimi 搜索")
        if _has_meaningful_dashboard(dashboard):
            return dashboard, ""

    return None, f"ai_drama_node: {report_month} 月报未获取到有效数据"


def _empty_output(report_month: str, message: str, source_suffix: str) -> AIDramaNodeOutput:
    return AIDramaNodeOutput(
        ai_drama_dashboard=AIDramaDashboard(
            report_month=report_month,
            data_source=f"DataEye 月报 + Kimi 搜索（{source_suffix}）",
            update_frequency="monthly",
        ),
        error_message=message,
    )


def ai_drama_node(state: AIDramaNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> AIDramaNodeOutput:
    """
    title: 🤖 AI 短剧/漫剧看板
    desc: 月度 DataEye AI 短剧/漫剧月报 + thepaper 直爬 + Kimi 搜索补充
    integrations: Moonshot API, DeepSeek API
    """
    data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
    report_month = _resolve_report_month(data_date)
    logger.info("ai_drama_node: 开始执行, data_date=%s, report_month=%s", data_date, report_month)

    try:
        cache = load_cache(today=data_date)
        if cache:
            dashboard = cache.get("dashboard", {})
            if dashboard.get("report_month") == report_month:
                return AIDramaNodeOutput(
                    ai_drama_dashboard=AIDramaDashboard(**dashboard),
                    error_message="",
                )

        cfg = _load_llm_cfg(config)
        client = MoonshotClient()
        errors: List[str] = []

        dashboard, err = _try_fetch_dashboard(report_month, cfg, client)
        if err:
            errors.append(err)

        if not dashboard:
            prev_month = _shift_report_month(report_month, -1)
            logger.warning("ai_drama_node: 目标月 %s 无数据，尝试上月 %s", report_month, prev_month)
            dashboard, err = _try_fetch_dashboard(prev_month, cfg, client, allow_kimi_discovery=False)
            if dashboard:
                dashboard.report_month = report_month
                dashboard.data_source = f"{dashboard.data_source}（沿用上月 {prev_month} 月报）"
            elif err:
                errors.append(err)

        if not dashboard:
            logger.warning("ai_drama_node: 尝试通用 Kimi 搜索")
            raw_generic = _search_ai_drama_data(client, 0, 0, cfg, generic=True)
            if raw_generic:
                dashboard = _build_dashboard(
                    raw_generic,
                    report_month,
                    data_source="DataEye 月报 + Kimi 通用搜索",
                )
                if not _has_meaningful_dashboard(dashboard):
                    dashboard = None

        if not dashboard:
            dashboard = _load_carry_forward_dashboard(report_month)

        if not dashboard or not _has_meaningful_dashboard(dashboard):
            return _empty_output(
                report_month,
                ";".join(errors) or "ai_drama_node: 所有渠道均未获取到有效 AI 短剧/漫剧数据",
                "未获取到数据",
            )

        try:
            save_cache(dashboard.model_dump(), today=data_date)
        except Exception as exc:
            logger.warning("ai_drama_node: 缓存保存失败: %s", exc)

        return AIDramaNodeOutput(ai_drama_dashboard=dashboard, error_message="")
    except Exception as exc:
        if is_api_budget_error(exc):
            raise
        error_msg = f"ai_drama_node: 节点执行异常: {exc}"
        logger.warning(error_msg, exc_info=True)
        return _empty_output(report_month, error_msg, "节点异常")
