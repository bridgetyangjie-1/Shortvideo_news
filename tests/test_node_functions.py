import json
import unittest
from collections import Counter
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

from graphs.nodes.search_node import _merge_hongguo_dataeye
from graphs.nodes.enrich.fallback import fill_unknown_actors
from graphs.nodes.audience_profile_node import (
    _collect_tags,
    _infer_profile,
    _dominant_gender,
    _build_traits,
    _validate_profile,
    _parse_profile,
    _adjust_profile_by_rankings,
    _compute_weekly_signals,
    _compute_weekly_trends,
    _generate_analyst_insights,
    _safe_percent_dict,
    _safe_named_list,
    _safe_segments,
    _safe_spending,
)
from graphs.nodes.genre_distribution_node import (
    _classify_tag,
    _collect_drama_labels,
    _load_history_rankings,
    _normalize_label,
)
from graphs.state import DramaRanking


class SearchNodeMergeTest(unittest.TestCase):
    def test_merge_without_dataeye_sets_hongguo_source(self) -> None:
        hongguo = [
            {"title": " 剧A ", "heat": 100},
            {"title": "剧B", "heat": 90},
        ]
        merged = _merge_hongguo_dataeye(hongguo, [])
        self.assertEqual(len(merged), 2)
        # 红果网页端为推荐列表，不是真实热榜，因此置信度降低并明确标注来源
        self.assertEqual(merged[0]["data_source"], "hongguo_recommend")
        self.assertEqual(merged[0]["confidence_score"], 0.5)
        self.assertFalse(merged[0]["cross_validated"])

    def test_merge_cross_validated_increases_confidence(self) -> None:
        hongguo = [{"title": "剧A", "heat": 100}]
        dataeye = [{"title": "剧A", "rank": 1, "heat": 120}]
        merged = _merge_hongguo_dataeye(hongguo, dataeye)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["data_source"], "hongguo+dataeye")
        # 红果推荐页本身质量较低，即使交叉验证也不应给予过高置信度
        self.assertEqual(merged[0]["confidence_score"], 0.6)
        self.assertTrue(merged[0]["cross_validated"])
        self.assertEqual(merged[0]["heat"], 120)

    def test_merge_fuzzy_match_by_substring(self) -> None:
        hongguo = [{"title": "霸道总裁的小娇妻", "heat": 100}]
        dataeye = [{"title": "霸道总裁的小娇妻完整版", "rank": 2, "heat": 80}]
        merged = _merge_hongguo_dataeye(hongguo, dataeye)
        self.assertTrue(merged[0]["cross_validated"])


class EnrichNodeFallbackTest(unittest.TestCase):
    def test_fill_unknown_actors_for_female(self) -> None:
        rankings = [
            {"title": "女频剧1", "category": "female", "female_lead": "未知", "male_lead": ""},
            {"title": "女频剧2", "category": "female", "female_lead": "已知", "male_lead": "unknown"},
        ]
        filled = fill_unknown_actors(rankings)
        self.assertEqual(filled[0]["female_lead"], "")
        self.assertEqual(filled[0]["male_lead"], "")
        self.assertEqual(filled[1]["female_lead"], "已知")
        self.assertEqual(filled[1]["male_lead"], "")

    def test_fill_unknown_actors_for_male(self) -> None:
        rankings = [
            {"title": "男频剧1", "category": "male", "female_lead": "待定", "male_lead": "未知"},
        ]
        filled = fill_unknown_actors(rankings)
        self.assertEqual(filled[0]["female_lead"], "")
        self.assertEqual(filled[0]["male_lead"], "")


