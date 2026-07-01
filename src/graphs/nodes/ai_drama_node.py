"""
🤖 AI 短剧/漫剧看板节点

策略：
1. 以自然月为粒度缓存，月初/缓存缺失时使用 Kimi 联网搜索 DataEye 等行业月报。
2. 日常运行直接读取缓存，不重复调用 API。
3. 搜索失败或字段缺失时留空，不返回固定默认值。
"""
import json
import os
import re
import logging
from datetime import datetime
from typing import Any, Dict, List
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from coze_coding_utils.runtime_ctx.context import Context

from tools.moonshot_api import MoonshotClient
from tools.ai_drama_cache import load_cache, save_cache
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

    # 尝试默认路径
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


def _normalize_kpis(raw_kpis: List[Any]) -> List[Dict[str, Any]]:
    """规范化 KPI 列表"""
    kpis: List[Dict[str, Any]] = []
    for item in raw_kpis[:6]:
        if not isinstance(item, dict):
            continue
        trend = _safe_text(item.get("trend"), "same").lower()
        if trend not in {"up", "down", "same"}:
            trend = "same"
        kpis.append(
            {
                "label": _safe_text(item.get("label", item.get("name", "")), ""),
                "value": _safe_text(item.get("value", item.get("数值", "")), ""),
                "unit": _safe_text(item.get("unit", item.get("单位", "")), ""),
                "trend": trend,
                "period": _safe_text(item.get("period", item.get("周期", "环比")), "环比"),
                "note": _safe_text(item.get("note", item.get("说明", "")), ""),
            }
        )
    return kpis


