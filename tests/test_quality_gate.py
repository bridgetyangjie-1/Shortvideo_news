import unittest
from graphs.state import (
    DramaRanking,
    ActorRanking,
    ActorsData,
    DailyNews,
    IndustryData,
    PlatformData,
    QualityGateInput,
)
from graphs.nodes.quality_gate_node import quality_gate_node


def _make_ranking(title: str, rank: int = 1) -> DramaRanking:
    return DramaRanking(
        rank=rank,
        title=title,
        views="1000万",
        views_num=1000,
        platform="红果",
        genre="都市甜宠",
        confidence_score=0.85,
    )


def _make_actor(name: str, rank: int = 1) -> ActorRanking:
    return ActorRanking(rank=rank, name=name, popularity=100)


def _make_news(title: str, url: str = "https://example.com/news") -> DailyNews:
    return DailyNews(
        title=title,
        content="content",
        insight="insight",
        source_url=url,
    )


def _run_gate(state: QualityGateInput):
    return quality_gate_node(state, None, None)


class QualityGateNodeTest(unittest.TestCase):
    def test_passes_with_complete_data(self) -> None:
        rankings = [_make_ranking(f"剧{i}", i) for i in range(1, 21)]
        actors = ActorsData(
            female=[_make_actor(f"女演员{i}", i) for i in range(1, 11)],
            male=[_make_actor(f"男演员{i}", i) for i in range(1, 11)],
        )
        news = [_make_news(f"新闻{i}") for i in range(1, 7)]
        industry = IndustryData(
            app_mau={"value": 1.5, "unit": "亿", "yoy": "+12%"},
            drama_count="1.2万部",
            ai_ratio=15,
        )

        state = QualityGateInput(
            enriched_rankings=rankings,
            actors=actors,
            daily_news=news,
            industry=industry,
            platform=PlatformData(),
        )
        result = _run_gate(state)

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.quality_score, 60)

    def test_fails_when_rankings_below_threshold(self) -> None:
        rankings = [_make_ranking(f"剧{i}", i) for i in range(1, 5)]
        actors = ActorsData(
            female=[_make_actor(f"女演员{i}", i) for i in range(1, 11)],
            male=[_make_actor(f"男演员{i}", i) for i in range(1, 11)],
        )
        news = [_make_news(f"新闻{i}") for i in range(1, 7)]

        state = QualityGateInput(
            enriched_rankings=rankings,
            actors=actors,
            daily_news=news,
            industry=IndustryData(),
        )
        result = _run_gate(state)

        self.assertFalse(result.success)
        self.assertLess(result.quality_score, 60)
        self.assertIn("榜单数量不足", result.error_message)

    def test_fails_when_actors_missing(self) -> None:
        rankings = [_make_ranking(f"剧{i}", i) for i in range(1, 21)]
        actors = ActorsData(
            female=[_make_actor("未知", i) for i in range(1, 11)],
            male=[],
        )
        news = [_make_news(f"新闻{i}") for i in range(1, 7)]

        state = QualityGateInput(
            enriched_rankings=rankings,
            actors=actors,
            daily_news=news,
            industry=IndustryData(),
        )
        result = _run_gate(state)

        self.assertFalse(result.success)
        self.assertIn("女频演员", result.error_message)
        self.assertIn("男频演员", result.error_message)

    def test_fails_when_daily_news_missing_url(self) -> None:
        rankings = [_make_ranking(f"剧{i}", i) for i in range(1, 21)]
        actors = ActorsData(
            female=[_make_actor(f"女演员{i}", i) for i in range(1, 11)],
            male=[_make_actor(f"男演员{i}", i) for i in range(1, 11)],
        )
        news = [_make_news(f"新闻{i}", url="") for i in range(1, 7)]

        state = QualityGateInput(
            enriched_rankings=rankings,
            actors=actors,
            daily_news=news,
            industry=IndustryData(),
        )
        result = _run_gate(state)

        self.assertFalse(result.success)
        self.assertIn("快讯", result.error_message)

    def test_fails_when_upstream_has_api_error(self) -> None:
        rankings = [_make_ranking(f"剧{i}", i) for i in range(1, 21)]
        actors = ActorsData(
            female=[_make_actor(f"女演员{i}", i) for i in range(1, 11)],
            male=[_make_actor(f"男演员{i}", i) for i in range(1, 11)],
        )
        news = [_make_news(f"新闻{i}") for i in range(1, 7)]

        state = QualityGateInput(
            enriched_rankings=rankings,
            actors=actors,
            daily_news=news,
            industry=IndustryData(),
            error_message="DeepSeek API key invalid: unauthorized",
        )
        result = _run_gate(state)

        self.assertFalse(result.success)
        self.assertIn("API", result.error_message)


class IndustryDataNormalizationTest(unittest.TestCase):
    def test_dict_metric_normalized_to_string(self) -> None:
        industry = IndustryData(app_mau={"value": 1.5, "unit": "亿", "yoy": "+12%"})
        self.assertEqual(industry.app_mau, "1.5亿（+12%）")

    def test_ratios_clamped_to_0_100(self) -> None:
        industry = IndustryData(ai_ratio=150, female_ratio=-10, male_ratio=50)
        self.assertEqual(industry.ai_ratio, 100)
        self.assertEqual(industry.female_ratio, 0)
        self.assertEqual(industry.male_ratio, 50)


if __name__ == "__main__":
    unittest.main()
