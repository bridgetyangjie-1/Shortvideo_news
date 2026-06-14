import unittest
from graphs.state import (
    DramaRanking,
    ActorRanking,
    ActorsData,
    DailyNews,
    IndustryData,
    PlatformData,
    AlertNodeInput,
    AlertItem,
)
from graphs.nodes.alert_node import alert_node


def _make_ranking(title: str, rank: int = 1, confidence: float = 0.85, rank_change: int = 0) -> DramaRanking:
    return DramaRanking(
        rank=rank,
        title=title,
        views="1000万",
        views_num=1000,
        platform="红果",
        genre="都市甜宠",
        confidence_score=confidence,
        rank_change=rank_change,
    )


def _make_actor(name: str, rank: int = 1) -> ActorRanking:
    return ActorRanking(rank=rank, name=name, popularity=100)


class AlertNodeTest(unittest.TestCase):
    def test_generates_quality_alert_when_score_low(self):
        state = AlertNodeInput(
            quality_score=55,
            quality_report={"checks": [{"name": "rankings_count", "passed": False}]},
        )
        result = alert_node(state, None, None)
        self.assertGreater(result.alert_count, 0)
        self.assertTrue(any(a.metric == "quality_score" for a in result.alerts))

    def test_generates_ranking_alert_when_count_low(self):
        state = AlertNodeInput(
            enriched_rankings=[_make_ranking(f"剧{i}", i) for i in range(1, 5)],
        )
        result = alert_node(state, None, None)
        self.assertTrue(any(a.category == "ranking" and a.metric == "rankings_count" for a in result.alerts))

    def test_generates_actor_alert_when_list_short(self):
        state = AlertNodeInput(
            enriched_rankings=[_make_ranking(f"剧{i}", i) for i in range(1, 21)],
            actors=ActorsData(female=[_make_actor("演员1")], male=[]),
        )
        result = alert_node(state, None, None)
        self.assertTrue(any(a.category == "actor" and "男频" in a.title for a in result.alerts))

    def test_generates_api_alert_when_error_message_matches(self):
        state = AlertNodeInput(
            error_message="DeepSeek API rate limit 429",
        )
        result = alert_node(state, None, None)
        self.assertTrue(any(a.category == "api" and a.severity == "critical" for a in result.alerts))

    def test_deduplicates_same_alert(self):
        state = AlertNodeInput(
            quality_score=55,
            quality_report={"checks": [{"name": "rankings_count", "passed": False}]},
            enriched_rankings=[_make_ranking("剧1", 1)],
        )
        result = alert_node(state, None, None)
        titles = [a.title for a in result.alerts]
        self.assertEqual(len(titles), len(set(titles)))


if __name__ == "__main__":
    unittest.main()
