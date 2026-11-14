"""连板选股口径：空结果、并列、一排边界、炸板排除。"""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from streakpicker.pick import PickError, pick  # noqa: E402
import cli  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "get_mixed.json"
SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def _names(result: dict) -> set[str]:
    found = {result["leaders"]["market"]["name"]}
    for bucket in (result["row1"], result["row2"], result["leaders"]["sectors"], result["leaders"]["intraday"]):
        for item in bucket:
            if item.get("name"):
                found.add(item["name"])
    return found


def _stock(**overrides: object) -> dict:
    base = {
        "market": "sh",
        "code": "600000",
        "name": "测试股份",
        "direction": "up",
        "closed_at_limit": True,
        "limit_rate_bp": 1000,
        "streak_height": 1,
        "limit_up_reasons": ["题材"],
        "first_limit_time": "10:00:00",
        "seal_ratio": 0.2,
        "seal_amount": 10_000_000,
        "close_price": 10,
        "stock_float_market_cap": 2_000_000_000,
    }
    base.update(overrides)
    return base


def _data(stocks: list[dict], *, review: dict | None = None, events: list | None = None) -> dict:
    return {
        "review": {} if review is None else review,
        "events": events if events is not None else [{"code": "placeholder"}],
        "ladder": {
            "groups": [{"streak_height": 1, "count": len(stocks), "stocks": stocks}] if stocks else [],
            "broken_limit_up": [],
            "opened_limit_down": [],
            "closed_limit_down": [],
        },
    }


class MixedFixtureTest(unittest.TestCase):
    def test_fixture_classifies_sectors_leaders_and_rows(self) -> None:
        result = pick(json.loads(FIXTURE.read_text(encoding="utf-8")))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            [item["theme"] for item in result["strong_sectors"]],
            ["机器人", "算力", "军工"],
        )
        robot = result["strong_sectors"][0]
        self.assertEqual(robot["limit_up_count"], 3)
        self.assertEqual(robot["max_streak"], 4)
        self.assertEqual(robot["earliest_limit_time"], "09:31:00")
        self.assertEqual(robot["seal_amount_sum"], 330_000_000)
        self.assertIn("3.30亿元", robot["basis"])
        self.assertNotIn("冷门", [item["theme"] for item in result["strong_sectors"]])

        self.assertEqual(result["leaders"]["market"]["code"], "600001")
        self.assertEqual(
            [item["code"] for item in result["leaders"]["sectors"]],
            ["600001", "600003", "600004"],
        )
        self.assertEqual(
            [item["code"] for item in result["leaders"]["intraday"]],
            ["600001", "600003", "600004"],
        )
        self.assertTrue(all(item["market"] and item["code"] for item in result["leaders"]["sectors"]))

        self.assertEqual([item["code"] for item in result["row1"]], ["600002", "600004", "600099", "000010"])
        self.assertEqual([item["code"] for item in result["row2"]], ["000001", "300001"])
        self.assertEqual(result["row2"][0]["unmet"], ["收盘价不低于30元"])
        self.assertEqual(result["row2"][1]["unmet"], ["涨停限幅不是10%"])
        self.assertEqual([item["code"] for item in result["unclassified_rows"]], ["600003"])
        self.assertEqual(result["unclassified_rows"][0]["missing_fields"], ["stock_float_market_cap"])
        self.assertIn("数据缺失：个股流通市值", result["unclassified_rows"][0]["basis"])
        self.assertIn("40.00%", result["leaders"]["market"]["basis"])

        names = _names(result)
        self.assertNotIn("炸板股份", names)
        self.assertNotIn("跌停股份", names)
        self.assertNotIn("600001", [item["code"] for item in result["row1"] + result["row2"]])


