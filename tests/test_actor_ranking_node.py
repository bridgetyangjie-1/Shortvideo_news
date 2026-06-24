"""
actor_ranking_node 单元测试（聚焦 DeepSeek 补充触发策略）
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from graphs.nodes import actor_ranking_node as actor_module
from graphs.state import ActorRankingNodeInput, DramaRanking
from tools import weekly_cache


class ActorRankingNodeTokenTest(unittest.TestCase):
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
        """构造少量榜单数据，使男女演员均不足10人。"""
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

    def _mock_config(self) -> dict:
        return {"metadata": {"llm_cfg": "config/actor_ranking_llm_cfg.json"}}

    def test_deepseek_supplement_only_on_monday(self) -> None:
        """周一演员不足时调用 DeepSeek，周二不调用。"""
        rankings = self._build_rankings(3)

        with mock.patch.object(actor_module.DeepSeekClient, "chat", return_value="{}") as mock_chat:
            # 周一：应调用 DeepSeek
            monday_state = ActorRankingNodeInput(
                data_date="2025-06-09", enriched_rankings=rankings
            )
            actor_module.actor_ranking_node(monday_state, self._mock_config(), self._make_runtime())
            self.assertGreaterEqual(mock_chat.call_count, 1)

            mock_chat.reset_mock()

            # 周二：不应调用 DeepSeek
            tuesday_state = ActorRankingNodeInput(
                data_date="2025-06-10", enriched_rankings=rankings
            )
            actor_module.actor_ranking_node(tuesday_state, self._mock_config(), self._make_runtime())
            mock_chat.assert_not_called()

    def test_no_supplement_when_actors_sufficient(self) -> None:
        """男女演员均满10人时，无论是否周一都不调用 DeepSeek。"""
        rankings = self._build_rankings(12)

        with mock.patch.object(actor_module.DeepSeekClient, "chat", return_value="{}") as mock_chat:
            monday_state = ActorRankingNodeInput(
                data_date="2025-06-09", enriched_rankings=rankings
            )
            actor_module.actor_ranking_node(monday_state, self._mock_config(), self._make_runtime())
            mock_chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
