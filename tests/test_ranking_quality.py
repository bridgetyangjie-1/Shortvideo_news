import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

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
    def test_uses_recent_history_to_reach_top20(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            history_dir = root / "assets" / "data" / "history"
            history_dir.mkdir(parents=True)
            history_payload = {
                "rankings": [
                    _ranking(index, f"历史补位{index}", 9000 - index)
                    for index in range(1, 19)
                ]
            }
            (history_dir / "2026-06-10.json").write_text(
                json.dumps(history_payload, ensure_ascii=False),
                encoding="utf-8",
            )

            rankings, warning = ensure_top_rankings(
                [_ranking(1, "今日冠军", 12000), _ranking(2, "今日亚军", 11000)],
                data_date="2026-06-11",
                workspace_path=str(root),
            )

        self.assertEqual(len(rankings), 20)
        self.assertEqual([item["rank"] for item in rankings], list(range(1, 21)))
        self.assertIn("补齐到 20 条", warning)
        self.assertEqual(rankings[0]["title"], "今日冠军")

    def test_raises_when_sources_cannot_reach_top20(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            with self.assertRaises(RankingCountError):
                ensure_top_rankings(
                    [_ranking(1, "今日冠军", 12000)],
                    data_date="2026-06-11",
                    workspace_path=tmp_dir,
                )


if __name__ == "__main__":
    unittest.main()
