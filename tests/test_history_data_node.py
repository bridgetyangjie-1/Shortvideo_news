"""
历史数据节点单元测试
重点验证：周榜热度趋势以周为粒度，daily_play_trend 由 weekly_rankings 派生。
"""
import unittest
from datetime import datetime

from graphs.nodes.history_data_node import _week_start, _derive_daily_from_weekly


class TestHistoryDataNode(unittest.TestCase):

    def test_week_start_returns_monday(self):
        """任意日期应返回当周周一"""
        # 2026-06-22 是周一
        self.assertEqual(_week_start(datetime(2026, 6, 22)), datetime(2026, 6, 22))
        # 2026-06-25 是周四，应返回 06-22
        self.assertEqual(_week_start(datetime(2026, 6, 25)), datetime(2026, 6, 22))
        # 2026-06-21 是周日，应返回 06-15
        self.assertEqual(_week_start(datetime(2026, 6, 21)), datetime(2026, 6, 15))

    def test_derive_daily_from_weekly(self):
        """daily_play_trend 应由 weekly_rankings 派生，每周一个点"""
        weekly = [
            {"week": "2026-W25", "start_date": "2026-06-22", "total_views": 160000},
            {"week": "2026-W24", "start_date": "2026-06-15", "total_views": 180000},
            {"week": "2026-W23", "start_date": "2026-06-08", "total_views": 150000},
        ]
        daily = _derive_daily_from_weekly(weekly, limit=8)
        # 应返回 3 个点，按日期倒序
        self.assertEqual(len(daily), 3)
        self.assertEqual(daily[0]["date"], "2026-06-22")
        self.assertEqual(daily[0]["total_views"], 160000)
        self.assertEqual(daily[1]["date"], "2026-06-15")
        self.assertEqual(daily[1]["total_views"], 180000)
        self.assertEqual(daily[2]["date"], "2026-06-08")

    def test_derive_daily_limits_to_8(self):
        """限制返回最近 8 周"""
        weekly = [
            {"week": f"2026-W{i:02d}", "start_date": f"2026-01-{i+1:02d}", "total_views": i * 1000}
            for i in range(1, 15)
        ]
        daily = _derive_daily_from_weekly(weekly, limit=8)
        self.assertEqual(len(daily), 8)


if __name__ == "__main__":
    unittest.main()
