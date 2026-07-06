"""
AI 短剧/漫剧看板节点与抓取器单元测试
"""
import unittest
from unittest.mock import MagicMock, patch

from graphs.nodes.ai_drama_node import (
    _resolve_report_month,
    _normalize_kpis,
    _normalize_rankings,
    _normalize_news,
    _normalize_trends,
    _build_dashboard,
    _has_meaningful_dashboard,
    _unwrap_dashboard_payload,
    REPORT_PUBLISH_DAY,
)
from graphs.models.ai_drama import AIDramaDashboard
from tools.ai_drama_fetcher import (
    extract_thepaper_ids,
    regex_extract_dashboard,
    strip_html,
)


class TestResolveReportMonth(unittest.TestCase):
    def test_normal_month_after_publish_day(self):
        # 28 号 >= 18 号，取上个月
        self.assertEqual(_resolve_report_month("2026-06-28"), "2026-05")

    def test_normal_month_before_publish_day(self):
        # 6 号 < 18 号，最新完整月报为上上个月
        self.assertEqual(_resolve_report_month("2026-06-06"), "2026-04")

    def test_january_rolls_to_previous_year(self):
        # 1 月 10 号 < 18 号，回退两个月到上年 11 月
        self.assertEqual(_resolve_report_month("2026-01-15"), "2025-11")


class TestNormalizeKPIs(unittest.TestCase):
    def test_filters_invalid_trend(self):
        raw = [
            {"label": "AI短剧月活", "value": "1.52", "unit": "亿", "trend": "暴涨"},
            {"label": "AI漫剧月活", "value": "0.89", "unit": "亿", "trend": "down"},
        ]
        result = _normalize_kpis(raw)
        self.assertEqual(result[0]["trend"], "same")
        self.assertEqual(result[1]["trend"], "down")

    def test_drops_empty_label_or_value(self):
        raw = [
            {"label": "", "value": "1.52"},
            {"label": "有效指标", "value": ""},
            {"label": "月新增", "value": "3.95", "unit": "万部"},
        ]
        result = _normalize_kpis(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["label"], "月新增")


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

    def test_supports_chinese_keys(self):
        raw = {
            "仿真人剧": [{"剧名": "换亲成宠", "平台": "抖音", "热度": "8.7亿", "rank": 1}],
            "漫剧": [{"剧名": "聚宝仙盆", "平台": "红果", "类型": "3D漫", "rank": 1}],
        }
        result = _normalize_rankings(raw)
        self.assertEqual(result["ai_drama"][0]["title"], "换亲成宠")
        self.assertEqual(result["ai_comic"][0]["title"], "聚宝仙盆")

    def test_extracts_new_fields(self):
        raw = {
            "ai_drama": [
                {
                    "rank": 1,
                    "title": "换亲成宠",
                    "platform": "抖音",
                    "category": "AI仿真人剧",
                    "heat": "8.7亿",
                    "plot": "换亲嫁入豪门逆袭成宠",
                    "tags": ["逆袭", "乡村", "换亲"],
                    "studio": "麦芽",
                    "url": "https://example.com/1",
                }
            ]
        }
        result = _normalize_rankings(raw)
        item = result["ai_drama"][0]
        self.assertEqual(item["plot"], "换亲嫁入豪门逆袭成宠")
        self.assertEqual(item["tags"], ["逆袭", "乡村", "换亲"])
        self.assertEqual(item["studio"], "麦芽")
        self.assertEqual(item["url"], "https://example.com/1")

    def test_truncates_long_plot_and_tags(self):
        raw = {
            "ai_drama": [
                {
                    "rank": 1,
                    "title": "A",
                    "plot": "x" * 200,
                    "tags": ["1", "2", "3", "4", "5"],
                }
            ]
        }
        result = _normalize_rankings(raw)
        item = result["ai_drama"][0]
        self.assertTrue(item["plot"].endswith("..."))
        self.assertEqual(len(item["tags"]), 4)


class TestNormalizeTrends(unittest.TestCase):
    def test_extracts_source_url(self):
        raw = [
            {"title": "3D漫升温", "summary": "3D漫占比提升", "source": "DataEye", "source_url": "https://thepaper.cn/1"}
        ]
        result = _normalize_trends(raw)
        self.assertEqual(result[0]["source"], "DataEye")
        self.assertEqual(result[0]["source_url"], "https://thepaper.cn/1")