class EmptyResultTest(unittest.TestCase):
    def test_no_record_when_review_and_events_are_empty(self) -> None:
        result = pick({"review": None, "events": [], "ladder": {"groups": []}})
        self.assertEqual(result["status"], "no_record")
        self.assertEqual(result["message"], "库内无记录")

    def test_events_without_closed_limit_up_are_not_a_missing_record(self) -> None:
        result = pick(
            {
                "review": None,
                "events": [{"market": "sz", "code": "000002", "direction": "up"}],
                "ladder": {"groups": [], "broken_limit_up": [_stock(code="000002", name="炸板股份", closed_at_limit=False)]},
            }
        )
        self.assertEqual(result["status"], "no_closed_limit_up")
        self.assertEqual(result["message"], "库内无收盘涨停事件")

    def test_saved_review_without_limit_up_is_not_a_missing_record(self) -> None:
        result = pick({"review": {"turnover_amount_sh": 1}, "events": [], "ladder": {"groups": []}})
        self.assertEqual(result["status"], "no_closed_limit_up")

    def test_null_events_behaves_like_empty_events(self) -> None:
        result = pick({"review": None, "events": None, "ladder": {"groups": []}})
        self.assertEqual(result["status"], "no_record")


class TieBreakTest(unittest.TestCase):
    def test_equal_business_keys_use_market_then_code(self) -> None:
        result = pick(
            _data(
                [
                    _stock(market="sz", code="000002", name="后排", streak_height=5, first_limit_time="09:30:00", seal_ratio=0.5, seal_amount=100),
                    _stock(market="sh", code="600010", name="同键后码", streak_height=5, first_limit_time="09:30:00", seal_ratio=0.5, seal_amount=100),
                    _stock(market="sh", code="600001", name="同键前码", streak_height=5, first_limit_time="09:30:00", seal_ratio=0.5, seal_amount=100),
                ]
            )
        )
        leader = result["leaders"]["market"]
        self.assertEqual((leader["market"], leader["code"]), ("sh", "600001"))
        self.assertEqual(
            [(item["market"], item["code"]) for item in leader["tied"]],
            [("sh", "600010"), ("sz", "000002")],
        )

    def test_intraday_leader_uses_seal_ratio_when_time_ties(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", name="封成比低", first_limit_time="09:31:00", seal_ratio=0.1, seal_amount=9),
                    _stock(code="600002", name="封成比高", first_limit_time="09:31:00", seal_ratio=0.8, seal_amount=1),
                ]
            )
        )
        self.assertEqual(result["leaders"]["intraday"][0]["code"], "600002")

    def test_intraday_leader_stays_undetermined_when_every_time_is_missing(self) -> None:
        result = pick(_data([_stock(first_limit_time=None), _stock(code="600001", first_limit_time=None)]))
        intraday = result["leaders"]["intraday"][0]
        self.assertTrue(intraday["undetermined"])
        self.assertIsNone(intraday["code"])
        self.assertIsNone(intraday["streak_height"])
        self.assertEqual(intraday["tied"], [])
        self.assertEqual(intraday["basis"], "数据缺失，无法判定")
        self.assertEqual(result["leaders"]["market"]["code"], "600000")

    def test_fewer_than_three_themes_are_all_listed(self) -> None:
        result = pick(_data([_stock(limit_up_reasons=["只有一个"])]))
        self.assertEqual([item["theme"] for item in result["strong_sectors"]], ["只有一个"])

    def test_identical_sector_keys_break_by_unicode_code_point(self) -> None:
        stocks = [
            _stock(code=f"60000{index}", name=theme, limit_up_reasons=[theme], first_limit_time="09:30:00", seal_amount=100)
            for index, theme in enumerate("甲乙丙丁")
        ]
        result = pick(_data(stocks))
        self.assertEqual([item["theme"] for item in result["strong_sectors"]], ["丁", "丙", "乙"])

    def test_missing_sector_time_and_seal_rank_after_present_values(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", limit_up_reasons=["有时间"], first_limit_time="10:00:00", seal_amount=None),
                    _stock(code="600002", limit_up_reasons=["无时间"], first_limit_time=None, seal_amount=999),
                ]
            )
        )
        self.assertEqual([item["theme"] for item in result["strong_sectors"]], ["有时间", "无时间"])

        result = pick(
            _data(
                [
                    _stock(code="600001", limit_up_reasons=["有封单"], first_limit_time="10:00:00", seal_amount=1),
                    _stock(code="600002", limit_up_reasons=["无封单"], first_limit_time="10:00:00", seal_amount=None),
                ]
            )
        )
        self.assertEqual([item["theme"] for item in result["strong_sectors"]], ["有封单", "无封单"])

    def test_duplicate_reason_counts_once_and_two_reasons_count_in_both(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", limit_up_reasons=["机器人", "机器人"]),
                    _stock(code="600002", limit_up_reasons=["机器人", "算力"]),
                ]
            )
        )
        counts = {item["theme"]: item["limit_up_count"] for item in result["strong_sectors"]}
        self.assertEqual(counts, {"机器人": 2, "算力": 1})

    def test_sector_seal_sum_uses_present_values_only(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", limit_up_reasons=["部分缺"], first_limit_time="09:30:00", seal_amount=100_000_000),
                    _stock(code="600002", limit_up_reasons=["部分缺"], first_limit_time="10:00:00", seal_amount=None),
                    _stock(code="600003", limit_up_reasons=["全部有"], first_limit_time="09:30:00", seal_amount=90_000_000),
                    _stock(code="600004", limit_up_reasons=["全部有"], first_limit_time="10:00:00", seal_amount=90_000_000),
                ]
            )
        )
        sectors = {item["theme"]: item for item in result["strong_sectors"]}
        self.assertEqual(sectors["部分缺"]["seal_amount_sum"], 100_000_000)
        self.assertEqual(sectors["全部有"]["seal_amount_sum"], 180_000_000)

    def test_invalid_reasons_type_is_an_error(self) -> None:
        with self.assertRaises(PickError):
            pick(_data([_stock(limit_up_reasons=0)]))


