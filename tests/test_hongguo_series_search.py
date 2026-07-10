"""短剧工程 slug / 红果 series_id 搜索 / 演员上下文过滤测试"""
import unittest

from tools.duanjugongcheng_crawler import _parse_table, fetch_drama_detail
from tools.hongguo_series_search import (
    extract_series_id_from_text,
    extract_series_id_map_from_text,
    parse_actors_from_batch_text,
    resolve_series_id_from_catalog,
)
from utils.data_quality import filter_actors_by_search_context, is_platform_name, sanitize_actor_field


class TestDuanjuSlugParsing(unittest.TestCase):
    def test_parse_table_extracts_slug(self) -> None:
        html = """
        <table>
        <tr><th>排名</th><th></th><th>剧名</th></tr>
        <tr>
          <td>1</td><td></td>
          <td><a href="/cn/bangdan/ju/wo-kao-ting-wu-cheng-tuan-chong">我靠听物成团宠上架 2026-06-27</a></td>
          <td>奇幻脑洞</td><td>13662</td><td>15990</td>
        </tr>
        </table>
        """
        rows = _parse_table(html, "2026-07-06")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], "wo-kao-ting-wu-cheng-tuan-chong")
        self.assertEqual(rows[0]["title"], "我靠听物成团宠")


class TestHongguoSeriesSearch(unittest.TestCase):
    def test_extract_series_id_from_url(self) -> None:
        text = "详情 https://novelquickapp.com/detail?series_id=7594450347217669145 演员"
        self.assertEqual(extract_series_id_from_text(text), "7594450347217669145")

    def test_catalog_exact_match(self) -> None:
        catalog = [{"title": "半熟烟火", "series_id": "1234567890123456789"}]
        self.assertEqual(
            resolve_series_id_from_catalog("半熟烟火", catalog),
            "1234567890123456789",
        )

    def test_batch_series_id_map(self) -> None:
        text = (
            "【朝思暮时】\n"
            "链接: https://novelquickapp.com/detail?series_id=7594450347217669145\n"
            "【我靠听物成团宠】\n"
            "详情 https://novelquickapp.com/detail?series_id=7433340051892735038"
        )
        mapping = extract_series_id_map_from_text(text, ["朝思暮时", "我靠听物成团宠"])
        self.assertEqual(mapping["朝思暮时"], "7594450347217669145")
        self.assertEqual(mapping["我靠听物成团宠"], "7433340051892735038")

    def test_batch_actor_parse(self) -> None:
        text = "【测试剧】\n女主: 徐艺真\n男主: 曾辉\n"
        actors = parse_actors_from_batch_text(text, ["测试剧"])
        self.assertEqual(actors["测试剧"]["female_lead"], "徐艺真")
        self.assertEqual(actors["测试剧"]["male_lead"], "曾辉")


class TestActorContextFilter(unittest.TestCase):
    def test_platform_name_blocked(self) -> None:
        self.assertTrue(is_platform_name("红果"))
        self.assertEqual(sanitize_actor_field("红果"), "")

    def test_missing_marker_clears_actors(self) -> None:
        ctx = "【剧目：《测试剧》演员信息缺失，禁止编造演员名】"
        f, m = filter_actors_by_search_context("测试剧", "红果", "李明", ctx)
        self.assertEqual(f, "")
        self.assertEqual(m, "")

    def test_actor_must_appear_in_context(self) -> None:
        ctx = "【剧目：《测试剧》红果详情页数据】\n女主: 徐艺真\n男主: 曾辉\n"
        f, m = filter_actors_by_search_context("测试剧", "徐艺真", "曾辉", ctx)
        self.assertEqual(f, "徐艺真")
        self.assertEqual(m, "曾辉")
        f2, m2 = filter_actors_by_search_context("测试剧", "周迅", "曾辉", ctx)
        self.assertEqual(f2, "")
        self.assertEqual(m2, "曾辉")


if __name__ == "__main__":
    unittest.main()
