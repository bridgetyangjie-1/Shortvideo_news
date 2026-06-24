"""
飞书群机器人推送工具
支持将短剧看板数据按日报/周报/月报推送到飞书群，采用交互式卡片消息。

环境变量：
    FEISHU_WEBHOOK: 飞书机器人 webhook 地址（必填）
    FEISHU_WEBHOOK_SECRET: 飞书机器人签名密钥（可选，未配置时不启用签名校验）
"""
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://shortvideo.bridgetyangjie.cn/"


def _get_webhook_url() -> Optional[str]:
    """从环境变量获取 webhook 地址。"""
    url = os.getenv("FEISHU_WEBHOOK", "").strip()
    return url if url else None


def _escape_md(text: str) -> str:
    """转义飞书 lark_md 中的特殊字符。"""
    if not isinstance(text, str):
        text = str(text)
    chars = ["*", "_", "[", "]", "(", ")", "~", "`", "#", "+", "-", "!", "{", "}", "|"]
    for ch in chars:
        text = text.replace(ch, f"\\{ch}")
    return text.replace("\n", "\n")


def _truncate(text: str, max_len: int = 100) -> str:
    """截断文本并补充省略号。"""
    if not isinstance(text, str):
        text = str(text)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _format_rank_change(item: Dict[str, Any]) -> str:
    """格式化榜单变化。"""
    trend_type = item.get("trend_type", "same")
    rank_change = item.get("rank_change", 0)
    if trend_type == "new":
        return "🆕 新晋"
    if trend_type == "up" and rank_change > 0:
        return f"📈 上升{rank_change}"
    if trend_type == "down" and rank_change < 0:
        return f"📉 下降{abs(rank_change)}"
    return "➖ 持平"


def _build_header(data_date: str, quality_score: float, report_type: str) -> Dict[str, Any]:
    """构建卡片 header。"""
    quality_emoji = "🟢" if quality_score >= 80 else "🟡" if quality_score >= 60 else "🔴"
    type_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(report_type, "日报")
    return {
        "tag": "plain_text",
        "content": f"📺 短剧{type_label} | {data_date} {quality_emoji} 质量分 {quality_score}",
    }


def _build_subtitle(industry: Dict[str, Any], report_type: str) -> Dict[str, Any]:
    """构建卡片副标题。"""
    if report_type == "monthly":
        # 月报展示完整行业宏观摘要
        drama_count = industry.get("drama_count") or "-"
        app_mau = industry.get("app_mau") or "-"
        ai_ratio = industry.get("ai_ratio", 0)
        female_ratio = industry.get("female_ratio", 0)
        male_ratio = industry.get("male_ratio", 0)
        user_scale = industry.get("user_scale") or "-"
        market_size = industry.get("market_size") or "-"
        content = (
            f"用户规模 {user_scale} | 市场规模 {market_size} | 短剧数 {drama_count} | "
            f"APP月活 {app_mau} | AI占比 {ai_ratio}% | 女/男 {female_ratio}%/{male_ratio}%"
        )
    elif report_type == "weekly":
        # 周报展示核心行业指标
        drama_count = industry.get("drama_count") or "-"
        app_mau = industry.get("app_mau") or "-"
        ai_ratio = industry.get("ai_ratio", 0)
        female_ratio = industry.get("female_ratio", 0)
        male_ratio = industry.get("male_ratio", 0)
        content = (
            f"短剧数 {drama_count} | APP月活 {app_mau} | AI占比 {ai_ratio}% | 女/男 {female_ratio}%/{male_ratio}%"
        )
    else:
        # 日报极简：只展示质量分和一句话
        content = "今日榜单与行业快讯摘要"
    return {"tag": "plain_text", "content": content}


