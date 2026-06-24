"""
飞书推送工具单元测试
"""
import json
import unittest

from tools.feishu_pusher import (
    determine_report_type,
    build_daily_card,
    build_weekly_card,
    build_monthly_card,
    _escape_md,
    _truncate,
)


class FeishuPusherTest(unittest.TestCase):
    def test_determine_report_type(self) -> None:
        self.assertEqual(determine_report_type("2025-06-01"), "monthly")  # 每月1日
        self.assertEqual(determine_report_type("2025-06-03"), "daily")    # 周二
        self.assertEqual(determine_report_type("2025-06-09"), "weekly")   # 周一

    def test_escape_md_escapes_special_chars(self) -> None:
        self.assertEqual(_escape_md("*bold*"), "\\*bold\\*")
        self.assertEqual(_escape_md("[link]"), "\\[link\\]")

    def test_truncate_long_text(self) -> None:
        self.assertEqual(len(_truncate("a" * 200, 10)), 10)
        self.assertTrue(_truncate("a" * 200, 10).endswith("…"))

    def _build_sample_data(self, data_date: str = "2025-06-09") -> dict:
        return {
            "data_date": data_date,
            "generated_at": f"{data_date}T09:00:00",
            "quality_score": 85,
            "industry": {
                "user_scale": "7亿",
                "market_size": "1000亿",
                "drama_count": "25万+",
                "app_mau": "3亿",
                "ai_ratio": 20,
                "female_ratio": 70,
                "male_ratio": 30,
            },
            "rankings": [
                {"rank": 1, "title": "剧A", "views": "1亿", "trend_type": "same", "genre": "甜宠"},
                {"rank": 2, "title": "剧B", "views": "9000万", "trend_type": "up", "rank_change": 3, "genre": "复仇"},
            ],
            "actors": {
                "female": [{"name": "演员A"}, {"name": "演员B"}],
                "male": [{"name": "演员C"}],
            },
            "daily_news": [
                {"type": "数据", "icon": "📊", "title": "新闻1", "content": "内容1", "source_url": "https://example.com/1"},
            ],
            "insights": [
                {"icon": "💡", "title": "洞察1", "content": "洞察内容1"},
            ],
            "genre_distribution": {
                "trending": [{"name": "逆袭", "change": 5, "trend": "up"}],
                "hot_tags": [{"name": "甜宠", "value": 10}],
            },
            "emotional_analysis": {
                "summary": "今日情绪摘要",
                "dominant_emotion": "身份逆袭",
                "top_trigger": "复仇打脸",
                "actionable_insights": [
                    {"icon": "💡", "title": "建议1", "content": "建议内容1"},
                ],
            },
            "play_trend": {
                "weekly": [
                    {"start_date": "2025-06-02", "total_views": 1000},
                    {"start_date": "2025-06-09", "total_views": 1200},
                ],
            },
            "platform": {
                "apps": [{"name": "红果", "mau": 3.0, "mau_unit": "亿", "yoy": "+10%"}],
            },
            "audience_profile": {
                "gender": {"female": 70, "male": 30},
                "age": {"18-24": 20, "25-34": 40, "35-44": 30, "45+": 10},
                "traits": ["特征1", "特征2"],
            },
            "alerts": [],
            "alert_count": 0,
        }

    def _extract_card_text(self, card: dict) -> str:
        """从卡片中提取所有文本内容，用于断言"""
        texts = []

        def _walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("content", "title") and isinstance(v, str):
                        texts.append(v)
                    else:
                        _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(card)
        return "\n".join(texts)

    def test_daily_card_is_compact(self) -> None:
        data = self._build_sample_data("2025-06-03")  # 周二
        card = build_daily_card(data)
        text = self._extract_card_text(card)
        self.assertIn("榜单 TOP5", text)
        self.assertIn("今日黑马", text)
        self.assertIn("行业快讯", text)
        # 日报不应包含周更/月更内容：演员榜、洞察、题材标签、情绪、趋势、平台、画像
        self.assertNotIn("演员热力", text)
        self.assertNotIn("今日洞察", text)
        self.assertNotIn("题材 & 标签风向标", text)
        self.assertNotIn("情绪驾驶舱", text)
        self.assertNotIn("周榜热度趋势", text)
        self.assertNotIn("平台月活", text)
        self.assertNotIn("核心观众画像", text)

    def test_weekly_card_includes_weekly_sections(self) -> None:
        data = self._build_sample_data("2025-06-09")  # 周一
        card = build_weekly_card(data)
        text = self._extract_card_text(card)
        self.assertIn("榜单 TOP5", text)
        self.assertIn("演员热力", text)
        self.assertIn("题材 & 标签风向标", text)
        self.assertIn("周榜热度趋势", text)
        # 周报不应包含月报专属内容
        self.assertNotIn("核心观众画像", text)
        self.assertNotIn("平台月活", text)

    def test_monthly_card_includes_all_sections(self) -> None:
        data = self._build_sample_data("2025-06-01")  # 月1日
        card = build_monthly_card(data)
        text = self._extract_card_text(card)
        self.assertIn("榜单 TOP5", text)
        self.assertIn("演员热力", text)
        self.assertIn("题材 & 标签风向标", text)
        self.assertIn("周榜热度趋势", text)
        self.assertIn("核心观众画像", text)
        self.assertIn("平台月活", text)
        self.assertIn("用户规模", text)
        self.assertIn("市场规模", text)

    def test_card_json_serializable(self) -> None:
        data = self._build_sample_data("2025-06-09")
        card = build_weekly_card(data)
        # 确保卡片可以被 JSON 序列化
        json_str = json.dumps(card, ensure_ascii=False)
        self.assertTrue(len(json_str) > 0)


if __name__ == "__main__":
    unittest.main()
