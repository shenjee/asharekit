"""东财股池解析与 enrich 补缺口径。"""

from __future__ import annotations

import unittest
from unittest import mock

import _bootstrap  # noqa: F401

from marketreview.enrich import build_enrich_patches, enrich_events
from marketreview.schema import PriceLimitEventDetailRecord, PriceLimitEventRecord
from marketreview.sources.eastmoney import (
    EastMoneyLimitPoolClient,
    EastMoneyPoolError,
    LimitPoolStock,
    _parse_stock,
)


def _zt_raw(**overrides: object) -> dict:
    raw = {
        "c": "603366",
        "m": 1,
        "n": "日出东方",
        "p": 25660,
        "zdp": 9.99,
        "amount": 38862070,
        "ltsz": 4943043301.08,
        "tshare": 4953984083.58,
        "hs": 0.78,
        "lbc": 5,
        "fbt": 93018,
        "lbt": 93018,
        "fund": 170182252,
        "zbc": 0,
        "hybk": "厨卫电器",
        "zttj": {"days": 8, "ct": 5},
    }
    raw.update(overrides)
    return raw


def _stock(**overrides: object) -> LimitPoolStock:
    payload = {
        "market": "sh",
        "code": "603366",
        "name": "日出东方",
        "industry": "厨卫电器",
        "close_price": 25.66,
        "seal_amount": 170182252.0,
        "first_limit_time": "09:30:18",
        "stock_float_market_cap": 4943043301.08,
        "turnover_amount": 38862070.0,
        "streak_height": 5,
        "broken_count": 0,
    }
    payload.update(overrides)
    return LimitPoolStock(**payload)


def _event(**overrides: object) -> PriceLimitEventRecord:
    payload = {
        "trade_date": "2026-11-12",
        "market": "sh",
        "code": "603366",
        "name": "日出东方",
        "direction": "up",
        "closed_at_limit": True,
        "limit_rate_bp": 1000,
        "streak_height": 5,
    }
    payload.update(overrides)
    return PriceLimitEventRecord(**payload)


def _detail(**overrides: object) -> PriceLimitEventDetailRecord:
    payload = {
        "trade_date": "2026-11-12",
        "market": "sh",
        "code": "603366",
        "direction": "up",
        "previous_turnover_amount": None,
        "auction_amount": None,
        "previous_close": None,
        "open_price": None,
        "turnover_amount": None,
        "turnover_rate": None,
        "seal_amount": None,
        "seal_ratio": None,
        "first_limit_time": None,
        "close_price": None,
        "stock_float_market_cap": None,
        "is_leader": None,
        "note": None,
        "sectors": [],
        "limit_up_reasons": [],
    }
    payload.update(overrides)
    return PriceLimitEventDetailRecord(**payload)


class ParseStockTest(unittest.TestCase):
    def test_units_and_market(self) -> None:
        stock = _parse_stock(_zt_raw(), closed=True)
        self.assertEqual(stock.market, "sh")
        self.assertEqual(stock.close_price, 25.66)  # p ÷ 1000
        self.assertEqual(stock.first_limit_time, "09:30:18")  # 93018 → HH:MM:SS
        self.assertEqual(stock.seal_amount, 170182252.0)
        self.assertEqual(stock.stock_float_market_cap, 4943043301.08)
        self.assertEqual(stock.streak_height, 5)
        self.assertEqual(stock.industry, "厨卫电器")

    def test_sz_market_from_code_prefix(self) -> None:
        stock = _parse_stock(_zt_raw(c="002623", m=0), closed=True)
        self.assertEqual(stock.market, "sz")

    def test_bj_market_from_code_prefix(self) -> None:
        stock = _parse_stock(_zt_raw(c="830799", m=0), closed=True)
        self.assertEqual(stock.market, "bj")

    def test_zb_stock_has_no_seal_or_streak(self) -> None:
        stock = _parse_stock(_zt_raw(fbt=92500), closed=False)
        self.assertIsNone(stock.seal_amount)
        self.assertIsNone(stock.streak_height)
        self.assertEqual(stock.first_limit_time, "09:25:00")

    def test_industry_kept_verbatim_even_when_truncated(self) -> None:
        # 东财接口自身会截断行业标签（「房地产开发」→「房地产开」），按原文入库
        stock = _parse_stock(_zt_raw(hybk="房地产开"), closed=True)
        self.assertEqual(stock.industry, "房地产开")

    def test_missing_code_is_an_error(self) -> None:
        with self.assertRaises(EastMoneyPoolError):
            _parse_stock({"n": "无代码"}, closed=True)


class FetchPoolTest(unittest.TestCase):
    def _payload(self, pool: list[dict]) -> dict:
        return {"rc": 0, "data": {"tc": len(pool), "pool": pool}}

    def test_fetch_zt_pool_parses_list(self) -> None:
        with mock.patch.object(
            EastMoneyLimitPoolClient, "_fetch_json", return_value=self._payload([_zt_raw()])
        ):
            pool = EastMoneyLimitPoolClient.fetch_zt_pool("2026-11-12")
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0].code, "603366")

    def test_null_data_means_empty_pool(self) -> None:
        with mock.patch.object(EastMoneyLimitPoolClient, "_fetch_json", return_value={"rc": 0, "data": None}):
            self.assertEqual(EastMoneyLimitPoolClient.fetch_zt_pool("2026-11-15"), [])

    def test_bad_structure_is_an_error(self) -> None:
        with mock.patch.object(EastMoneyLimitPoolClient, "_fetch_json", return_value={"rc": 1}):
            with self.assertRaises(EastMoneyPoolError):
                EastMoneyLimitPoolClient.fetch_zt_pool("2026-11-12")