def _build_rankings_section(rankings: List[Dict[str, Any]], top_n: int = 5) -> Optional[Dict[str, Any]]:
    """榜单 TOP N。"""
    if not rankings:
        return None
    lines = [f"**🏆 榜单 TOP{top_n}**"]
    for item in rankings[:top_n]:
        rank = item.get("rank", 0)
        title = _escape_md(_truncate(item.get("title", "未知剧名"), 20))
        views = item.get("views") or "-"
        change = _format_rank_change(item)
        genre = _escape_md(item.get("genre", ""))
        line = f"{rank}. **{title}**｜{views}｜{change}"
        if genre:
            line += f"｜*{genre}*"
        lines.append(line)
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_dark_horse_section(rankings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """今日黑马（new 或 up >= 3）。"""
    horses = [
        r for r in rankings
        if r.get("trend_type") == "new" or (r.get("trend_type") == "up" and (r.get("rank_change") or 0) >= 3)
    ][:5]
    if not horses:
        return None
    lines = ["**🔥 今日黑马**"]
    for item in horses:
        title = _escape_md(_truncate(item.get("title", "未知剧名"), 18))
        change = _format_rank_change(item)
        tags = item.get("tags") or []
        tag_str = "/".join(_escape_md(t) for t in tags[:2])
        line = f"• **{title}**｜{change}"
        if tag_str:
            line += f"｜*{tag_str}*"
        lines.append(line)
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_actors_section(actors: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """演员热力 TOP3（周报/月报）。"""
    female = actors.get("female") or []
    male = actors.get("male") or []
    if not female and not male:
        return None
    lines = ["**🌟 演员热力 TOP3**"]
    if female:
        names = " / ".join(_escape_md(a.get("name", "-")) for a in female[:3])
        lines.append(f"👩 女频：{names}")
    if male:
        names = " / ".join(_escape_md(a.get("name", "-")) for a in male[:3])
        lines.append(f"👨 男频：{names}")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_news_section(daily_news: List[Dict[str, Any]], max_items: int = 3) -> Optional[Dict[str, Any]]:
    """行业快讯。"""
    if not daily_news:
        return None
    lines = [f"**📰 行业快讯 TOP{max_items}**"]
    for news in daily_news[:max_items]:
        icon = news.get("icon") or "📰"
        news_type = news.get("type") or "资讯"
        title = _escape_md(_truncate(news.get("title", "-"), 22))
        content = _escape_md(_truncate(news.get("content", "").replace("\n", " "), 60))
        lines.append(f"{icon} *[{news_type}]* **{title}**\n{content}")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_insights_section(insights: List[Dict[str, Any]], max_items: int = 2) -> Optional[Dict[str, Any]]:
    """今日洞察。"""
    if not insights:
        return None
    lines = ["**💡 今日洞察**"]
    for idx, insight in enumerate(insights[:max_items], 1):
        icon = insight.get("icon") or "💡"
        title = _escape_md(_truncate(insight.get("title", "-"), 30))
        content = _escape_md(_truncate(insight.get("content", "").replace("\n", " "), 90))
        lines.append(f"{icon} **{title}**\n{content}")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_genre_section(genre_distribution: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """题材/标签风向标（周报/月报）。"""
    trending = genre_distribution.get("trending") or []
    hot_tags = genre_distribution.get("hot_tags") or []
    if not trending and not hot_tags:
        return None
    lines = ["**🎯 题材 & 标签风向标**"]
    if trending:
        trend_parts = []
        for tag in trending[:5]:
            name = _escape_md(tag.get("name", "-"))
            change = tag.get("change", 0)
            trend = tag.get("trend", "same")
            emoji = "🆕" if trend == "new" else "📈" if change > 0 else "📉" if change < 0 else "➖"
            trend_parts.append(f"{name}{emoji}")
        lines.append(f"环比异动：{ ' / '.join(trend_parts)}")
    if hot_tags:
        hot_parts = []
        for tag in hot_tags[:5]:
            name = _escape_md(tag.get("name", "-"))
            value = tag.get("value", 0)
            hot_parts.append(f"{name}({value})")
        lines.append(f"热门标签：{ ' / '.join(hot_parts)}")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_emotion_section(emotional_analysis: Optional[Dict[str, Any]], detailed: bool = False) -> Optional[Dict[str, Any]]:
    """情绪驾驶舱摘要。"""
    if not emotional_analysis:
        return None
    summary = emotional_analysis.get("summary")
    dominant_emotion = emotional_analysis.get("dominant_emotion")
    top_trigger = emotional_analysis.get("top_trigger")
    insights = emotional_analysis.get("actionable_insights") or []
    if not any([summary, dominant_emotion, top_trigger, insights]):
        return None
    lines = ["**🎭 情绪驾驶舱**"]
    if summary:
        lines.append(_escape_md(_truncate(summary, 80 if detailed else 60)))
    if dominant_emotion or top_trigger:
        parts = []
        if dominant_emotion:
            parts.append(f"主导情绪：*{_escape_md(dominant_emotion)}*")
        if top_trigger:
            parts.append(f"TOP1触发：*{_escape_md(top_trigger)}*")
        lines.append(" ｜ ".join(parts))
    if detailed and insights:
        for idx, insight in enumerate(insights[:2], 1):
            icon = insight.get("icon") or "💡"
            title = _escape_md(_truncate(insight.get("title", "-"), 20))
            content = _escape_md(_truncate(insight.get("content", "").replace("\n", " "), 60))
            lines.append(f"{icon} **{title}**\n{content}")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_audience_section(audience_profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """观众画像（月报）。"""
    if not audience_profile:
        return None
    gender = audience_profile.get("gender") or {}
    female = gender.get("female", 0)
    male = gender.get("male", 0)
    age = audience_profile.get("age") or {}
    top_age = max(age.items(), key=lambda x: x[1])[0] if age else "-"
    traits = audience_profile.get("traits") or []
    if not any([female, male, traits]):
        return None
    lines = ["**👥 核心观众画像**"]
    lines.append(f"女性 {female}% / 男性 {male}% | 主力年龄 *{top_age}*")
    if traits:
        lines.append(f"特征：{ ' / '.join(_escape_md(t) for t in traits[:3]) }")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_platform_section(platform: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """平台数据（月报）。"""
    apps = platform.get("apps") or []
    if not apps:
        return None
    lines = ["**📱 平台月活**"]
    for app in apps[:3]:
        name = _escape_md(app.get("name", "-"))
        mau = app.get("mau", 0)
        unit = app.get("mau_unit", "亿")
        yoy = app.get("yoy") or "-"
        lines.append(f"• {name}：{mau}{unit}（同比 {yoy}）")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_weekly_trend_section(play_trend: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """周榜热度趋势（周报/月报）。"""
    if not play_trend:
        return None
    weekly = play_trend.get("weekly") or []
    if len(weekly) < 2:
        return None
    latest = weekly[-1]
    previous = weekly[-2]
    latest_total = latest.get("total_views", 0)
    previous_total = previous.get("total_views", 0)
    if not latest_total or not previous_total:
        return None
    change_pct = round((latest_total - previous_total) / previous_total * 100, 1)
    emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➖"
    lines = ["**📊 周榜热度趋势**"]
    lines.append(
        f"{emoji} 本周总热度 {latest_total}，较上周 {'+' if change_pct >= 0 else ''}{change_pct}%"
    )
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_alerts_section(alerts: List[Dict[str, Any]], alert_count: int) -> Optional[Dict[str, Any]]:
    """异常告警摘要。"""
    if not alerts or alert_count <= 0:
        return None
    lines = [f"**⚠️ 异常监测（共 {alert_count} 条）**"]
    for alert in alerts[:3]:
        severity = alert.get("severity", "info")
        emoji = "🔴" if severity == "critical" else "🟠" if severity == "warning" else "🔵"
        title = _escape_md(_truncate(alert.get("title", "-"), 24))
        message = _escape_md(_truncate(alert.get("message", ""), 60))
        lines.append(f"{emoji} **{title}**\n{message}")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_footer() -> Dict[str, Any]:
    """构建底部按钮。"""
    return {
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看完整看板"},
                "type": "primary",
                "url": DASHBOARD_URL,
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "TOP20 数据"},
                "type": "default",
                "url": "https://bridgetyangjie-1.github.io/Shortvideo_news/assets/data/latest.json",
            },
        ],
    }


def _compose_card(data: Dict[str, Any], report_type: str, sections: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """组装卡片通用结构。"""
    data_date = data.get("data_date") or data.get("generated_at", "")[:10] or "今日"
    quality_score = float(data.get("quality_score") or 0)
    industry = data.get("industry") or {}

    elements: List[Dict[str, Any]] = []
    for section in sections:
        if section:
            elements.append(section)

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [
            {
                "tag": "plain_text",
                "content": f"生成时间：{data.get('generated_at', '-')}",
            }
        ],
    })
    elements.append(_build_footer())

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": _build_header(data_date, quality_score, report_type),
                "subtitle": _build_subtitle(industry, report_type),
            },
            "elements": elements,
        },
    }


