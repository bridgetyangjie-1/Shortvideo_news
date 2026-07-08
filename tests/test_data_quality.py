"""P0 数据质量校验单元测试"""
import unittest

from utils.data_quality import (
    count_ranking_hallucinations,
    extract_insight_from_content,
    is_hallucinated_actor_name,
    is_mainstream_celebrity,
    is_suspicious_studio_name,
    is_trusted_news_url,
    is_unreliable_actor_name,
    sanitize_actor_field,
    sanitize_production_house,
)
from tools.actor_name_utils import is_placeholder_actor_name


class TestHallucinatedActorNames(unittest.TestCase):
    def test_numbered_placeholders_detected(self):
        for name in ("李十三", "王十四", "钱十六", "周十八", "吴十九", "钱二十一"):
            self.assertTrue(is_hallucinated_actor_name(name), name)

    def test_real_names_not_flagged(self):
        for name in ("徐艺真", "曾辉", "王道铁", "何健麒", "马秋元"):
            self.assertFalse(is_hallucinated_actor_name(name), name)

    def test_placeholder_via_utils(self):
        self.assertTrue(is_placeholder_actor_name("张三"))
        self.assertTrue(is_placeholder_actor_name("待核实"))


class TestMainstreamActorFilter(unittest.TestCase):
    def test_mainstream_celebrities_blocked(self):
        for name in ("周迅", "赵丽颖", "杨幂", "胡歌", "孙红雷", "邓超"):
            self.assertTrue(is_mainstream_celebrity(name), name)
            self.assertTrue(is_unreliable_actor_name(name), name)
            self.assertEqual(sanitize_actor_field(name), "")

    def test_short_drama_actors_allowed(self):
        for name in ("徐艺真", "曾辉", "王道铁", "何健麒", "马秋元"):
            self.assertFalse(is_mainstream_celebrity(name), name)
            self.assertFalse(is_unreliable_actor_name(name), name)

    def test_generic_names_blocked(self):
        for name in ("张伟", "王强", "赵丽"):
            self.assertTrue(is_unreliable_actor_name(name), name)

    def test_hallucination_count_includes_mainstream(self):
        rankings = [
            {"title": "剧A", "female_lead": "周迅", "male_lead": "", "production_house": "九州"},
            {"title": "剧B", "female_lead": "徐艺真", "male_lead": "", "production_house": "九州"},
        ]
        stats = count_ranking_hallucinations(rankings)
        self.assertEqual(stats["actor_hits"], 1)


class TestSuspiciousStudios(unittest.TestCase):
    def test_template_studios_detected(self):
        for name in ("蓝海影视工作室", "红星影视公司", "绿岛影视工作室", "青鸟影视工作室"):
            self.assertTrue(is_suspicious_studio_name(name), name)

    def test_known_studios_ok(self):
        for name in ("九州", "点众", "麦芽", "网易"):
            self.assertFalse(is_suspicious_studio_name(name), name)

    def test_sanitize_removes_suspicious(self):
        self.assertEqual(sanitize_production_house("蓝海影视工作室"), "")
        self.assertEqual(sanitize_production_house("九州"), "九州")


class TestNewsUrlValidation(unittest.TestCase):
    def test_blocks_example_and_search_urls(self):
        self.assertFalse(is_trusted_news_url("https://www.example.com/article1"))
        self.assertFalse(is_trusted_news_url("https://www.google.com/search?q=test"))
        self.assertTrue(is_trusted_news_url("https://www.thepaper.cn/newsDetail_forward_123"))


class TestInsightExtraction(unittest.TestCase):
    def test_extracts_from_structured_content(self):
        content = (
            "【事件核心】：测试事件\\n"
            "【数据支撑】：增长10%\\n"
            "【商业洞察】：短剧买量成本上行，需关注ROI。\\n"
            "【决策价值】：建议优化素材。"
        )
        insight = extract_insight_from_content(content)
        self.assertIn("买量成本", insight)


class TestRankingHallucinationCount(unittest.TestCase):
    def test_counts_hits(self):
        rankings = [
            {"title": "剧A", "female_lead": "李十三", "male_lead": "", "production_house": "九州"},
            {"title": "剧B", "female_lead": "徐艺真", "male_lead": "", "production_house": "蓝海影视工作室"},
        ]
        stats = count_ranking_hallucinations(rankings)
        self.assertEqual(stats["actor_hits"], 1)
        self.assertEqual(stats["studio_hits"], 1)

    def test_compute_confidence_with_series_id(self):
        from utils.data_quality import compute_ranking_confidence
        score = compute_ranking_confidence({
            "data_source": "duanjugongcheng",
            "series_id": "abc",
            "female_lead": "徐艺真",
            "production_house": "九州",
            "episodes_count": 92,
        })
        self.assertGreaterEqual(score, 0.9)


if __name__ == "__main__":
    unittest.main()
