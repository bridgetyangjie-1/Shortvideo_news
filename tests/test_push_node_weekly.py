"""
Tests for push_node weekly benchmark and archive helpers.
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graphs.nodes.push_node import _build_weekly_base_info, _build_weekly_archive_data
from graphs.state import DramaRanking


class BuildWeeklyBaseInfoTest(unittest.TestCase):
    def test_no_duanju_rankings_returns_unavailable(self):
        rankings = [
            DramaRanking(rank=1, title="剧A", data_source="hongguo_recommend"),
        ]
        info = _build_weekly_base_info(rankings)
        self.assertFalse(info["available"])

    def test_duanju_rankings_returns_top1_info(self):
        rankings = [
            DramaRanking(
                rank=2,
                title="第二名",
                data_source="duanjugongcheng",
                views_num=15000,
                heat=15000,
                genre="古装",
                week_date="2026-06-15",
            ),
            DramaRanking(
                rank=1,
                title="第一名",
                data_source="duanjugongcheng",
                views_num=20000,
                heat=20000,
                genre="都市",
                week_date="2026-06-15",
            ),
        ]
        info = _build_weekly_base_info(rankings)
        self.assertTrue(info["available"])
        self.assertEqual(info["top1_title"], "第一名")
        self.assertEqual(info["top1_index"], 20000)
        self.assertEqual(info["top1_genre"], "都市")
        self.assertEqual(info["week_date"], "2026-06-15")
        self.assertEqual(info["total_count"], 2)
        self.assertEqual(info["data_source"], "duanjugongcheng")


class BuildWeeklyArchiveDataTest(unittest.TestCase):
    def test_non_monday_returns_none(self):
        rankings = [
            DramaRanking(rank=1, title="剧A", data_source="duanjugongcheng"),
        ]
        result = _build_weekly_archive_data(rankings, "2026-06-20", "2026-06-20T00:00:00+08:00")
        self.assertIsNone(result)

    def test_monday_without_duanju_returns_none(self):
        rankings = [
            DramaRanking(rank=1, title="剧A", data_source="hongguo_recommend"),
        ]
        result = _build_weekly_archive_data(rankings, "2026-06-22", "2026-06-22T00:00:00+08:00")
        self.assertIsNone(result)

    def test_monday_with_duanju_returns_archive(self):
        rankings = [
            DramaRanking(
                rank=1,
                title="登顶剧",
                data_source="duanjugongcheng",
                views_num=25000,
                heat=25000,
                genre="甜宠",
                total_index=150000,
                release_date="2026-06-15",
                is_new=True,
                week_date="2026-06-22",
            ),
            DramaRanking(
                rank=2,
                title="第二名",
                data_source="duanjugongcheng",
                views_num=20000,
                heat=20000,
                genre="逆袭",
                total_index=120000,
                release_date="2026-06-10",
                is_new=False,
                week_date="2026-06-22",
            ),
        ]
        result = _build_weekly_archive_data(rankings, "2026-06-22", "2026-06-22T09:00:00+08:00")
        self.assertIsNotNone(result)
        weekly_data, week_date = result
        self.assertEqual(week_date, "2026-06-22")
        self.assertEqual(weekly_data["week_date"], "2026-06-22")
        self.assertEqual(weekly_data["rankings_count"], 2)
        self.assertEqual(weekly_data["generated_at"], "2026-06-22T09:00:00+08:00")

        first = weekly_data["rankings"][0]
        self.assertEqual(first["rank"], 1)
        self.assertEqual(first["title"], "登顶剧")
        self.assertEqual(first["weekly_index"], 25000)
        self.assertEqual(first["total_index"], 150000)
        self.assertEqual(first["release_date"], "2026-06-15")
        self.assertTrue(first["is_new"])
        self.assertEqual(first["week_date"], "2026-06-22")

    def test_week_date_fallback_to_data_date(self):
        rankings = [
            DramaRanking(
                rank=1,
                title="剧A",
                data_source="duanjugongcheng",
                views_num=10000,
                heat=10000,
            ),
        ]
        result = _build_weekly_archive_data(rankings, "2026-06-22", "2026-06-22T00:00:00+08:00")
        weekly_data, week_date = result
        self.assertEqual(week_date, "2026-06-22")
        self.assertEqual(weekly_data["rankings"][0]["week_date"], "2026-06-22")


if __name__ == "__main__":
    unittest.main()