def build_daily_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """日报卡片：极简，只放每日变化内容。"""
    rankings = data.get("rankings") or []
    daily_news = data.get("daily_news") or []
    alerts = data.get("alerts") or []
    alert_count = int(data.get("alert_count") or 0)

    sections = [
        _build_rankings_section(rankings, top_n=5),
        _build_dark_horse_section(rankings),
        _build_news_section(daily_news, max_items=1),
        _build_alerts_section(alerts, alert_count),
    ]
    return _compose_card(data, "daily", sections)


def build_weekly_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """周报卡片：日报内容 + 演员/标签/周趋势。"""
    rankings = data.get("rankings") or []
    actors = data.get("actors") or {}
    daily_news = data.get("daily_news") or []
    insights = data.get("insights") or []
    genre_distribution = data.get("genre_distribution") or {}
    emotional_analysis = data.get("emotional_analysis") or data.get("emotion_analysis")
    play_trend = data.get("play_trend") or {}
    alerts = data.get("alerts") or []
    alert_count = int(data.get("alert_count") or 0)

    sections = [
        _build_rankings_section(rankings, top_n=5),
        _build_dark_horse_section(rankings),
        _build_actors_section(actors),
        _build_news_section(daily_news, max_items=3),
        _build_insights_section(insights, max_items=2),
        _build_genre_section(genre_distribution),
        _build_emotion_section(emotional_analysis, detailed=True),
        _build_weekly_trend_section(play_trend),
        _build_alerts_section(alerts, alert_count),
    ]
    return _compose_card(data, "weekly", sections)