class AudienceProfileNodeTest(unittest.TestCase):
    def test_infer_profile_for_sweet_petty_female(self) -> None:
        rankings = [
            DramaRanking(rank=1, title="甜宠剧", genre="甜宠", tags=["高糖甜宠", "总裁"]),
            DramaRanking(rank=2, title="霸总剧", genre="霸总", tags=["逆袭", "豪门"]),
        ]
        profile = _infer_profile(rankings)
        self.assertGreater(profile["gender"]["female"], profile["gender"]["male"])
        self.assertEqual(sum(profile["gender"].values()), 100)
        self.assertEqual(sum(profile["age"].values()), 100)

    def test_infer_profile_returns_default_when_no_tags(self) -> None:
        rankings = []
        profile = _infer_profile(rankings)
        self.assertEqual(sum(profile["gender"].values()), 100)
        self.assertEqual(sum(profile["age"].values()), 100)

    def test_dominant_gender(self) -> None:
        self.assertEqual(_dominant_gender({"female": 70, "male": 30}), "female")
        self.assertEqual(_dominant_gender({"female": 30, "male": 70}), "male")
        self.assertEqual(_dominant_gender({"female": 50, "male": 50}), "neutral")

    def test_build_traits_for_female_drama(self) -> None:
        rankings = [DramaRanking(rank=1, title="甜宠", genre="甜宠", tags=["甜宠", "霸总"])]
        traits = _build_traits("female", rankings)
        self.assertEqual(len(traits), 4)
        self.assertTrue(any("甜" in t or "撒糖" in t for t in traits))

    def test_collect_tags_merges_fields(self) -> None:
        drama = DramaRanking(
            rank=1,
            title="剧",
            genre="甜宠",
            tags=["总裁", "逆袭"],
            core_trope=["打脸"],
        )
        tags = _collect_tags(drama.model_dump())
        self.assertIn("甜宠", tags)
        self.assertIn("总裁", tags)
        self.assertIn("逆袭", tags)
        self.assertIn("打脸", tags)

    def test_validate_profile_accepts_reasonable_data(self) -> None:
        profile = {
            "gender": {"female": 70, "male": 30},
            "age": {"18-24": 20, "25-34": 42, "35-44": 28, "45+": 10},
        }
        self.assertTrue(_validate_profile(profile))

    def test_validate_profile_rejects_unbalanced_gender(self) -> None:
        profile = {
            "gender": {"female": 80, "male": 30},
            "age": {"18-24": 20, "25-34": 42, "35-44": 28, "45+": 10},
        }
        self.assertFalse(_validate_profile(profile))

    def test_parse_profile_normalizes_percentages(self) -> None:
        raw = {
            "source_title": "测试报告",
            "gender": {"female": 68, "male": 32},
            "age": {"18-24": 18, "25-34": 40, "35-44": 30, "45+": 12},
            "regions": [{"name": "广东", "value": 50}, {"name": "江苏", "value": 50}],
            "traits": ["特征一", "特征二", "特征三", "特征四"],
            "content_preferences": [{"name": "都市爱情", "value": 60}, {"name": "甜宠", "value": 40}],
            "viewing_time": [{"name": "睡前", "value": 100}],
            "spending_power": {"paid_ratio": 40, "arpu": "¥20", "willingness": "高"},
            "user_segments": [{"name": "核心用户", "share": 50, "desc": "描述"}],
        }
        parsed = _parse_profile(raw)
        self.assertEqual(sum(parsed["gender"].values()), 100)
        self.assertEqual(sum(parsed["age"].values()), 100)
        self.assertEqual(parsed["spending_power"]["arpu"], "¥20")
        self.assertEqual(len(parsed["traits"]), 4)

    def test_adjust_profile_increases_male_when_male_dramas_rise(self) -> None:
        base = {
            "gender": {"female": 70, "male": 30},
            "age": {"18-24": 20, "25-34": 40, "35-44": 30, "45+": 10},
            "regions": [{"name": "广东", "value": 15}],
        }
        rankings = [
            DramaRanking(rank=1, title="战神", category="male", genre="战神", tags=["战神"]),
            DramaRanking(rank=2, title="赘婿", category="male", genre="赘婿", tags=["赘婿"]),
            DramaRanking(rank=3, title="甜宠", category="female", genre="甜宠", tags=["甜宠"]),
        ]
        adjusted = _adjust_profile_by_rankings(base, rankings)
        self.assertGreater(adjusted["gender"]["male"], 30)
        self.assertEqual(sum(adjusted["gender"].values()), 100)

    def test_safe_named_list_filters_invalid_items(self) -> None:
        raw = [
            {"name": "有效", "value": 60},
            {"name": "", "value": 40},
            {"value": 20},
            "invalid",
        ]
        result = _safe_named_list(raw, top_n=6)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "有效")
        self.assertEqual(result[0]["value"], 100)

    def test_safe_spending_parses_string_values(self) -> None:
        result = _safe_spending({"paid_ratio": "45%", "arpu": "¥25", "willingness": "高"})
        self.assertEqual(result["paid_ratio"], 45)
        self.assertEqual(result["arpu"], "¥25")

    def test_compute_weekly_signals_from_rankings(self) -> None:
        rankings = [
            DramaRanking(rank=1, title="甜宠剧", category="female", genre="都市爱情", tags=["甜宠"]),
            DramaRanking(rank=2, title="霸总剧", category="female", genre="都市爱情", tags=["霸总"]),
            DramaRanking(rank=3, title="战神", category="male", genre="战神归来", tags=["战神"]),
        ]
        signals = _compute_weekly_signals(rankings)
        self.assertGreater(signals["female_ratio"], signals["male_ratio"])
        self.assertEqual(signals["female_ratio"] + signals["male_ratio"], 100)
        self.assertGreater(len(signals["top_genres"]), 0)
        self.assertEqual(signals["top_genres"][0]["name"], "都市爱情")

    def test_compute_weekly_trends_detects_female_shift(self) -> None:
        current = {"female_ratio": 75, "male_ratio": 25, "ai_ratio": 10, "new_drama_ratio": 15,
                   "top_genres": [{"name": "都市爱情", "share": 40}]}
        previous = {"date": "2026-07-06", "signals": {
            "female_ratio": 70, "male_ratio": 30, "ai_ratio": 8, "new_drama_ratio": 10,
            "top_genres": [{"name": "都市爱情", "share": 32}]
        }}
        trends = _compute_weekly_trends(current, previous)
        self.assertEqual(trends["female_ratio_delta"], 5)
        self.assertEqual(trends["female_ratio_trend"], "up")
        self.assertEqual(trends["compared_to"], "2026-07-06")

    def test_generate_analyst_insights_compares_baseline_and_signals(self) -> None:
        baseline = {"gender": {"female": 70, "male": 30}}
        signals = {"female_ratio": 90, "male_ratio": 10, "new_drama_ratio": 25, "ai_ratio": 5,
                   "top_genres": [{"name": "都市爱情", "share": 36}]}
        trends = {"female_ratio_delta": 5, "compared_to": "2026-07-06", "genre_shift": "都市爱情升温4pp"}
        insights = _generate_analyst_insights(baseline, signals, trends)
        self.assertGreaterEqual(len(insights), 2)
        self.assertTrue(any("女频" in i for i in insights))
        self.assertTrue(any("都市爱情" in i for i in insights))


