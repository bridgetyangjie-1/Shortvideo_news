"""
本地 SQLite 知识库缓存
避免对同一部剧重复搜索演员/工作室
"""
import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# 缓存数据库路径
DB_PATH = os.path.join(os.getenv("COZE_WORKSPACE_PATH", os.getcwd()), "data", "drama_cache.db")


def _ensure_db() -> None:
    """确保数据库和表存在"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drama_knowledge (
            series_id TEXT PRIMARY KEY,
            title TEXT,
            actors TEXT,          -- JSON: {"female_lead": "...", "male_lead": "..."}
            studio TEXT,
            release_date TEXT,
            tags TEXT,            -- JSON 数组
            first_seen DATE,
            last_verified DATE,
            data_source TEXT      -- hongguo/dataeye/kimi
        )
    """)
    conn.commit()
    conn.close()


def get_drama(series_id: str) -> Optional[Dict[str, Any]]:
    """查询本地缓存，7天内有效"""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT * FROM drama_knowledge WHERE series_id = ? AND last_verified >= ?",
        (series_id, (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "series_id": row[0],
        "title": row[1],
        "actors": json.loads(row[2]) if row[2] else {},
        "studio": row[3] or "",
        "release_date": row[4] or "",
        "tags": json.loads(row[5]) if row[5] else [],
        "first_seen": row[6],
        "last_verified": row[7],
        "data_source": row[8] or ""
    }


def save_drama(
    series_id: str, 
    title: str, 
    actors: Dict[str, str], 
    studio: str, 
    release_date: str, 
    tags: List[str], 
    data_source: str = "hongguo"
) -> None:
    """保存/更新缓存"""
    _ensure_db()
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO drama_knowledge 
        (series_id, title, actors, studio, release_date, tags, first_seen, last_verified, data_source)
        VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT first_seen FROM drama_knowledge WHERE series_id=?), ?), ?, ?)
    """, (
        series_id, title, json.dumps(actors, ensure_ascii=False), 
        studio, release_date, json.dumps(tags, ensure_ascii=False),
        series_id, today, today, data_source
    ))
    conn.commit()
    conn.close()


def batch_get_dramas(series_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """批量查询缓存"""
    _ensure_db()
    if not series_ids:
        return {}
    
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" * len(series_ids))
    cursor = conn.execute(
        f"SELECT * FROM drama_knowledge WHERE series_id IN ({placeholders}) AND last_verified >= ?",
        series_ids + [(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")]
    )
    rows = cursor.fetchall()
    conn.close()
    
    result = {}
    for row in rows:
        result[row[0]] = {
            "series_id": row[0],
            "title": row[1],
            "actors": json.loads(row[2]) if row[2] else {},
            "studio": row[3] or "",
            "release_date": row[4] or "",
            "tags": json.loads(row[5]) if row[5] else [],
            "first_seen": row[6],
            "last_verified": row[7],
            "data_source": row[8] or ""
        }
    return result


def get_cache_stats() -> Dict[str, int]:
    """获取缓存统计"""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT COUNT(*) FROM drama_knowledge")
    total = cursor.fetchone()[0]
    cursor = conn.execute(
        "SELECT COUNT(*) FROM drama_knowledge WHERE last_verified >= ?",
        ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),)
    )
    valid = cursor.fetchone()[0]
    conn.close()
    return {"total": total, "valid_7days": valid}