class BuildPatchesTest(unittest.TestCase):
    def test_fills_only_missing_fields_and_not_sectors(self) -> None:
        events = [_event()]
        details = [_detail(seal_amount=999.0, sectors=["人工板块"])]
        patches, report = build_enrich_patches(events, details, [_stock()], [])
        self.assertEqual(len(patches), 1)
        patch = patches[0]
        self.assertNotIn("seal_amount", patch)  # 人工值不覆盖
        self.assertNotIn("sectors", patch)  # 所属板块不来自东财
        self.assertEqual(patch["close_price"], 25.66)
        self.assertEqual(patch["first_limit_time"], "09:30:18")
        self.assertEqual(patch["stock_float_market_cap"], 4943043301.08)
        self.assertEqual(patch["turnover_amount"], 38862070.0)
        self.assertEqual(report["matched"], 1)

    def test_does_not_fill_sectors_from_eastmoney(self) -> None:
        patches, _report = build_enrich_patches([_event()], [_detail()], [_stock()], [])
        self.assertNotIn("sectors", patches[0])

    def test_no_detail_row_still_fills(self) -> None:
        patches, _report = build_enrich_patches([_event()], [], [_stock()], [])
        self.assertIn("seal_amount", patches[0])
        self.assertNotIn("sectors", patches[0])

    def test_broken_event_uses_zb_pool(self) -> None:
        broken = _event(closed_at_limit=False, streak_height=0)
        zb = _stock(seal_amount=None, streak_height=None)
        patches, report = build_enrich_patches([broken], [], [], [zb])
        self.assertEqual(len(patches), 1)
        self.assertNotIn("seal_amount", patches[0])
        self.assertEqual(report["streak_mismatch"], [])

    def test_unmatched_and_streak_mismatch_are_reported_only(self) -> None:
        events = [_event(code="600001", streak_height=3), _event(code="600002", streak_height=5)]
        pool = [_stock(code="600001", streak_height=4)]
        patches, report = build_enrich_patches(events, [], pool, [])
        self.assertEqual(len(patches), 1)
        self.assertEqual(report["unmatched"][0]["identity"], "sh 600002 up")
        self.assertEqual(
            report["streak_mismatch"],
            [{"identity": "sh 600001 up", "name": "日出东方", "ledger_streak": 3, "pool_streak": 4}],
        )

    def test_market_mismatch_skips_fill(self) -> None:
        patches, report = build_enrich_patches(
            [_event(market="sz", code="003366")],
            [],
            [_stock(market="sh", code="003366")],
            [],
        )
        self.assertEqual(patches, [])
        self.assertEqual(len(report["market_mismatch"]), 1)

    def test_down_events_are_skipped_not_unmatched(self) -> None:
        down_closed = _event(direction="down", closed_at_limit=True, streak_height=0, code="600010", name="收盘跌停")
        down_opened = _event(direction="down", closed_at_limit=False, streak_height=0, code="600011", name="打开跌停")
        # 跌停代码即使出现在涨停池里也不补、不计未匹配
        pool = [_stock(), _stock(code="600010"), _stock(code="600011")]
        patches, report = build_enrich_patches([down_closed, down_opened, _event()], [], pool, [])
        self.assertEqual([patch["code"] for patch in patches], ["603366"])
        self.assertEqual(report["unmatched"], [])
        self.assertEqual(report["market_mismatch"], [])

    def test_never_writes_limit_up_reasons(self) -> None:
        patches, _report = build_enrich_patches([_event()], [_detail()], [_stock()], [])
        for patch in patches:
            self.assertNotIn("limit_up_reasons", patch)


class EnrichEventsTest(unittest.TestCase):
    def test_dry_run_does_not_write(self) -> None:
        repo = mock.Mock()
        day = mock.Mock()
        day.events = [_event()]
        day.details = []
        repo.read_day.return_value = day
        report = enrich_events(repo, "2026-11-12", zt_pool=[_stock()], zb_pool=[], dry_run=True)
        repo.save_price_limit_event_details.assert_not_called()
        self.assertFalse(report["written"])
        self.assertEqual(report["patch_count"], 1)

    def test_writes_when_not_dry_run(self) -> None:
        repo = mock.Mock()
        day = mock.Mock()
        day.events = [_event()]
        day.details = []
        repo.read_day.return_value = day
        report = enrich_events(repo, "2026-11-12", zt_pool=[_stock()], zb_pool=[], dry_run=False)
        repo.save_price_limit_event_details.assert_called_once()
        self.assertTrue(report["written"])


if __name__ == "__main__":
    unittest.main()