class AudienceProfileCacheTest(unittest.TestCase):
    def test_load_cache_returns_none_when_expired(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            cache_file = Path(tmp_dir) / "audience_profile_cache.json"
            cache_file.write_text(
                json.dumps({
                    "data_month": "2025-01",
                    "profile": {"gender": {"female": 70, "male": 30}},
                }),
                encoding="utf-8",
            )
            import tools.audience_profile_cache as cache_module
            original_path = cache_module.CACHE_FILE
            cache_module.CACHE_FILE = str(cache_file)
            try:
                self.assertIsNone(cache_module.load_cache(today="2025-06-22"))
            finally:
                cache_module.CACHE_FILE = original_path

    def test_save_and_load_cache_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            cache_file = Path(tmp_dir) / "audience_profile_cache.json"
            import tools.audience_profile_cache as cache_module
            original_path = cache_module.CACHE_FILE
            cache_module.CACHE_FILE = str(cache_file)
            try:
                profile = {
                    "gender": {"female": 65, "male": 35},
                    "age": {"18-24": 20, "25-34": 40, "35-44": 30, "45+": 10},
                }
                cache_module.save_cache(profile, source_url="http://test", source_title="测试", today="2025-06-22")
                loaded = cache_module.load_cache(today="2025-06-22")
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded["data_month"], "2025-06")
                self.assertEqual(loaded["source_title"], "测试")
                self.assertEqual(loaded["profile"]["gender"]["female"], 65)
            finally:
                cache_module.CACHE_FILE = original_path


class GenreDistributionNodeTest(unittest.TestCase):
    def test_normalize_label_strips_noise(self) -> None:
        self.assertEqual(_normalize_label(" 总裁 "), "总裁")
        self.assertEqual(_normalize_label("（总裁）"), "总裁")
        self.assertEqual(_normalize_label(""), "")

    def test_classify_tag(self) -> None:
        self.assertEqual(_classify_tag("都市甜宠"), "题材")
        self.assertEqual(_classify_tag("霸道总裁"), "人设")
        self.assertEqual(_classify_tag("打脸"), "爽点")
        self.assertEqual(_classify_tag("复仇打脸"), "爽点")
        self.assertEqual(_classify_tag("先婚后爱"), "情感关系")  # 关系动态归入情感关系
        self.assertEqual(_classify_tag("闪婚"), "情感关系")
        self.assertEqual(_classify_tag("日久生情"), "情感关系")
        self.assertEqual(_classify_tag("八零"), "时代背景")
        self.assertEqual(_classify_tag("未知标签"), "其他")

    def test_collect_drama_labels(self) -> None:
        drama = {"genre": "甜宠", "tags": ["总裁", "逆袭"], "core_trope": "打脸,撒糖"}
        labels = _collect_drama_labels(drama)
        self.assertIn("甜宠", labels)
        self.assertIn("霸总", labels)
        self.assertIn("逆袭", labels)
        self.assertIn("打脸", labels)
        self.assertIn("撒糖", labels)

    def test_load_history_rankings(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            history_dir = root / "assets" / "data" / "history"
            history_dir.mkdir(parents=True)

            today = datetime(2026, 6, 13)
            yesterday = today - timedelta(days=1)
            history_file = history_dir / f"{yesterday.strftime('%Y-%m-%d')}.json"
            history_file.write_text(
                json.dumps({"rankings": [{"title": "历史剧", "views_num": 1000}]}),
                encoding="utf-8",
            )

            history = _load_history_rankings(today.strftime("%Y-%m-%d"), str(root), lookback_days=7)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0][0], yesterday.strftime("%Y-%m-%d"))
            self.assertEqual(history[0][1], 1)


if __name__ == "__main__":
    unittest.main()
