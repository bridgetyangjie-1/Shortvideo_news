"""
情绪分析节点单元测试
"""
import sys
import os
import unittest

# 确保能导入 src 下的模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graphs.nodes.emotion_analysis_node import (
    _aggregate_emotion_scores,
    _build_wordcloud,
    _build_emotion_rankings,
    _build_trends,
    _rank_weight,
)
from graphs.state import DramaRanking, EmotionalAnalysis, default_emotional_analysis


class TestEmotionAnalysis(unittest.TestCase):
    """测试情绪分析节点的规则映射与统计逻辑"""

    def test_rank_weight_decreases_with_rank(self):
        """排名越靠后权重越低"""
        self.assertEqual(_rank_weight(1), 20)
        self.assertEqual(_rank_weight(20), 1)
        self.assertEqual(_rank_weight(25), 1)

    def test_aggregate_emotion_scores_revenge_theme(self):
        """复仇题材应产生身份逆袭和复仇打脸高分"""
        dramas = [
            DramaRanking(rank=1, title="离婚后她带六宝惊艳全球", genre="都市", tags=["复仇", "打脸", "离婚"], core_trope=["复仇打脸"]),
            DramaRanking(rank=2, title="甜宠总裁每天撒糖", genre="甜宠", tags=["甜宠", "总裁"], core_trope=["甜宠撒糖"]),
        ]
        scores = _aggregate_emotion_scores(dramas)
        self.assertIn("身份逆袭", scores)
        self.assertIn("复仇打脸", scores)
        self.assertIn("甜宠撒糖", scores)
        self.assertIn("亲密关系失衡", scores)
        # 复仇剧 rank1 权重高，复仇打脸应高于甜宠撒糖
        self.assertGreater(scores["复仇打脸"], scores["甜宠撒糖"])

    def test_build_wordcloud_categories(self):
        """词云条目必须携带正确分类"""
        scores = {
            "复仇打脸": 80,
            "亲密关系失衡": 60,
            "身份逆袭": 50,
        }
        cloud = _build_wordcloud(scores)
        self.assertGreaterEqual(len(cloud), 3)
        categories = {item.category for item in cloud}
        self.assertIn("trigger", categories)
        self.assertIn("anxiety", categories)
        self.assertIn("emotion", categories)

    def test_build_emotion_rankings_binding(self):
        """TOP3 剧目应绑定情绪/焦虑/触发点"""
        dramas = [
            DramaRanking(rank=1, title="离婚后她带六宝惊艳全球", genre="都市", tags=["复仇", "打脸", "离婚"]),
            DramaRanking(rank=2, title="总裁甜宠妻", genre="甜宠", tags=["甜宠", "总裁"]),
            DramaRanking(rank=3, title="战神归来", genre="男频", tags=["战神", "逆袭"]),
        ]
        scores = _aggregate_emotion_scores(dramas)
        rankings = _build_emotion_rankings(dramas, scores)
        self.assertEqual(len(rankings), 3)
        for item in rankings:
            self.assertTrue(item.title)
            self.assertTrue(item.primary_emotion)
            self.assertTrue(item.anxiety)
            self.assertTrue(item.trigger)

    def test_build_trends_vs_yesterday(self):
        """环比趋势计算正确"""
        current = {"复仇打脸": 80, "甜宠撒糖": 50}
        yesterday = {"复仇打脸": 65, "甜宠撒糖": 70}
        trends = _build_trends(current, yesterday)
        names = {t.name: t for t in trends}
        self.assertEqual(names["复仇打脸"].trend, "up")
        self.assertEqual(names["复仇打脸"].change, 15)
        self.assertEqual(names["甜宠撒糖"].trend, "down")
        self.assertEqual(names["甜宠撒糖"].change, -20)

    def test_default_emotional_analysis_structure(self):
        """默认情绪分析结构符合新模型"""
        ea = default_emotional_analysis()
        self.assertIsInstance(ea, EmotionalAnalysis)
        self.assertTrue(ea.summary)
        self.assertTrue(ea.dominant_emotion)
        self.assertTrue(ea.wordcloud)
        self.assertTrue(ea.emotion_rankings)
        self.assertTrue(ea.actionable_insights)
        self.assertEqual(len(ea.actionable_insights), 3)


if __name__ == "__main__":
    unittest.main()
