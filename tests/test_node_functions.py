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
        self.assertNotIn("未知", filled[0]["female_lead"])
        self.assertNotIn("unknown", filled[0]["male_lead"].lower())
        self.assertEqual(filled[1]["female_lead"], "已知")
        self.assertTrue(filled[1]["male_lead"])

    def test_fill_unknown_actors_for_male(self) -> None:
        rankings = [
            {"title": "男频剧1", "category": "male", "female_lead": "待定", "male_lead": "未知"},
        ]
        filled = fill_unknown_actors(rankings)
        self.assertNotIn("待定", filled[0]["female_lead"])
        self.assertNotIn("未知", filled[0]["male_lead"])


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


class GenreDistributionNodeTest(unittest.TestCase):
    def test_normalize_label_strips_noise(self) -> None:
        self.assertEqual(_normalize_label(" 总裁 "), "总裁")
        self.assertEqual(_normalize_label("（总裁）"), "总裁")
        self.assertEqual(_normalize_label(""), "")

    def test_classify_tag(self) -> None:
        self.assertEqual(_classify_tag("都市甜宠"), "题材")
        self.assertEqual(_classify_tag("霸道总裁"), "人设")
        self.assertEqual(_classify_tag("打脸"), "爽点")
        self.assertEqual(_classify_tag("复仇打脸"), "题材")  # "复仇" 在题材分类中优先命中
        self.assertEqual(_classify_tag("先婚后爱"), "情感关系")  # 关系动态归入情感关系
        self.assertEqual(_classify_tag("闪婚"), "情感关系")
        self.assertEqual(_classify_tag("日久生情"), "情感关系")
        self.assertEqual(_classify_tag("八零"), "时代背景")
        self.assertEqual(_classify_tag("未知标签"), "其他")

    def test_collect_drama_labels(self) -> None:
        drama = {"genre": "甜宠", "tags": ["总裁", "逆袭"], "core_trope": "打脸,撒糖"}
        labels = _collect_drama_labels(drama)
        self.assertIn("甜宠", labels)
        self.assertIn("总裁", labels)
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