def _normalize_rankings(raw_rankings: Any) -> Dict[str, List[Dict[str, Any]]]:
    """规范化榜单，分为 ai_drama 和 ai_comic"""
    rankings: Dict[str, List[Dict[str, Any]]] = {"ai_drama": [], "ai_comic": []}
    if not isinstance(raw_rankings, dict):
        return rankings

    drama_list = raw_rankings.get("ai_drama") or raw_rankings.get("ai_short_drama") or raw_rankings.get("ai仿真人剧") or []
    comic_list = raw_rankings.get("ai_comic") or raw_rankings.get("ai_manga") or raw_rankings.get("aigc漫剧") or raw_rankings.get("漫剧") or []

    for items, key in ((drama_list, "ai_drama"), (comic_list, "ai_comic")):
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items[:5], start=1):
            if not isinstance(item, dict):
                continue
            category = _safe_text(
                item.get("category", item.get("类型", "")), ""
            )
            # 漫剧榜单如果没有 category，默认归为 AIGC 漫剧
            if key == "ai_comic" and not category:
                category = "AIGC 漫剧"
            rankings[key].append(
                {
                    "rank": _safe_rank(item.get("rank", idx)),
                    "title": _safe_text(item.get("title", item.get("剧名", "")), ""),
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
            trends.append(
                {
                    "title": _safe_text(item.get("title", item.get("标题", "")), ""),
                    "summary": _safe_text(item.get("summary", item.get("摘要", "")), ""),
                }
            )
    return trends


def _normalize_news(raw_news: Any) -> List[Dict[str, Any]]:
    news: List[Dict[str, Any]] = []
    if not isinstance(raw_news, list):
        return news
    for item in raw_news[:5]:
        if isinstance(item, dict):
            url = _safe_text(item.get("url", item.get("链接", "")), "")
            if not url.startswith(("http://", "https://")):
                continue
            news.append(
                {
                    "title": _safe_text(item.get("title", item.get("标题", "")), ""),
                    "source": _safe_text(item.get("source", item.get("来源", "")), ""),
                    "date": _safe_text(item.get("date", item.get("日期", "")), ""),
                    "url": url,
                }
            )
    return news


def _build_dashboard(raw: Dict[str, Any], report_month: str) -> AIDramaDashboard:
    """将原始搜索结果转换为规范模型"""
    dashboard_data = raw.get("dashboard", raw)
    if not isinstance(dashboard_data, dict):
        dashboard_data = raw

    kpis = _normalize_kpis(dashboard_data.get("kpis", dashboard_data.get("KPI", [])))
    rankings = _normalize_rankings(dashboard_data.get("rankings", dashboard_data.get("榜单", {})))
    trends = _normalize_trends(dashboard_data.get("trends", dashboard_data.get("趋势", [])))
    news = _normalize_news(dashboard_data.get("news", dashboard_data.get("快讯", [])))

    # 回退：如果 rankings 未分层但有 items 数组，按 category 自动分流
    if not rankings["ai_drama"] and not rankings["ai_comic"]:
        raw_items = dashboard_data.get("rankings", dashboard_data.get("items", []))
        if isinstance(raw_items, list):
            for item in raw_items[:10]:
                if not isinstance(item, dict):
                    continue
                cat = _safe_text(item.get("category", item.get("类型", "")), "").lower()
                if "仿真人" in cat or "ai剧" in cat or "短剧" in cat:
                    target = "ai_drama"
                else:
                    target = "ai_comic"
                rankings[target].append(
                    {
                        "rank": _safe_rank(item.get("rank", 0)),
                        "title": _safe_text(item.get("title", item.get("剧名", "")), ""),
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
        data_source="DataEye 月报 + Kimi 搜索",
        update_frequency="monthly",
    )


def _search_ai_drama_data(client: MoonshotClient, year: int, month: int, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """使用 Kimi 搜索 AI 短剧/漫剧月报数据"""
    sp = cfg.get(
        "sp",
        "你是 AI 短剧/漫剧行业数据分析师，擅长从 DataEye 等行业报告和公开信息中提取 AI 短剧、AIGC 漫剧、3D/2D AI 漫剧的 KPI、榜单与趋势。",
    )
    up_template = cfg.get("up", "")

    query = f"""请联网搜索 {year}年{month}月 DataEye AI短剧/漫剧 行业月报或权威报道。

需要提取：
1. 4 个核心 KPI（如 AI 短剧月活用户、AI 短剧/漫剧市场规模、AI 短剧渗透率、AI 漫剧月活用户等），含数值、单位、环比趋势。
2. AI 仿真人短剧 TOP5 剧名、平台、类型、热度。
3. AIGC/3D/2D AI 漫剧 TOP5 剧名、平台、类型、热度。
4. 3-5 条趋势洞察，每条 50-100 字。
5. 3-5 条 AI 短剧/漫剧行业快讯（标题、来源、日期、链接）。

只收录真正的 AI 短剧/漫剧，排除普通沙雕漫、真人短剧。若数据不足请留空，不要编造。
返回合法 JSON，不要 Markdown 代码块。"""

    if up_template:
        try:
            query = Template(up_template).render(year=year, month=month, date=f"{year}-{month:02d}-01")
        except Exception as e:
            logger.warning("ai_drama_node: Jinja2 渲染 prompt 失败，使用内置 prompt: %s", e)

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
        )
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as e:
        logger.warning("ai_drama_node: Kimi 搜索失败: %s", e)
        return {}


def ai_drama_node(state: AIDramaNodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> AIDramaNodeOutput:
    """
    title: 🤖 AI 短剧/漫剧看板
    desc: 月度 DataEye AI 短剧/漫剧月报 + Kimi 搜索补充，输出 KPI、榜单、趋势、快讯
    integrations: Moonshot API
    """
    data_date = state.data_date or datetime.now().strftime("%Y-%m-%d")
    report_month = _resolve_report_month(data_date)

    try:
        # 1. 尝试读取月度缓存
        cache = load_cache(today=data_date)
        if cache:
            dashboard = cache.get("dashboard", {})
            # 缓存的 report_month 与目标月份不一致时重新搜索
            if dashboard.get("report_month") == report_month:
                return AIDramaNodeOutput(
                    ai_drama_dashboard=AIDramaDashboard(**dashboard),
                    error_message="",
                )

        # 2. 读取配置
        cfg = _load_llm_cfg(config)
        try:
            dt = datetime.strptime(report_month, "%Y-%m")
            year, month = dt.year, dt.month
        except ValueError:
            now = datetime.now()
            year, month = now.year, now.month

        # 3. 调用 Kimi 搜索
        client = MoonshotClient()
        raw_data = _search_ai_drama_data(client, year, month, cfg)

        if not raw_data:
            logger.warning("ai_drama_node: 未获取到 AI 短剧/漫剧数据，返回空看板")
            return AIDramaNodeOutput(
                ai_drama_dashboard=AIDramaDashboard(
                    report_month=report_month,
                    data_source="DataEye 月报 + Kimi 搜索（未获取到数据）",
                    update_frequency="monthly",
                ),
                error_message="ai_drama_node: 未获取到 AI 短剧/漫剧数据",
            )

        # 4. 规范化并保存缓存
        dashboard = _build_dashboard(raw_data, report_month)
        try:
            save_cache(dashboard.model_dump(), today=data_date)
        except Exception as e:
            logger.warning("ai_drama_node: 缓存保存失败: %s", e)

        return AIDramaNodeOutput(
            ai_drama_dashboard=dashboard,
            error_message="",
        )
    except Exception as e:
        error_msg = f"ai_drama_node: 节点执行异常: {e}"
        logger.warning(error_msg, exc_info=True)
        return AIDramaNodeOutput(
            ai_drama_dashboard=AIDramaDashboard(
                report_month=report_month,
                data_source="DataEye 月报 + Kimi 搜索（节点异常）",
                update_frequency="monthly",
            ),
            error_message=error_msg,
        )
