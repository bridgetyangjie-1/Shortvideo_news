import unittest

from graphs.ranking_quality import RankingCountError, ensure_top_rankings


def _ranking(rank: int, title: str, views_num: int) -> dict:
    return {
        "rank": rank,
        "title": title,
        "views": f"{views_num}万",
        "views_num": views_num,
        "platform": "红果",
    }


class RankingQualityTest(unittest.TestCase):
    def test_uses_generic_placeholders_to_reach_top8(self) -> None:
        rankings, warning = ensure_top_rankings(
            [_ranking(1, "今日冠军", 12000), _ranking(2, "今日亚军", 11000)],
            data_date="2026-06-11",
        )

        self.assertEqual(len(rankings), 8)
        self.assertEqual([item["rank"] for item in rankings], list(range(1, 9)))
        self.assertIn("补齐到 8 条", warning)
        self.assertIn("通用占位条目", warning)
        self.assertEqual(rankings[0]["title"], "今日冠军")
        self.assertEqual(rankings[2]["title"], "今日暂无数据 (API受限)")
        self.assertEqual(rankings[2]["play_count"], 0)
        self.assertEqual(rankings[2]["platform"], "未知")

    def test_raises_when_target_count_is_invalid(self) -> None:
        with self.assertRaises(RankingCountError):
            ensure_top_rankings(
                [_ranking(1, "今日冠军", 12000)],
                data_date="2026-06-11",
                target_count=0,
            )


if __name__ == "__main__":
    unittest.main()
