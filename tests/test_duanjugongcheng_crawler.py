"""
Tests for duanjugongcheng_crawler pure functions and mocked network paths.
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tools.duanjugongcheng_crawler import (
    _parse_title,
    _parse_number,
    _parse_table,
    _has_ranking_data,
    _extract_latest_week_date,
    build_duanju_metadata_index,
    fetch_week_ranking,
    fetch_latest_full_ranking,
)


class ParseTitleTest(unittest.TestCase):
    def test_new_drama_with_date(self):
        raw = "少夫人来自东北2新上架 2026-06-06"
        result = _parse_title(raw)
        self.assertEqual(result["title"], "少夫人来自东北2")
        self.assertTrue(result["is_new"])
        self.assertEqual(result["release_date"], "2026-06-06")

    def test_existing_drama_with_date(self):
        raw = "顾先生，搭个伙上架 2026-06-08"
        result = _parse_title(raw)
        self.assertEqual(result["title"], "顾先生，搭个伙")
        self.assertFalse(result["is_new"])
        self.assertEqual(result["release_date"], "2026-06-08")

    def test_empty_title(self):
        result = _parse_title("")
        self.assertEqual(result["title"], "")
        self.assertFalse(result["is_new"])
        self.assertEqual(result["release_date"], "")

    def test_title_without_date(self):
        raw = "无名短剧"
        result = _parse_title(raw)
        self.assertEqual(result["title"], "无名短剧")
        self.assertFalse(result["is_new"])
        self.assertEqual(result["release_date"], "")


class ParseNumberTest(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(_parse_number("12345"), 12345)

    def test_number_with_comma(self):
        self.assertEqual(_parse_number("12,345"), 12345)

    def test_mixed_text(self):
        self.assertEqual(_parse_number("热度 12,345 万"), 12345)

    def test_empty(self):
        self.assertEqual(_parse_number(""), 0)
        self.assertEqual(_parse_number(None), 0)


class ParseTableTest(unittest.TestCase):
    def test_parses_valid_table(self):
        html = """
        <table>
            <tr><th>排名</th><th>封面</th><th>剧名</th><th>题材</th><th>本周指数</th><th>累计指数</th></tr>
            <tr><td>1</td><td><img src="a.jpg"/></td><td>剧A新上架 2026-06-01</td><td>都市</td><td>16,000</td><td>99,999</td></tr>
            <tr><td>2</td><td><img src="b.jpg"/></td><td>剧B上架 2026-05-20</td><td>古装</td><td>15,000</td><td>88,888</td></tr>
        </table>
        """
        rankings = _parse_table(html, "2026-06-01")
        self.assertEqual(len(rankings), 2)

        first = rankings[0]
        self.assertEqual(first["rank"], 1)
        self.assertEqual(first["title"], "剧A")
        self.assertEqual(first["genre"], "都市")
        self.assertEqual(first["weekly_index"], 16000)
        self.assertEqual(first["total_index"], 99999)
        self.assertEqual(first["release_date"], "2026-06-01")
        self.assertTrue(first["is_new"])
        self.assertEqual(first["week_date"], "2026-06-01")
        self.assertEqual(first["platform"], "红果")

        second = rankings[1]
        self.assertEqual(second["title"], "剧B")
        self.assertFalse(second["is_new"])

    def test_skips_header_and_empty_rows(self):
        html = """
        <table>
            <tr><th>排名</th><th>封面</th><th>剧名</th><th>题材</th><th>指数</th><th>累计</th></tr>
            <tr><td></td><td></td><td></td><td></td><td></td><td></td></tr>
            <tr><td>1</td><td><img src="c.jpg"/></td><td>唯一剧新上架 2026-06-01</td><td>悬疑</td><td>10,000</td><td>50,000</td></tr>
        </table>
        """
        rankings = _parse_table(html, "2026-06-01")
        self.assertEqual(len(rankings), 1)
        self.assertEqual(rankings[0]["title"], "唯一剧")

    def test_no_table_returns_empty(self):
        self.assertEqual(_parse_table("<div>no data</div>", "2026-06-01"), [])


class HasRankingDataTest(unittest.TestCase):
    def test_valid_page(self):
        self.assertTrue(_has_ranking_data("<table><tr><td>1</td></tr></table>"))

    def test_no_table(self):
        self.assertFalse(_has_ranking_data("<div>loading</div>"))

    def test_error_message(self):
        self.assertFalse(_has_ranking_data("<table>榜单数据暂时无法加载</table>"))


class ExtractLatestWeekDateTest(unittest.TestCase):
    def test_extracts_latest_date(self):
        html = '''
        <a href="/cn/bangdan/2026-06-15">上周</a>
        <a href="/cn/bangdan/2026-06-08">上上周</a>
        <a href="/cn/bangdan/2026-06-01">更早</a>
        '''
        self.assertEqual(_extract_latest_week_date(html), "2026-06-15")

    def test_no_links_returns_none(self):
        self.assertIsNone(_extract_latest_week_date("<div>no links</div>"))


class BuildMetadataIndexTest(unittest.TestCase):
    def test_builds_index(self):
        data = [
            {"title": "剧A", "genre": "都市"},
            {"title": "  剧B  ", "genre": "古装"},
        ]
        index = build_duanju_metadata_index(data)
        self.assertIn("剧A", index)
        self.assertIn("剧B", index)
        self.assertIn("剧B", index)  # stripped spaces
        self.assertEqual(index["剧A"]["genre"], "都市")


class FetchWeekRankingTest(unittest.TestCase):
    @patch("tools.duanjugongcheng_crawler._fetch_html")
    def test_fetch_week_ranking_returns_parsed_data(self, mock_fetch):
        mock_fetch.return_value = """
        <table>
            <tr><th>排名</th><th>封面</th><th>剧名</th><th>题材</th><th>本周指数</th><th>累计指数</th></tr>
            <tr><td>1</td><td><img src="top.jpg"/></td><td>登顶剧新上架 2026-06-15</td><td>甜宠</td><td>20,000</td><td>100,000</td></tr>
        </table>
        """
        rankings = fetch_week_ranking("2026-06-15")
        self.assertEqual(len(rankings), 1)
        self.assertEqual(rankings[0]["title"], "登顶剧")
        mock_fetch.assert_called_once_with("https://www.duanjugongcheng.com/cn/bangdan/2026-06-15")

    @patch("tools.duanjugongcheng_crawler._fetch_html")
    def test_fetch_week_ranking_no_data_returns_empty(self, mock_fetch):
        mock_fetch.return_value = "榜单数据暂时无法加载"
        self.assertEqual(fetch_week_ranking("2026-06-15"), [])


class FetchLatestFullRankingTest(unittest.TestCase):
    @patch("tools.duanjugongcheng_crawler.find_latest_available_week")
    @patch("tools.duanjugongcheng_crawler.fetch_week_ranking")
    def test_returns_full_ranking(self, mock_fetch_week, mock_find_week):
        mock_find_week.return_value = "2026-06-15"
        mock_fetch_week.return_value = [{"rank": 1, "title": "剧A"}]

        result = fetch_latest_full_ranking()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "剧A")

    @patch("tools.duanjugongcheng_crawler.find_latest_available_week")
    @patch("tools.duanjugongcheng_crawler.fetch_homepage_top10")
    def test_falls_back_to_homepage(self, mock_homepage, mock_find_week):
        mock_find_week.return_value = None
        mock_homepage.return_value = [{"rank": 1, "title": "首页剧"}]

        result = fetch_latest_full_ranking()
        self.assertEqual(result[0]["title"], "首页剧")


if __name__ == "__main__":
    unittest.main()
