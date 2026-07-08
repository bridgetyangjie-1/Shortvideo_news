"""剧名模糊匹配单元测试"""
import unittest

from utils.title_matcher import (
    find_best_title_match,
    normalize_title_for_match,
    title_match_score,
    lookup_hongguo_metadata,
    build_title_metadata_indexes,
)


class TestTitleMatcher(unittest.TestCase):
    def test_normalize_strips_punctuation_and_suffix(self):
        self.assertEqual(normalize_title_for_match("《我靠听物成团宠》"), "我靠听物成团宠")
        self.assertEqual(normalize_title_for_match("少夫人来自东北2"), "少夫人来自东北")

    def test_score_substring_match(self):
        score = title_match_score("我靠听物成团宠", "我靠听物 成团宠!")
        self.assertGreaterEqual(score, 0.88)

    def test_find_best_match(self):
        candidates = [
            ("我靠听物成团宠", {"series_id": "abc123"}),
            ("完全不同的剧", {"series_id": "zzz"}),
        ]
        result = find_best_title_match("我靠听物成团宠!", candidates)
        self.assertEqual(result["series_id"], "abc123")

    def test_lookup_hongguo_metadata_fuzzy(self):
        items = [{"title": "上司！上瘾！商总一眼心动了", "series_id": "sid-1"}]
        exact, norm, fuzzy = build_title_metadata_indexes(items)
        meta = lookup_hongguo_metadata("上司上瘾商总一眼心动了", exact, norm, fuzzy)
        self.assertEqual(meta["series_id"], "sid-1")


if __name__ == "__main__":
    unittest.main()
