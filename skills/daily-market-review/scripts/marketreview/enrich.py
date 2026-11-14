"""用东方财富涨停/炸板股池补齐涨停事件明细与 sectors。

口径：
- 只补缺，不覆盖：明细字段当前为 None、sectors 当前为空时才写入（人工优先）；
- 只处理 direction=up：收盘涨停对涨停池，炸板对炸板池，按 6 位代码匹配；跌停不参与补缺，也不进未匹配；
- 不写 limit_up_reasons（东财池没有该字段，原因文字维持人工喂入）；
- 连板数对账只报告、不改账。
"""

from __future__ import annotations

from typing import Any, Protocol

from .schema import DayRead, PriceLimitEventDetailRecord, PriceLimitEventRecord
from .sources.eastmoney import LimitPoolStock

_DETAIL_FILL_FIELDS = (
    "seal_amount",
    "first_limit_time",
    "close_price",
    "stock_float_market_cap",
    "turnover_amount",
)


class _DayReader(Protocol):
    def read_day(self, trade_date: str, previous_trade_date: str | None) -> DayRead: ...


class _DetailSaver(Protocol):
    def save_price_limit_event_details(self, trade_date: str, details: list[dict[str, Any]]) -> None: ...


def build_enrich_patches(
    events: list[PriceLimitEventRecord],
    details: list[PriceLimitEventDetailRecord],
    zt_pool: list[LimitPoolStock],
    zb_pool: list[LimitPoolStock],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """生成补缺 patch 与对账报告。不改账，写库由调用方决定。"""
    detail_by_id = {(d.market, d.code, d.direction): d for d in details}
    zt_by_code = {s.code: s for s in zt_pool}
    zb_by_code = {s.code: s for s in zb_pool}

    patches: list[dict[str, Any]] = []
    filled: dict[str, list[str]] = {}
    unmatched: list[dict[str, str]] = []
    streak_mismatch: list[dict[str, Any]] = []
    market_mismatch: list[dict[str, Any]] = []

    for event in events:
        if event.direction != "up":
            continue
        identity = f"{event.market} {event.code} {event.direction}"
        pool = zt_by_code if event.closed_at_limit else zb_by_code
        stock = pool.get(event.code)
        if stock is None:
            unmatched.append({"identity": identity, "name": event.name})
            continue
        if stock.market != event.market:
            market_mismatch.append({"identity": identity, "pool_market": stock.market})
            continue

        detail = detail_by_id.get((event.market, event.code, event.direction))
        patch: dict[str, Any] = {
            "market": event.market,
            "code": event.code,
            "direction": event.direction,
        }
        fields: list[str] = []
        for field in _DETAIL_FILL_FIELDS:
            current = getattr(detail, field) if detail is not None else None
            incoming = getattr(stock, field)
            if current is None and incoming is not None:
                patch[field] = incoming
                fields.append(field)
        current_sectors = detail.sectors if detail is not None else []
        if not current_sectors and stock.industry:
            patch["sectors"] = [stock.industry]
            fields.append("sectors")

        if fields:
            patches.append(patch)
            filled[identity] = fields

        if (
            event.direction == "up"
            and event.closed_at_limit
            and stock.streak_height is not None
            and stock.streak_height != event.streak_height
        ):
            streak_mismatch.append(
                {
                    "identity": identity,
                    "name": event.name,
                    "ledger_streak": event.streak_height,
                    "pool_streak": stock.streak_height,
                }
            )

    report = {
        "matched": len(filled),
        "unmatched": unmatched,
        "filled": filled,
        "streak_mismatch": streak_mismatch,
        "market_mismatch": market_mismatch,
    }
    return patches, report


def enrich_events(
    repo: _DayReader | Any,
    trade_date: str,
    *,
    zt_pool: list[LimitPoolStock],
    zb_pool: list[LimitPoolStock],
    dry_run: bool = False,
) -> dict[str, Any]:
    """读当日事件与明细，生成补缺 patch，非 dry-run 时写库。返回 JSON 报告。"""
    day = repo.read_day(trade_date, None)
    patches, report = build_enrich_patches(day.events, day.details, zt_pool, zb_pool)
    if patches and not dry_run:
        repo.save_price_limit_event_details(trade_date, patches)
    return {
        "trade_date": trade_date,
        "source": "eastmoney",
        "dry_run": dry_run,
        "patch_count": len(patches),
        "written": bool(patches) and not dry_run,
        **report,
    }
