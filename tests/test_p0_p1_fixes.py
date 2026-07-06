"""P0/P1 修复相关单元测试"""
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from graphs.nodes.history_data_node import _load_previous_rankings_map
from graphs.nodes.process_node import _find_hongguo_metadata, _normalize_title_key
from graphs.nodes.enrich.fallback import fill_unknown_actors
from tools.actor_name_utils import is_placeholder_actor_name, sanitize_actor_name
from tools.industry_cache import load_seed, _has_valid_industry_payload
from tools.ai_drama_cache import load_cache


class TestActorNameUtils(unittest.TestCase):
    def test_placeholder_names(self):
        for name in ("张三", "李四", "王五", "未知", "男主"):
            self.assertTrue(is_placeholder_actor_name(name))
        self.assertFalse(is_placeholder_actor_name("徐艺真"))

    def test_sanitize_returns_empty_for_placeholder(self):
        self.assertEqual(sanitize_actor_name("张三"), "")


class TestEnrichFallback(unittest.TestCase):
    def test_fill_replaces_placeholder_names(self):
        rankings = [
            {"title": "剧A", "category": "female", "female_lead": "张三", "male_lead": "李四"},
        ]
        filled = fill_unknown_actors(rankings)
        self.assertNotEqual(filled[0]["female_lead"], "张三")
        self.assertNotEqual(filled[0]["male_lead"], "李四")


class TestProcessNodeFuzzyMatch(unittest.TestCase):
    def test_normalize_title_key(self):
        self.assertEqual(_normalize_title_key("我靠听物 成团宠"), "我靠听物成团宠")

    def test_substring_match(self):
        index = {"我靠听物成团宠": {"series_id": "abc123", "title": "我靠听物成团宠"}}
        meta = _find_hongguo_metadata("我靠听物成团宠!", index, index)
        self.assertEqual(meta["series_id"], "abc123")


class TestHistoryRankCompare(unittest.TestCase):
    def test_monday_uses_previous_weekly_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            weekly_dir = Path(tmp) / "assets" / "data" / "weekly"
            weekly_dir.mkdir(parents=True)
            prev_monday = "2026-06-29"
            payload = {
                "rankings": [
                    {"title": "剧A", "rank": 1},
                    {"title": "剧B", "rank": 2},
                ]
            }
            (weekly_dir / f"{prev_monday}.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            os.environ["COZE_WORKSPACE_PATH"] = tmp
            rankings_map, source = _load_previous_rankings_map("2026-07-06", tmp)
            self.assertEqual(rankings_map.get("剧A"), 1)
            self.assertIn("周榜", source)

    def test_weekday_uses_yesterday_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            history_dir = Path(tmp) / "assets" / "data" / "history"
            history_dir.mkdir(parents=True)
            yesterday = "2026-07-06"
            payload = {"rankings": [{"title": "剧C", "rank": 1}]}
            (history_dir / f"{yesterday}.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            rankings_map, source = _load_previous_rankings_map("2026-07-07", tmp)
            self.assertEqual(rankings_map.get("剧C"), 1)
            self.assertIn("昨日", source)


class TestIndustrySeed(unittest.TestCase):
    def test_seed_file_valid(self):
        os.environ.setdefault("COZE_WORKSPACE_PATH", os.getcwd())
        seed = load_seed()
        self.assertIsNotNone(seed)
        self.assertTrue(_has_valid_industry_payload(seed.get("industry", {})))


class TestAIDramaCacheValidation(unittest.TestCase):
    def test_rejects_partial_comic_only_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "data"
            cache_dir.mkdir()
            cache_path = cache_dir / "ai_drama_cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "data_month": "2026-07",
                        "dashboard": {
                            "report_month": "2026-06",
                            "kpis": [{"label": "x", "value": "1", "unit": "亿"}],
                            "rankings": {"ai_drama": [], "ai_comic": [{"rank": 1}] * 5},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.environ["COZE_WORKSPACE_PATH"] = tmp
            # patch CACHE_FILE by reloading - load_cache uses env path
            from importlib import reload
            import tools.ai_drama_cache as mod
            reload(mod)
            result = mod.load_cache(today="2026-07-06")
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