class RowBoundaryTest(unittest.TestCase):
    def test_exact_price_and_cap_limits_go_to_row2(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", name="刚好30元", close_price=30),
                    _stock(code="600002", name="刚好100亿", close_price=29.99, stock_float_market_cap=10_000_000_000),
                    _stock(code="600003", name="刚好入选", close_price=29.99, stock_float_market_cap=9_999_999_999),
                ]
            )
        )
        self.assertEqual([item["code"] for item in result["row1"]], ["600003"])
        self.assertEqual(result["row2"][0]["unmet"], ["收盘价不低于30元"])
        self.assertEqual(result["row2"][1]["unmet"], ["个股流通市值不低于100亿"])

    def test_null_seal_ratio_sorts_after_a_present_value(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", name="有比值", streak_height=3, first_limit_time="09:30:00", seal_ratio=0.01, seal_amount=1),
                    _stock(code="600002", name="缺比值", streak_height=3, first_limit_time="09:30:00", seal_ratio=None, seal_amount=999),
                ]
            )
        )
        self.assertEqual(result["leaders"]["market"]["code"], "600001")
        self.assertEqual(result["leaders"]["market"]["seal_ratio"], 0.01)

    def test_missing_row_field_is_unclassified_even_when_another_field_fails(self) -> None:
        result = pick(_data([_stock(close_price=35, stock_float_market_cap=None)]))
        self.assertEqual(result["row1"], [])
        self.assertEqual(result["row2"], [])
        self.assertEqual([item["code"] for item in result["unclassified_rows"]], ["600000"])
        self.assertEqual(result["unclassified_rows"][0]["missing_fields"], ["stock_float_market_cap"])
        self.assertEqual(result["unclassified_rows"][0]["unmet"], [])


