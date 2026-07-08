import json
import unittest
from typing import List

from graphs.nodes.enrich.fallback import fill_unknown_actors
from graphs.nodes.enrich.cache_adapter import DramaCache
from graphs.nodes.enrich.metadata_fetcher import HongguoDetailFetcher
from graphs.nodes.enrich.actor_resolver import ActorResolver
from graphs.nodes.enrich.json_refiner import JsonRefiner


class FallbackTest(unittest.TestCase):
    def test_fill_unknown_actors_preserves_known_names(self) -> None:
        rankings = [
            {"title": "A", "female_lead": "徐艺真", "male_lead": "曾辉", "category": "female"},
        ]
        result = fill_unknown_actors(rankings)
        self.assertEqual(result[0]["female_lead"], "徐艺真")
        self.assertEqual(result[0]["male_lead"], "曾辉")

    def test_fill_unknown_actors_replaces_unknown(self) -> None:
        rankings = [{"title": "A", "female_lead": "未知", "male_lead": "", "category": "female"}]
        result = fill_unknown_actors(rankings)
        self.assertEqual(result[0]["female_lead"], "")
        self.assertEqual(result[0]["male_lead"], "")


class CacheAdapterTest(unittest.TestCase):
    def test_format_context(self) -> None:
        cache = DramaCache()
        record = {
            "actors": {"female_lead": "女主", "male_lead": "男主"},
            "studio": "九州",
            "release_date": "2026-01-01",
        }
        context = cache.format_context("测试剧", record)
        self.assertIn("测试剧", context)
        self.assertIn("女主", context)
        self.assertIn("九州", context)
        self.assertIn("2026-01-01", context)


class MetadataFetcherTest(unittest.TestCase):
    def test_format_context(self) -> None:
        fetcher = HongguoDetailFetcher()
        detail = {"actors": ["女主", "男主"], "studio": "点众", "release_date": "2026-02-01"}
        context = fetcher.format_context("测试剧", detail)
        self.assertIn("测试剧", context)
        self.assertIn("女主", context)
        self.assertIn("点众", context)

    def test_parse_cast_from_html(self) -> None:
        from graphs.nodes.enrich.metadata_fetcher import parse_cast_from_html, assign_leads_from_cast

        html = (
            ">张子烨</div><div class=\"cast\">饰 林南</div>"
            "<div>张星禾</div><div class=\"cast\">饰 卢苗苗</div>"
        )
        pairs = parse_cast_from_html(html)
        self.assertEqual(len(pairs), 2)
        leads = assign_leads_from_cast(pairs)
        self.assertEqual(leads["male_lead"], "张子烨")
        self.assertEqual(leads["female_lead"], "张星禾")


class ActorResolverTest(unittest.TestCase):
    def test_resolve_with_cache_hit(self) -> None:
        class FakeCache:
            def get(self, series_id):
                return {"actors": {"female_lead": "女主", "male_lead": "男主"}, "studio": "九州"}

            def format_context(self, title, record):
                return f"cached:{title}"

        class FakeFetcher:
            def fetch(self, series_id):
                return None

        resolver = ActorResolver(cache=FakeCache(), fetcher=FakeFetcher(), searcher=None)
        rankings = [{"title": "剧A", "series_id": "123", "tags": []}]
        context, missing, stats = resolver.resolve(rankings)
        self.assertIn("cached:剧A", context)
        self.assertEqual(len(missing), 0)
        self.assertEqual(stats["cache_hits"], 1)

    def test_resolve_with_crawler(self) -> None:
        class FakeCache:
            def get(self, series_id):
                return None

            def save(self, **kwargs):
                pass

            def format_context(self, title, record):
                return ""

        class FakeFetcher:
            def fetch(self, series_id):
                return {"actors": ["女主", "男主"], "studio": "点众"}

            def format_context(self, title, detail):
                return f"crawled:{title}"

        resolver = ActorResolver(cache=FakeCache(), fetcher=FakeFetcher(), searcher=None)
        rankings = [{"title": "剧B", "series_id": "456", "tags": []}]
        context, missing, stats = resolver.resolve(rankings)
        self.assertIn("crawled:剧B", context)
        self.assertEqual(stats["crawler_hits"], 1)


class JsonRefinerTest(unittest.TestCase):
    def test_parse_response_extracts_rankings(self) -> None:
        refiner = JsonRefiner(client=None)  # type: ignore[arg-type]
        response = "```json\n{\"rankings\": [{\"rank\": 1, \"title\": \"剧A\"}]}\n```"
        result = refiner._parse_response(response)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "剧A")

    def test_parse_response_fallback_to_array(self) -> None:
        refiner = JsonRefiner(client=None)  # type: ignore[arg-type]
        response = "[{\"rank\": 1, \"title\": \"剧B\"}]"
        result = refiner._parse_response(response)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "剧B")

    def test_parse_response_returns_empty_on_invalid(self) -> None:
        refiner = JsonRefiner(client=None)  # type: ignore[arg-type]
        result = refiner._parse_response("not json")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