class TestNormalizeNews(unittest.TestCase):
    def test_allows_missing_url(self):
        raw = [
            {"title": "有链接", "source": "A", "date": "2026-05-01", "url": "https://example.com/1"},
            {"title": "无链接", "source": "B", "date": "2026-05-01", "url": ""},
        ]
        result = _normalize_news(raw)
        self.assertEqual(len(result), 2)

    def test_extracts_summary(self):
        raw = [
            {"title": "出海", "source": "A", "date": "2026-05-01", "url": "https://x.com", "summary": "AI短剧出海增长快"}
        ]
        result = _normalize_news(raw)
        self.assertEqual(result[0]["summary"], "AI短剧出海增长快")


class TestBuildDashboard(unittest.TestCase):
    def test_unwraps_nested_dashboard(self):
        raw = {
            "dashboard": {
                "kpis": [{"label": "月新增", "value": "4.4", "unit": "万部", "trend": "down"}],
                "rankings": {"ai_drama": [{"rank": 1, "title": "AI剧A", "platform": "抖音", "category": "AI仿真人剧", "heat": "8亿"}]},
            }
        }
        dashboard = _build_dashboard(raw, "2026-04")
        self.assertTrue(_has_meaningful_dashboard(dashboard))
        self.assertEqual(dashboard.kpis[0].value, "4.4")

    def test_empty_dashboard_not_meaningful(self):
        dashboard = AIDramaDashboard(report_month="2026-06")
        self.assertFalse(_has_meaningful_dashboard(dashboard))


class TestAIDramaFetcher(unittest.TestCase):
    def test_strip_html(self):
        html = "<p>新增AI剧/漫剧约<strong>4.4</strong>万部</p>"
        self.assertIn("4.4", strip_html(html))

    def test_extract_thepaper_ids(self):
        text = "详见 https://m.thepaper.cn/newsDetail_forward_33198460 与 newsDetail_forward_33335582"
        self.assertEqual(extract_thepaper_ids(text), ["33198460", "33335582"])

    def test_regex_extract_dashboard(self):
        articles = [
            {
                "title": "4月AI剧/漫剧月报",
                "url": "https://m.thepaper.cn/newsDetail_forward_33198460",
                "text": (
                    "根据DataEye-ADX行业版数据显示，4月单月新增AI剧/漫剧约4.4万部，"
                    "播放破亿的有267部，破百万率14.6%。"
                    "《财神天降，送我上青云》单月播放增量达9.27亿。"
                ),
            }
        ]
        data = regex_extract_dashboard(articles, "2026-04")
        self.assertGreaterEqual(len(data.get("kpis", [])), 2)
        self.assertTrue(data.get("rankings", {}).get("ai_drama") or data.get("news"))

    def test_regex_extracts_top_from_may_report(self):
        text = (
            "5月抖音端原生百强榜中，麦芽的《换亲成宠》登顶；"
            "宇瀚忠毅制作的《从此朵朵花开》第二，版权方为新漫跳动；"
            "西垚数字制作的《离婚后，我与苏大小姐闪婚了》第三。"
            "5月红果AI剧/漫剧百强榜中，陈柯文化的《聚宝仙盆之杂灵根才是真BOSS第四季》第一，最高热度达8044W；"
            "《山海藏墟，无眼窥天》第三，最高热度达6975万。"
        )
        data = regex_extract_dashboard([{"title": "5月月报", "url": "https://x", "text": text}], "2026-05")
        ai_drama = data.get("rankings", {}).get("ai_drama", [])
        ai_comic = data.get("rankings", {}).get("ai_comic", [])
        titles = [i["title"] for i in ai_drama + ai_comic]
        self.assertIn("换亲成宠", titles)
        self.assertIn("聚宝仙盆之杂灵根才是真BOSS第四季", titles)


class TestUnwrapDashboardPayload(unittest.TestCase):
    def test_unwraps_data_key(self):
        raw = {"data": {"kpis": [{"label": "测试", "value": "1"}]}}
        nested = _unwrap_dashboard_payload(raw)
        self.assertIn("kpis", nested)


if __name__ == "__main__":
    unittest.main()
