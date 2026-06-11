"""
榜单数量质量门禁。

前端展示为 TOP8，因此数据链路不能把少于 8 条的 rankings 直接发布。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Tuple


REQUIRED_TOP_RANKING_COUNT = 8
RECENT_HISTORY_DAYS = 7


class RankingCountError(ValueError):
    """榜单数量不足且无法补齐时抛出。"""


def ensure_top_rankings(
    rankings: Iterable[Any],
    *,
    data_date: str = "",
    target_count: int = REQUIRED_TOP_RANKING_COUNT,
    supplemental_rankings: Iterable[Any] | None = None,
    workspace_path: str | None = None,
) -> Tuple[List[dict], str]:
    """
    返回严格达到 target_count 条的榜单字典列表。

    补齐优先级：
    1. 当前节点输出的 rankings；
    2. 上游传入的 supplemental_rankings；
    3. 近 7 天历史归档榜单。

    如果所有来源合并后仍不足 target_count，则抛出 RankingCountError，避免覆盖页面。
    """
    primary_items = _normalize_rankings(rankings)
    items = _merge_rankings(primary_items, _normalize_rankings(supplemental_rankings or []))
    history_used = False

    if len(items) < target_count:
        history_items = _load_recent_history_rankings(
            data_date=data_date,
            workspace_path=workspace_path,
        )
        before_history = len(items)
        items = _merge_rankings(items, history_items)
        history_used = len(items) > before_history

    if len(items) < target_count:
        raise RankingCountError(
            f"榜单数量不足：当前可用 {len(items)} 条，要求至少 {target_count} 条；"
            "已拒绝发布以避免 TOP8 页面显示不完整。"
        )

    items = _renumber(items[:target_count])
    warning = ""
    if len(primary_items) < target_count:
        warning = (
            f"rankings 不足 {target_count} 条，已由 {len(primary_items)} 条补齐到 "
            f"{target_count} 条"
        )
        if history_used:
            warning += "（使用近 7 天历史榜单补位）"
        warning += "。"

    return items, warning


def _normalize_rankings(rankings: Iterable[Any]) -> List[dict]:
    normalized: List[dict] = []
    for raw_item in rankings:
        item = _to_dict(raw_item)
        title = str(item.get("title") or "").strip()
        if not title:
            continue

        normalized.append(
            {
                **item,
                "rank": _safe_int(item.get("rank"), len(normalized) + 1),
                "title": title,
                "female_lead": _safe_text(item.get("female_lead"), ""),
                "male_lead": _safe_text(item.get("male_lead"), ""),
                "views": _safe_text(item.get("views"), ""),
                "views_num": _safe_int(
                    item.get("views_num"),
                    _parse_views_num(item.get("views")),
                ),
                "platform": _safe_text(item.get("platform"), "红果"),
                "genre": _safe_text(item.get("genre"), ""),
                "tags": _ensure_text_list(item.get("tags")),
                "trend": _safe_text(item.get("trend"), ""),
                "trend_tag": _safe_text(item.get("trend_tag"), ""),
                "trend_type": _safe_text(item.get("trend_type"), "same"),
                "category": _safe_text(item.get("category"), "female"),
                "is_ai": bool(item.get("is_ai", False)),
                "desc": _safe_text(item.get("desc"), ""),
                "change": _safe_text(item.get("change"), ""),
                "heat": _safe_int(item.get("heat"), _safe_int(item.get("views_num"), 0)),
                "production_house": _safe_text(item.get("production_house"), "独立厂牌"),
                "core_trope": _ensure_text_list(item.get("core_trope")),
                "episodes_count": _safe_int(item.get("episodes_count"), 80),
            }
        )
    return normalized


def _to_dict(item: Any) -> dict:
    if item is None:
        return {}
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if isinstance(item, dict):
        return dict(item)
    return {}


def _merge_rankings(primary: Iterable[dict], supplemental: Iterable[dict]) -> List[dict]:
    merged: List[dict] = []
    seen_titles: set[str] = set()

    for item in list(primary) + list(supplemental):
        title_key = _title_key(item.get("title"))
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        merged.append(dict(item))

    return _renumber(merged)


def _renumber(items: Iterable[dict]) -> List[dict]:
    numbered_items = [dict(item) for item in items]
    for index, item in enumerate(numbered_items, start=1):
        item["rank"] = index
        if not item.get("heat"):
            item["heat"] = _safe_int(item.get("views_num"), 0)
    return numbered_items


def _load_recent_history_rankings(*, data_date: str, workspace_path: str | None) -> List[dict]:
    workspace = Path(
        workspace_path
        or os.getenv("COZE_WORKSPACE_PATH")
        or Path(__file__).resolve().parents[2]
    )
    history_dir = workspace / "assets" / "data" / "history"
    if not history_dir.exists():
        return []

    target_date = _parse_date(data_date)
    candidates: List[tuple[datetime, dict]] = []

    for history_file in history_dir.glob("*.json"):
        file_date = _parse_date(history_file.stem)
        if target_date and file_date:
            day_gap = (target_date.date() - file_date.date()).days
            if day_gap < 0 or day_gap > RECENT_HISTORY_DAYS:
                continue

        try:
            with history_file.open("r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except (OSError, json.JSONDecodeError):
            continue

        for item in _normalize_rankings(payload.get("rankings") or []):
            if not item.get("trend_tag"):
                item["trend_tag"] = "📌 近7日补位"
            candidates.append((file_date or datetime.min, item))

    candidates.sort(
        key=lambda pair: (
            pair[0],
            _safe_int(pair[1].get("views_num"), 0),
        ),
        reverse=True,
    )
    return [item for _, item in candidates]


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _safe_text(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _ensure_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[、,，/|｜；;\s]+", value) if part.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _parse_views_num(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0

    match = re.search(r"(\d+(?:\.\d+)?)\s*([亿万]?)", text)
    if not match:
        return 0

    number = float(match.group(1))
    unit = match.group(2)
    if unit == "亿":
        number *= 10000
    return int(round(number))


def _title_key(title: Any) -> str:
    return re.sub(r"\s+", "", str(title or "").strip().lower())
