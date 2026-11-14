"""Read-side daily ladder view for price-limit events."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Sequence

from .schema import (
    LadderGroup,
    LadderStock,
    LadderView,
    PriceLimitEventDetailRecord,
    PriceLimitEventRecord,
)


def compute_seal_ratio(
    seal_amount: float | None,
    turnover_amount: float | None,
) -> float | None:
    if seal_amount is None or turnover_amount is None:
        return None
    if turnover_amount == 0:
        return None
    return seal_amount / turnover_amount


def compute_auction_ratio(
    auction_amount: float | None,
    previous_turnover_amount: float | None,
) -> float | None:
    if auction_amount is None or previous_turnover_amount is None:
        return None
    if previous_turnover_amount == 0:
        return None
    return auction_amount / previous_turnover_amount


def compute_open_change(
    open_price: float | None,
    previous_close: float | None,
) -> float | None:
    if open_price is None or previous_close is None:
        return None
    if previous_close == 0:
        return None
    return open_price / previous_close - 1


def _detail_map(
    details: Sequence[PriceLimitEventDetailRecord],
) -> dict[tuple[str, str, str], PriceLimitEventDetailRecord]:
    return {(item.market, item.code, item.direction): item for item in details}


def _to_ladder_stock(
    event: PriceLimitEventRecord,
    detail: PriceLimitEventDetailRecord | None,
) -> LadderStock:
    return LadderStock(
        market=event.market,
        code=event.code,
        name=event.name,
        direction=event.direction,
        closed_at_limit=event.closed_at_limit,
        limit_rate_bp=event.limit_rate_bp,
        streak_height=event.streak_height,
        sectors=list(detail.sectors) if detail is not None else [],
        limit_up_reasons=list(detail.limit_up_reasons) if detail is not None else [],
        previous_turnover_amount=(
            detail.previous_turnover_amount if detail is not None else None
        ),
        auction_amount=detail.auction_amount if detail is not None else None,
        previous_close=detail.previous_close if detail is not None else None,
        open_price=detail.open_price if detail is not None else None,
        turnover_amount=detail.turnover_amount if detail is not None else None,
        turnover_rate=detail.turnover_rate if detail is not None else None,
        seal_amount=detail.seal_amount if detail is not None else None,
        seal_ratio=compute_seal_ratio(
            detail.seal_amount if detail is not None else None,
            detail.turnover_amount if detail is not None else None,
        ),
        first_limit_time=detail.first_limit_time if detail is not None else None,
        close_price=detail.close_price if detail is not None else None,
        stock_float_market_cap=detail.stock_float_market_cap if detail is not None else None,
        is_leader=detail.is_leader if detail is not None else None,
        note=detail.note if detail is not None else None,
        auction_ratio=compute_auction_ratio(
            detail.auction_amount if detail is not None else None,
            detail.previous_turnover_amount if detail is not None else None,
        ),
        open_change=compute_open_change(
            detail.open_price if detail is not None else None,
            detail.previous_close if detail is not None else None,
        ),
    )


def _sorted_stocks(stocks: Sequence[LadderStock]) -> list[LadderStock]:
    return sorted(stocks, key=lambda item: (item.market, item.code))


def build_ladder(
    events: Sequence[PriceLimitEventRecord],
    details: Sequence[PriceLimitEventDetailRecord] | None = None,
) -> LadderView:
    detail_map = _detail_map(details or [])
    grouped: dict[int, list[LadderStock]] = {}
    broken_limit_up: list[LadderStock] = []
    opened_limit_down: list[LadderStock] = []
    closed_limit_down: list[LadderStock] = []
    for event in events:
        detail = detail_map.get((event.market, event.code, event.direction))
        stock = _to_ladder_stock(event, detail)
        if event.direction == "up" and event.closed_at_limit and event.streak_height >= 1:
            grouped.setdefault(event.streak_height, []).append(stock)
        elif event.direction == "up" and not event.closed_at_limit:
            broken_limit_up.append(stock)
        elif event.direction == "down" and event.closed_at_limit:
            closed_limit_down.append(stock)
        elif event.direction == "down" and not event.closed_at_limit:
            opened_limit_down.append(stock)
    groups = [
        LadderGroup(
            streak_height=height,
            count=len(stocks),
            stocks=_sorted_stocks(stocks),
        )
        for height, stocks in sorted(grouped.items(), key=lambda item: -item[0])
    ]
    return LadderView(
        groups=groups,
        broken_limit_up=_sorted_stocks(broken_limit_up),
        opened_limit_down=_sorted_stocks(opened_limit_down),
        closed_limit_down=_sorted_stocks(closed_limit_down),
    )


def ladder_to_dict(ladder: LadderView) -> dict[str, Any]:
    return {
        "groups": [
            {
                "streak_height": group.streak_height,
                "count": group.count,
                "stocks": [asdict(stock) for stock in group.stocks],
            }
            for group in ladder.groups
        ],
        "broken_limit_up": [asdict(stock) for stock in ladder.broken_limit_up],
        "opened_limit_down": [asdict(stock) for stock in ladder.opened_limit_down],
        "closed_limit_down": [asdict(stock) for stock in ladder.closed_limit_down],
    }
