"""
AI 短剧/漫剧看板节点单元测试
测试内部纯函数与模型，不依赖真实 API key。
"""
import unittest
from graphs.nodes.ai_drama_node import (
    _resolve_report_month,
    _normalize_kpis,
    _normalize_rankings,
    _normalize_trends,
    _normalize_news,
    _build_dashboard,
)
from graphs.models.ai_drama import AIDramaDashboard


class TestResolveReportMonth(unittest.TestCase):
    def test_normal_month(self):
        self.assertEqual(_resolve_report_month("2026-06-28"), "2026-05")

    def test_january_rolls_to_previous_year(self):
        self.assertEqual(_resolve_report_month("2026-01-15"), "2025-12")


class TestNormalizeKPIs(unittest.TestCase):
    def test_filters_invalid_trend(self):
        raw = [
            {"label": "AI短剧月活", "value": "1.52", "unit": "亿", "trend": "暴涨"},
            {"label": "AI漫剧月活", "value": "0.89", "unit": "亿", "trend": "down"},
        ]
        result = _normalize_kpis(raw)
        self.assertEqual(result[0]["trend"], "same")
        self.assertEqual(result[1]["trend"], "down")


class TestNormalizeRankings(unittest.TestCase):
    def test_splits_drama_and_comic(self):
        raw = {
            "ai_drama": [
                {"rank": 1, "title": "AI剧A", "platform": "红果", "category": "AI仿真人", "heat": "1亿"}
            ],
            "ai_comic": [
                {"rank": 1, "title": "漫剧A", "platform": "腾讯动漫", "category": "AIGC漫剧", "heat": "0.5亿"}
            ],
        }
        result = _normalize_rankings(raw)
        self.assertEqual(len(result["ai_drama"]), 1)
        self.assertEqual(len(result["ai_comic"]), 1)
        self.assertEqual(result["ai_comic"][0]["category"], "AIGC漫剧")

    def test_default_comic_category(self):
        raw = {
            "ai_comic": [
                {"rank": 1, "title": "漫剧A", "platform": "快看", "heat": "0.5亿"}
            ]
        }
        result = _normalize_rankings(raw)
        self.assertEqual(result["ai_comic"][0]["category"], "AIGC 漫剧")


class TestNormalizeNews(unittest.TestCase):
    def test_drops_missing_url(self):
        raw = [
            {"title": "有链接", "source": "A", "date": "2026-05-01", "url": "https://example.com/1"},
            {"title": "无链接", "source": "B", "date": "2026-05-01", "url": ""},
        ]
        result = _normalize_news(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "有链接")


class TestBuildDashboard(unittest.TestCase):
    def test_builds_dashboard(self):
        raw = {
            "kpis": [{"label": "AI短剧月活", "value": "1.52", "unit": "亿", "trend": "up"}],
            "rankings": {
                "ai_drama": [{"rank": 1, "title": "AI剧A", "platform": "红果", "category": "AI仿真人", "heat": "1亿"}],
                "ai_comic": [{"rank": 1, "title": "漫剧A", "platform": "腾讯动漫", "category": "AIGC漫剧", "heat": "0.5亿"}],
            },
            "trends": [{"title": "趋势1", "summary": "摘要1"}],
            "news": [{"title": "新闻1", "source": "DataEye", "date": "2026-05-06", "url": "https://example.com/1"}],
        }
        dashboard = _build_dashboard(raw, "2026-05")
        self.assertIsInstance(dashboard, AIDramaDashboard)
        self.assertEqual(dashboard.report_month, "2026-05")
        self.assertEqual(len(dashboard.kpis), 1)
        self.assertEqual(len(dashboard.rankings["ai_drama"]), 1)
        self.assertEqual(len(dashboard.trends), 1)
        self.assertEqual(len(dashboard.news), 1)


if __name__ == "__main__":
    unittest.main()