class MissingRowDataTest(unittest.TestCase):
    def test_all_first_and_second_boards_missing_fields_leave_rows_empty(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", name="首板缺值", streak_height=1, close_price=None, stock_float_market_cap=None),
                    _stock(code="600002", name="二板缺值", streak_height=2, close_price=None, stock_float_market_cap=None),
                    _stock(code="600003", name="总龙头", streak_height=5, close_price=None, stock_float_market_cap=None),
                ]
            )
        )
        self.assertEqual(result["status"], "unclassifiable_rows")
        self.assertEqual(
            result["message"],
            "首板和二板的收盘价、个股流通市值未保存，共2只，无法分排",
        )
        self.assertEqual(result["row1"], [])
        self.assertEqual(result["row2"], [])
        self.assertEqual([item["code"] for item in result["unclassified_rows"]], ["600002", "600001"])
        self.assertEqual(result["leaders"]["market"]["code"], "600003")

    def test_unclassifiable_message_names_only_the_missing_fields(self) -> None:
        result = pick(_data([_stock(stock_float_market_cap=None)]))
        self.assertEqual(result["status"], "unclassifiable_rows")
        self.assertEqual(result["message"], "首板和二板的个股流通市值未保存，共1只，无法分排")

    def test_pool_without_first_or_second_boards_is_reported(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", name="三板", streak_height=3, close_price=None, stock_float_market_cap=None),
                    _stock(code="600002", name="四板", streak_height=4, close_price=None, stock_float_market_cap=None),
                ]
            )
        )
        self.assertEqual(result["status"], "no_row_candidates")
        self.assertEqual(result["message"], "候选池内没有首板或二板")
        self.assertEqual(result["row1"], [])
        self.assertEqual(result["row2"], [])
        self.assertEqual(result["unclassified_rows"], [])
        self.assertEqual(result["leaders"]["market"]["code"], "600002")

    def test_some_missing_rows_are_listed_next_to_classified_rows(self) -> None:
        result = pick(
            _data(
                [
                    _stock(code="600001", name="能进一排", streak_height=1),
                    _stock(code="600002", name="明确二排", streak_height=1, close_price=35),
                    _stock(code="600003", name="缺市值", streak_height=2, stock_float_market_cap=None),
                ]
            )
        )
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["message"])
        self.assertEqual([item["code"] for item in result["row1"]], ["600001"])
        self.assertEqual([item["code"] for item in result["row2"]], ["600002"])
        self.assertEqual([item["code"] for item in result["unclassified_rows"]], ["600003"])


class CliTest(unittest.TestCase):
    def test_pick_reads_get_envelope(self) -> None:
        payload = {"ok": True, "data": json.loads(FIXTURE.read_text(encoding="utf-8")), "error": None}
        buffer = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
            with mock.patch("sys.stdout", buffer):
                code = cli.main(["pick", "--input", "-"])
        self.assertEqual(code, 0)
        output = json.loads(buffer.getvalue())
        self.assertTrue(output["ok"])
        self.assertEqual(output["data"]["leaders"]["market"]["code"], "600001")

    def test_pick_reads_input_file(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(FIXTURE.read_text(encoding="utf-8"))
            path = handle.name
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            code = cli.main(["pick", "--input", path])
        self.assertEqual(code, 0)
        output = json.loads(buffer.getvalue())
        self.assertTrue(output["ok"])
        self.assertEqual(output["data"]["leaders"]["market"]["code"], "600001")

    def test_missing_input_file_is_a_clean_error(self) -> None:
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            code = cli.main(["pick", "--input", "/nonexistent/get.json"])
        self.assertEqual(code, 1)
        output = json.loads(buffer.getvalue())
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "PICK_FAILED")

    def test_failed_get_is_rejected(self) -> None:
        payload = {"ok": False, "data": None, "error": {"code": "REMOTE_UNAVAILABLE", "message": "超时"}}
        buffer = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
            with mock.patch("sys.stdout", buffer):
                code = cli.main(["pick", "--input", "-"])
        self.assertEqual(code, 1)
        output = json.loads(buffer.getvalue())
        self.assertFalse(output["ok"])
        self.assertIn("REMOTE_UNAVAILABLE", output["error"]["message"])

    def test_duplicate_stock_is_an_error(self) -> None:
        with self.assertRaises(PickError):
            pick(_data([_stock(), _stock()]))


class SkillTextTest(unittest.TestCase):
    def test_skill_states_the_fixed_rules(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for phrase in (
            "不是交易日",
            "库内无记录",
            "库内无收盘涨停事件",
            "不足 3 个则全部列出",
            "Unicode 码位",
            "scripts/cli.py",
            "market",
            "code",
            "数据缺失，无法判定",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