def build_monthly_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """月报卡片：周报内容 + 行业宏观/观众画像/平台数据。"""
    rankings = data.get("rankings") or []
    actors = data.get("actors") or {}
    daily_news = data.get("daily_news") or []
    insights = data.get("insights") or []
    genre_distribution = data.get("genre_distribution") or {}
    emotional_analysis = data.get("emotional_analysis") or data.get("emotion_analysis")
    play_trend = data.get("play_trend") or {}
    industry = data.get("industry") or {}
    platform = data.get("platform") or {}
    audience_profile = data.get("audience_profile") or {}
    alerts = data.get("alerts") or []
    alert_count = int(data.get("alert_count") or 0)

    sections = [
        _build_rankings_section(rankings, top_n=5),
        _build_dark_horse_section(rankings),
        _build_actors_section(actors),
        _build_audience_section(audience_profile),
        _build_platform_section(platform),
        _build_news_section(daily_news, max_items=3),
        _build_insights_section(insights, max_items=2),
        _build_genre_section(genre_distribution),
        _build_emotion_section(emotional_analysis, detailed=True),
        _build_weekly_trend_section(play_trend),
        _build_alerts_section(alerts, alert_count),
    ]
    return _compose_card(data, "monthly", sections)


def determine_report_type(data_date: Optional[str] = None) -> str:
    """根据日期判断报告类型：每月1日月报，每周一周报，其他日报。"""
    try:
        dt = datetime.strptime(data_date or datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d")
    except ValueError:
        dt = datetime.now()

    if dt.day == 1:
        return "monthly"
    if dt.weekday() == 0:  # Monday
        return "weekly"
    return "daily"


def build_card(data: Dict[str, Any], report_type: Optional[str] = None) -> Dict[str, Any]:
    """根据报告类型构建对应卡片，未指定时自动判断。"""
    rt = report_type or determine_report_type(data.get("data_date"))
    if rt == "monthly":
        return build_monthly_card(data)
    if rt == "weekly":
        return build_weekly_card(data)
    return build_daily_card(data)


def send_push(card: Dict[str, Any], webhook_url: Optional[str] = None, timeout: int = 30) -> bool:
    """
    发送飞书卡片消息。
    失败仅记录日志，不抛出异常，避免阻断主流程。
    """
    url = webhook_url or _get_webhook_url()
    if not url:
        logger.warning("FEISHU_WEBHOOK 未配置，跳过飞书推送")
        return False

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(url, json=card)
            response.raise_for_status()
            result = response.json()
            if result.get("code") != 0:
                logger.error(f"飞书推送失败: {result}")
                return False
            logger.info("飞书推送成功")
            return True
    except httpx.TimeoutException:
        logger.error("飞书推送超时")
        return False
    except Exception as exc:
        logger.error(f"飞书推送异常: {exc}")
        return False


def push_report(data: Dict[str, Any], report_type: Optional[str] = None, webhook_url: Optional[str] = None) -> bool:
    """推送日报/周报/月报，未指定类型时根据 data_date 自动判断。"""
    rt = report_type or determine_report_type(data.get("data_date"))
    card = build_card(data, rt)
    logger.info("feishu_pusher: 构建%s卡片", {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(rt, rt))
    return send_push(card, webhook_url=webhook_url)


# 兼容旧接口
push_daily = push_report


def push_alert(title: str, message: str, webhook_url: Optional[str] = None) -> bool:
    """推送告警卡片，用于质量门禁失败等场景。"""
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"⚠️ 短剧日报异常告警｜{title}"},
                "subtitle": {"tag": "plain_text", "content": "数据质量门禁未通过，未覆盖 latest.json"},
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": _escape_md(message)},
                },
                _build_footer(),
            ],
        },
    }
    return send_push(card, webhook_url=webhook_url)


