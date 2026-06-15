"""
飞书群机器人推送工具
支持将每日短剧看板数据推送到飞书群，采用交互式卡片消息。
环境变量：
    FEISHU_WEBHOOK: 飞书机器人 webhook 地址（必填）
    FEISHU_WEBHOOK_SECRET: 飞书机器人签名密钥（可选，未配置时不启用签名校验）
"""
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html"


def _get_webhook_url() -> Optional[str]:
    """从环境变量获取 webhook 地址。"""
    url = os.getenv("FEISHU_WEBHOOK", "").strip()
    return url if url else None


def _escape_md(text: str) -> str:
    """转义飞书 lark_md 中的特殊字符。"""
    if not isinstance(text, str):
        text = str(text)
    # 飞书 lark_md 需要转义的字符
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


def _build_header(data_date: str, quality_score: float) -> Dict[str, Any]:
    """构建卡片 header。"""
    quality_emoji = "🟢" if quality_score >= 80 else "🟡" if quality_score >= 60 else "🔴"
    return {
        "tag": "plain_text",
        "content": f"📺 短剧日报 | {data_date} {quality_emoji} 质量分 {quality_score}",
    }


def _build_subtitle(industry: Dict[str, Any]) -> Dict[str, Any]:
    """构建卡片副标题。"""
    drama_count = industry.get("drama_count") or "-"
    app_mau = industry.get("app_mau") or "-"
    ai_ratio = industry.get("ai_ratio", 0)
    female_ratio = industry.get("female_ratio", 0)
    male_ratio = industry.get("male_ratio", 0)
    return {
        "tag": "plain_text",
        "content": f"短剧数 {drama_count} | APP月活 {app_mau} | AI占比 {ai_ratio}% | 女/男 {female_ratio}%/{male_ratio}%",
    }


def _build_rankings_section(rankings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """榜单 TOP5。"""
    lines = ["**🏆 榜单 TOP5**"]
    for item in rankings[:5]:
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
    """演员热力 TOP3。"""
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


def _build_news_section(daily_news: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """行业快讯 TOP3。"""
    if not daily_news:
        return None
    lines = ["**📰 行业快讯 TOP3**"]
    for news in daily_news[:3]:
        icon = news.get("icon") or "📰"
        news_type = news.get("type") or "资讯"
        title = _escape_md(_truncate(news.get("title", "-"), 22))
        content = _escape_md(_truncate(news.get("content", "").replace("\n", " "), 60))
        lines.append(f"{icon} *[{news_type}]* **{title}**\n{content}")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_insights_section(insights: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """今日洞察。"""
    if not insights:
        return None
    lines = ["**💡 今日洞察**"]
    for idx, insight in enumerate(insights[:2], 1):
        icon = insight.get("icon") or "💡"
        title = _escape_md(_truncate(insight.get("title", "-"), 30))
        content = _escape_md(_truncate(insight.get("content", "").replace("\n", " "), 90))
        source = _escape_md(insight.get("source", ""))
        lines.append(f"{icon} **{title}**\n{content}")
        if source:
            lines.append(f"   来源：*{source}*")
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def _build_genre_section(genre_distribution: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """题材/标签风向标。"""
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


def _build_emotion_section(emotional_analysis: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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
        lines.append(_escape_md(_truncate(summary, 80)))
    if dominant_emotion or top_trigger:
        parts = []
        if dominant_emotion:
            parts.append(f"主导情绪：*{_escape_md(dominant_emotion)}*")
        if top_trigger:
            parts.append(f"TOP1触发：*{_escape_md(top_trigger)}*")
        lines.append(" ｜ ".join(parts))
    if insights:
        for idx, insight in enumerate(insights[:2], 1):
            icon = insight.get("icon") or "💡"
            title = _escape_md(_truncate(insight.get("title", "-"), 20))
            content = _escape_md(_truncate(insight.get("content", "").replace("\n", " "), 60))
            lines.append(f"{icon} **{title}**\n{content}")
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


def build_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """从 latest.json 数据构建飞书交互式卡片。"""
    data_date = data.get("data_date") or data.get("generated_at", "")[:10] or "今日"
    quality_score = float(data.get("quality_score") or 0)
    industry = data.get("industry") or {}
    rankings = data.get("rankings") or []
    actors = data.get("actors") or {}
    daily_news = data.get("daily_news") or []
    insights = data.get("insights") or []
    genre_distribution = data.get("genre_distribution") or {}
    emotional_analysis = data.get("emotional_analysis") or data.get("emotion_analysis")
    alerts = data.get("alerts") or []
    alert_count = int(data.get("alert_count") or 0)

    elements: List[Dict[str, Any]] = []
    sections = [
        _build_rankings_section(rankings),
        _build_dark_horse_section(rankings),
        _build_actors_section(actors),
        _build_news_section(daily_news),
        _build_insights_section(insights),
        _build_genre_section(genre_distribution),
        _build_emotion_section(emotional_analysis),
        _build_alerts_section(alerts, alert_count),
    ]
    for section in sections:
        if section:
            elements.append(section)

    # 分隔线与时间戳
    elements.append({
        "tag": "hr",
    })
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
                "title": _build_header(data_date, quality_score),
                "subtitle": _build_subtitle(industry),
            },
            "elements": elements,
        },
    }


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


def push_daily(data: Dict[str, Any], webhook_url: Optional[str] = None) -> bool:
    """一键推送每日日报。"""
    card = build_card(data)
    return send_push(card, webhook_url=webhook_url)


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

    parser = argparse.ArgumentParser(description="手动推送短剧日报到飞书")
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

    card = build_card(data)
    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    ok = send_push(card, webhook_url=args.webhook)
    print("发送结果:", "成功" if ok else "失败")


if __name__ == "__main__":
    main()
