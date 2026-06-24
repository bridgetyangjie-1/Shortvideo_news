"""
周更缓存工具单元测试
"""
import os
import shutil
import tempfile
import unittest

from tools import weekly_cache


class WeeklyCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.original_dir = weekly_cache.CACHE_DIR
        weekly_cache.CACHE_DIR = os.path.join(self.tmpdir, "weekly_cache")

    def tearDown(self) -> None:
        weekly_cache.CACHE_DIR = self.original_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_is_refresh_day_monday(self) -> None:
        self.assertTrue(weekly_cache.is_refresh_day("2025-06-09"))   # 周一
        self.assertFalse(weekly_cache.is_refresh_day("2025-06-10"))  # 周二
        self.assertFalse(weekly_cache.is_refresh_day("2025-06-15"))  # 周日

    def test_week_key_returns_monday(self) -> None:
        self.assertEqual(weekly_cache._week_key("2025-06-09"), "2025-06-09")  # 周一
        self.assertEqual(weekly_cache._week_key("2025-06-10"), "2025-06-09")  # 周二
        self.assertEqual(weekly_cache._week_key("2025-06-15"), "2025-06-09")  # 周日

    def test_save_and_load_cache_roundtrip(self) -> None:
        payload = {"insights": [{"title": "洞察1"}]}
        weekly_cache.save_cache("insights", payload, "2025-06-10")
        loaded = weekly_cache.load_cache("insights", "2025-06-11")
        self.assertEqual(loaded, payload)

    def test_cache_miss_returns_none(self) -> None:
        self.assertIsNone(weekly_cache.load_cache("insights", "2025-06-10"))

    def test_different_keys_do_not_conflict(self) -> None:
        weekly_cache.save_cache("insights", {"v": 1}, "2025-06-10")
        weekly_cache.save_cache("actors", {"v": 2}, "2025-06-10")
        self.assertEqual(weekly_cache.load_cache("insights", "2025-06-10"), {"v": 1})
        self.assertEqual(weekly_cache.load_cache("actors", "2025-06-10"), {"v": 2})


if __name__ == "__main__":
    unittest.main()
