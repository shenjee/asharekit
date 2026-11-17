"""用静态板块字典计算当日收盘涨停的所属板块。

字典只提供存货。写入 `sectors` 的是当天这批收盘涨停的结论，不把个股概念原样抄进去。
炸板和跌停不参与。东财行业标签不再写入 `sectors`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .stock_boards import StockBoard, load_stock_boards

BROAD_CONCEPTS = frozenset(
    {
        "融资融券",
        "沪股通",
        "深股通",
        "国企改革",
        "央企国企改革",
        "华为概念",
        "专精特新",
        "创投",
        "乡村振兴",
        "粤港澳大湾区",
    }
)
_MARKET_SUFFIX = {"sh": "SH", "sz": "SZ", "bj": "BJ"}


class _DayReader(Protocol):
    def read_day(self, trade_date: str, previous_trade_date: str | None) -> Any: ...


class _DetailSaver(Protocol):
    def save_price_limit_event_details(self, trade_date: str, details: list[dict[str, Any]]) -> None: ...


@dataclass(frozen=True)
class PoolStock:
    market: str
    code: str
    name: str


@dataclass(frozen=True)
class SectorGroup:
    sectors: tuple[str, ...]
    members: tuple[PoolStock, ...]

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass(frozen=True)
class SectorClassification:
    groups: tuple[SectorGroup, ...]
    sectors_by_stock: dict[tuple[str, str], tuple[str, ...]]
    missing: tuple[PoolStock, ...]
    stocks: tuple[PoolStock, ...]


@dataclass(frozen=True)
class _Resolved:
    stock: PoolStock
    concepts: frozenset[str]
    industry_l2: str


def dictionary_code(market: str, code: str) -> str | None:
    suffix = _MARKET_SUFFIX.get(market)
    if suffix is None or len(code) != 6 or not code.isdigit():
        return None
    return f"{code}.{suffix}"


def filtered_concepts(board: StockBoard) -> frozenset[str]:
    industries = {board.industry_l1, board.industry_l2, board.industry_l3}
    return frozenset(
        concept
        for concept in board.concepts
        if concept not in BROAD_CONCEPTS and concept not in industries
    )


def classify_limit_ups(
    stocks: Sequence[PoolStock],
    boards: Mapping[str, StockBoard],
) -> SectorClassification:
    """只对传入的收盘涨停圈组。调用方负责排除炸板和跌停。"""
    resolved: list[_Resolved] = []
    missing: list[PoolStock] = []
    ordered: list[PoolStock] = []
    seen: set[tuple[str, str]] = set()
    for stock in stocks:
        key = (stock.market, stock.code)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(stock)
        board_code = dictionary_code(stock.market, stock.code)
        board = boards.get(board_code) if board_code is not None else None
        if board is None:
            missing.append(stock)
            continue
        resolved.append(
            _Resolved(stock=stock, concepts=filtered_concepts(board), industry_l2=board.industry_l2)
        )

    by_key = {(item.stock.market, item.stock.code): item for item in resolved}
    members_by_concept: dict[str, set[tuple[str, str]]] = {}
    for item in resolved:
        key = (item.stock.market, item.stock.code)
        for concept in item.concepts:
            members_by_concept.setdefault(concept, set()).add(key)

    # 2 只及以上：相同成员集合并成一组，属性是全体概念的交集。
    # 只有 1 只：每个概念单独成组，只写这一个概念，不把该股其余概念并进交集。
    candidates: list[tuple[frozenset[tuple[str, str]], tuple[str, ...]]] = []
    seen_multi: set[frozenset[tuple[str, str]]] = set()
    for concept, keys in members_by_concept.items():
        member_set = frozenset(keys)
        if len(member_set) == 1:
            candidates.append((member_set, (concept,)))
            continue
        if member_set in seen_multi:
            continue
        seen_multi.add(member_set)
        intersection = frozenset.intersection(*(by_key[key].concepts for key in member_set))
        candidates.append((member_set, tuple(sorted(intersection))))

    # 全部成员已被更大组覆盖的子集不单列。去掉这些成员后只剩 1 只的组仍保留。
    kept = [
        candidate
        for candidate in candidates
        if not any(candidate[0] < other[0] for other in candidates)
    ]

    sectors_by_stock: dict[tuple[str, str], tuple[str, ...]] = {}
    for item in resolved:
        key = (item.stock.market, item.stock.code)
        containing = [candidate for candidate in kept if key in candidate[0]]
        if not containing:
            sectors_by_stock[key] = (item.industry_l2,) if item.industry_l2 else ()
            continue
        max_size = max(len(candidate[0]) for candidate in containing)
        chosen = sorted(
            (candidate for candidate in containing if len(candidate[0]) == max_size),
            key=lambda candidate: candidate[1],
        )
        labels: list[str] = []
        for _member_set, sectors in chosen:
            for label in sectors:
                if label not in labels:
                    labels.append(label)
        sectors_by_stock[key] = tuple(labels)

    for stock in missing:
        sectors_by_stock[(stock.market, stock.code)] = ()

    groups: list[SectorGroup] = []
    for member_set, sectors in kept:
        is_max_for_someone = False
        for key in member_set:
            member_max = max(len(other[0]) for other in kept if key in other[0])
            if member_max == len(member_set):
                is_max_for_someone = True
                break
        if not is_max_for_someone:
            continue
        members = tuple(
            by_key[key].stock
            for key in sorted(member_set, key=lambda item: (item[0], item[1]))
        )
        groups.append(SectorGroup(sectors=sectors, members=members))
    groups.sort(key=lambda group: (-group.size, group.sectors))

    return SectorClassification(
        groups=tuple(groups),
        sectors_by_stock=sectors_by_stock,
        missing=tuple(sorted(missing, key=lambda stock: (stock.market, stock.code))),
        stocks=tuple(ordered),
    )


def apply_saved_limit_up_sectors(
    repo: _DayReader | _DetailSaver | Any,
    trade_date: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """读取当日已保存的收盘涨停，计算所属板块，非 dry-run 时写回 `sectors`。"""
    day = repo.read_day(trade_date, None)
    pool = [
        PoolStock(event.market, event.code, event.name)
        for event in day.events
        if event.direction == "up" and event.closed_at_limit
    ]
    result = classify_limit_ups(pool, load_stock_boards())
    patches = [
        {
            "market": stock.market,
            "code": stock.code,
            "direction": "up",
            "sectors": list(result.sectors_by_stock[(stock.market, stock.code)]),
        }
        for stock in sorted(pool, key=lambda item: (item.market, item.code))
    ]
    # 同一只收盘涨停只写一次。
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for patch in patches:
        key = (patch["market"], patch["code"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(patch)
    written = bool(deduped) and not dry_run
    if written:
        repo.save_price_limit_event_details(trade_date, deduped)
    return _report(trade_date, result, dry_run=dry_run, written=written)


def _report(
    trade_date: str,
    result: SectorClassification,
    *,
    dry_run: bool,
    written: bool,
) -> dict[str, Any]:
    names = {(stock.market, stock.code): stock.name for stock in result.stocks}
    assignments = []
    for key in sorted(result.sectors_by_stock):
        market, code = key
        assignments.append(
            {
                "market": market,
                "code": code,
                "name": names.get(key, ""),
                "sectors": list(result.sectors_by_stock[key]),
            }
        )
    return {
        "trade_date": trade_date,
        "dry_run": dry_run,
        "written": written,
        "group_count": len(result.groups),
        "groups": [
            {
                "sectors": list(group.sectors),
                "count": group.size,
                "members": [
                    {"market": member.market, "code": member.code, "name": member.name}
                    for member in group.members
                ],
            }
            for group in result.groups
        ],
        "assignments": assignments,
        "missing": [
            {"market": stock.market, "code": stock.code, "name": stock.name}
            for stock in result.missing
        ],
    }
