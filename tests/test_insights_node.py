"""
insights_node 单元测试（聚焦周缓存逻辑，不调用真实 API）
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from graphs.nodes import insights_node as insights_module
from graphs.state import InsightsNodeInput, InsightsNodeOutput, Insight
from tools import weekly_cache


class InsightsNodeCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.original_cache_dir = weekly_cache.CACHE_DIR
        weekly_cache.CACHE_DIR = os.path.join(self.tmpdir, "weekly_cache")

        # 最小化构造输入
        self.state = InsightsNodeInput(
            data_date="2025-06-10",  # 周二
            enriched_rankings=[],
            industry={},
        )
        self.config = {"metadata": {"llm_cfg": "config/insights_llm_cfg.json"}}

    def tearDown(self) -> None:
        weekly_cache.CACHE_DIR = self.original_cache_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_runtime(self) -> mock.MagicMock:
        runtime = mock.MagicMock()
        runtime.context = mock.MagicMock()
        return runtime

    def test_non_monday_uses_cache_without_calling_api(self) -> None:
        """非周一且缓存命中时，不应调用 _generate_insights。"""
        # 预先写入缓存
        weekly_cache.save_cache(
            "insights",
            {"insights": [{"title": "缓存洞察", "content": "内容", "icon": "💡", "source": "", "update_frequency": "weekly"}]},
            "2025-06-10",
        )

        with mock.patch.object(insights_module, "_generate_insights") as mock_gen:
            output = insights_module.insights_node(self.state, self.config, self._make_runtime())

        mock_gen.assert_not_called()
        self.assertEqual(output.error_message, "")
        self.assertEqual(len(output.insights), 1)
        self.assertEqual(output.insights[0].title, "缓存洞察")
        self.assertEqual(output.insights[0].update_frequency, "weekly")

    def test_monday_always_regenerates(self) -> None:
        """周一即使缓存命中，也应重新生成。"""
        self.state.data_date = "2025-06-09"  # 周一
        weekly_cache.save_cache(
            "insights",
            {"insights": [{"title": "旧洞察", "content": "旧内容", "icon": "💡", "source": ""}]},
            "2025-06-09",
        )

        fake_insights = [
            Insight(title="新洞察", content="新内容", icon="🔥", source="", update_frequency="weekly")
        ]
        with mock.patch.object(
            insights_module, "_generate_insights", return_value=(fake_insights, "")
        ) as mock_gen:
            output = insights_module.insights_node(self.state, self.config, self._make_runtime())

        mock_gen.assert_called_once()
        self.assertEqual(output.error_message, "")
        self.assertEqual(output.insights[0].title, "新洞察")

    def test_non_monday_cache_miss_generates_and_saves(self) -> None:
        """非周一缓存缺失时，重新生成并写入缓存。"""
        fake_insights = [
            Insight(title="生成洞察", content="内容", icon="📊", source="", update_frequency="weekly")
        ]
        with mock.patch.object(
            insights_module, "_generate_insights", return_value=(fake_insights, "")
        ) as mock_gen:
            output = insights_module.insights_node(self.state, self.config, self._make_runtime())

        mock_gen.assert_called_once()
        self.assertEqual(output.error_message, "")

        # 缓存应被写入
        cached = weekly_cache.load_cache("insights", "2025-06-10")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["insights"][0]["title"], "生成洞察")


if __name__ == "__main__":
    unittest.main()
