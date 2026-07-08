"""
actor_ranking_node 单元测试：榜单提取与一线明星过滤
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from graphs.nodes import actor_ranking_node as actor_module
from graphs.state import ActorRankingNodeInput, DramaRanking
from tools import weekly_cache


class ActorRankingNodeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.original_cache_dir = weekly_cache.CACHE_DIR
        weekly_cache.CACHE_DIR = os.path.join(self.tmpdir, "weekly_cache")

    def tearDown(self) -> None:
        weekly_cache.CACHE_DIR = self.original_cache_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_runtime(self) -> mock.MagicMock:
        runtime = mock.MagicMock()
        runtime.context = mock.MagicMock()
        return runtime

    def _build_rankings(self, count: int = 3) -> list[DramaRanking]:
        rankings = []
        for i in range(count):
            rankings.append(
                DramaRanking(
                    rank=i + 1,
                    title=f"剧{i+1}",
                    female_lead=f"女演员{i+1}",
                    male_lead=f"男演员{i+1}",
                    views_num=1000,
                    trend_type="same",
                )
            )
        return rankings

    def test_extracts_actors_without_deepseek(self) -> None:
        """演员不足时仅返回榜单提取结果，不调用 DeepSeek。"""
        rankings = self._build_rankings(3)
        state = ActorRankingNodeInput(data_date="2025-06-09", enriched_rankings=rankings)
        result = actor_module.actor_ranking_node(state, {}, self._make_runtime())

        self.assertEqual(result.error_message, "")
        self.assertEqual(len(result.actors.female), 3)
        self.assertEqual(len(result.actors.male), 3)
        self.assertIn("榜单主演统计", result.actors.data_source)

    def test_filters_mainstream_celebrities(self) -> None:
        """一线明星与泛化假名不应进入演员榜。"""
        rankings = [
            DramaRanking(rank=1, title="剧1", female_lead="周迅", male_lead="孙红雷", views_num=2000),
            DramaRanking(rank=2, title="剧2", female_lead="徐艺真", male_lead="曾辉", views_num=1800),
            DramaRanking(rank=3, title="剧3", female_lead="张伟", male_lead="杨紫", views_num=1600),
        ]
        state = ActorRankingNodeInput(data_date="2025-06-10", enriched_rankings=rankings)
        result = actor_module.actor_ranking_node(state, {}, self._make_runtime())

        female_names = [a.name for a in result.actors.female]
        male_names = [a.name for a in result.actors.male]
        self.assertEqual(female_names, ["徐艺真"])
        self.assertEqual(male_names, ["曾辉"])
        self.assertNotIn("周迅", female_names)
        self.assertNotIn("孙红雷", male_names)
        self.assertNotIn("杨紫", male_names)


if __name__ == "__main__":
    unittest.main()