def main() -> None:
    """手动触发入口：读取 assets/data/latest.json 并推送。"""
    import argparse

    parser = argparse.ArgumentParser(description="手动推送短剧日报/周报/月报到飞书")
    parser.add_argument(
        "--data",
        default="assets/data/latest.json",
        help="要推送的数据文件路径，默认 assets/data/latest.json",
    )
    parser.add_argument(
        "--webhook",
        default=None,
        help="飞书 webhook 地址，默认读取 FEISHU_WEBHOOK 环境变量",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="发送告警测试卡片而非日报",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="强制发送日报",
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="强制发送周报",
    )
    parser.add_argument(
        "--monthly",
        action="store_true",
        help="强制发送月报",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只构建卡片并打印，不真正发送",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.alert:
        card = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "⚠️ 测试告警"},
                    "subtitle": {"tag": "plain_text", "content": "这是一条飞书告警测试"},
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": "飞书机器人配置正确，可以正常接收告警消息。"},
                    },
                    _build_footer(),
                ],
            },
        }
        if args.dry_run:
            print(json.dumps(card, ensure_ascii=False, indent=2))
        else:
            ok = send_push(card, webhook_url=args.webhook)
            print("发送结果:", "成功" if ok else "失败")
        return

    if not os.path.exists(args.data):
        logger.error(f"数据文件不存在: {args.data}")
        return

    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    report_type = None
    if args.monthly:
        report_type = "monthly"
    elif args.weekly:
        report_type = "weekly"
    elif args.daily:
        report_type = "daily"

    card = build_card(data, report_type)
    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    ok = send_push(card, webhook_url=args.webhook)
    print("发送结果:", "成功" if ok else "失败")


if __name__ == "__main__":
    main()
