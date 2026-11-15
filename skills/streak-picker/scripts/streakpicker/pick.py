"""按 SKILL.md 的选股规则，把一次 get 结果分成三张表。

排序和筛选以本模块为准。展示单位在这里算好，调用方按输出顺序渲染，不另行重算。
`seal_ratio` 只读 get 已有值。`seal_to_float_ratio` 在这里现算，不写回封成比。
"""

from __future__ import annotations

import math
from typing import Any

ONE_HUNDRED_MILLION = 100_000_000
ROW1_MAX_CLOSE_PRICE = 30
ROW1_MAX_FLOAT_CAP = 100 * ONE_HUNDRED_MILLION
ROW1_LIMIT_RATE_BP = 1000
STRONG_SECTOR_LIMIT = 3
ROW_DISPLAY_LIMIT = 3

STATUS_OK = "ok"
STATUS_NO_RECORD = "no_record"
STATUS_NO_CLOSED_LIMIT_UP = "no_closed_limit_up"
STATUS_NO_ROW_CANDIDATES = "no_row_candidates"
STATUS_UNCLASSIFIABLE_ROWS = "unclassifiable_rows"

MESSAGE_NO_RECORD = "库内无记录"
MESSAGE_NO_CLOSED_LIMIT_UP = "库内无收盘涨停事件"
MESSAGE_INTRADAY_UNDETERMINED = "数据缺失，无法判定"
MESSAGE_NO_ROW_CANDIDATES = "候选池内没有首板或二板"

ROW_FIELDS = (
    "close_price",
    "stock_float_market_cap",
    "limit_rate_bp",
    "seal_ratio",
    "seal_amount",
    "first_limit_time",
)
FIELD_LABELS = {
    "close_price": "收盘价",
    "stock_float_market_cap": "个股流通市值",
    "limit_rate_bp": "涨停限幅",
    "seal_ratio": "封成比",
    "seal_amount": "封单额",
    "first_limit_time": "首次涨停时间",
}


class PickError(ValueError):
    """get 结果无法按选股规则计算。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def pick(data: dict[str, Any]) -> dict[str, Any]:
    """把 get 的 data 对象分成空结果或三张表。"""
    _require_get_data(data)
    events = data["events"] or []
    groups = data["ladder"]["groups"]
    if not groups:
        if data["review"] is None and len(events) == 0:
            return _empty(STATUS_NO_RECORD, MESSAGE_NO_RECORD)
        return _empty(STATUS_NO_CLOSED_LIMIT_UP, MESSAGE_NO_CLOSED_LIMIT_UP)

    stocks = _pool(groups)
    if not stocks:
        return _empty(STATUS_NO_CLOSED_LIMIT_UP, MESSAGE_NO_CLOSED_LIMIT_UP)

    strong = _strong_sectors(stocks)
    eligible, unclassified_all = _split_rows(stocks)
    row1_stocks = sorted((item for item in eligible if _is_row1(item)), key=_row1_sort_key)[
        :ROW_DISPLAY_LIMIT
    ]
    chosen = {(item["market"], item["code"]) for item in row1_stocks}
    row2_stocks = sorted(
        (item for item in eligible if (item["market"], item["code"]) not in chosen),
        key=_strength_sort_key,
    )[:ROW_DISPLAY_LIMIT]
    status = STATUS_OK
    message = None
    if not any(item["streak_height"] in (1, 2) for item in stocks):
        status = STATUS_NO_ROW_CANDIDATES
        message = MESSAGE_NO_ROW_CANDIDATES
    elif not eligible and unclassified_all:
        status = STATUS_UNCLASSIFIABLE_ROWS
        message = _unclassifiable_message(unclassified_all)
    return {
        "status": status,
        "message": message,
        "strong_sectors": [_sector_row(item) for item in strong],
        "leaders": {
            "market": _leader_row("总龙头", None, *_select_leader(stocks)),
            "sectors": [
                _leader_row("板块龙头", item["theme"], *_select_leader(item["stocks"]))
                for item in strong
            ],
            "intraday": [
                _intraday_row(item["theme"], item["stocks"]) for item in strong
            ],
        },
        "row1": [_candidate_row(stock, missing=[]) for stock in row1_stocks],
        "row2": [_candidate_row(stock, missing=[]) for stock in row2_stocks],
        "unclassified_rows": [
            _candidate_row(stock, missing=missing)
            for stock, missing in _capped_unclassified(unclassified_all)
        ],
    }


def _empty(status: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "strong_sectors": [],
        "leaders": {"market": None, "sectors": [], "intraday": []},
        "row1": [],
        "row2": [],
        "unclassified_rows": [],
    }


def _require_get_data(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise PickError("pick 输入必须是 get 的 data 对象")
    for key in ("review", "events", "ladder"):
        if key not in data:
            raise PickError(f"get 结果缺少 {key}")
    if data["events"] is not None and not isinstance(data["events"], list):
        raise PickError("get 结果的 events 必须是数组")
    ladder = data["ladder"]
    if not isinstance(ladder, dict) or not isinstance(ladder.get("groups"), list):
        raise PickError("get 结果的 ladder.groups 必须是数组")


def _pool(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stocks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("stocks"), list):
            raise PickError("ladder.groups 的每一组都必须包含 stocks 数组")
        for raw in group["stocks"]:
            stock = _normalize_stock(raw)
            if not (
                stock["direction"] == "up"
                and stock["closed_at_limit"] is True
                and stock["streak_height"] >= 1
            ):
                continue
            identity = (stock["market"], stock["code"])
            if identity in seen:
                raise PickError(f"候选池有重复股票：{stock['market']} {stock['code']}")
            seen.add(identity)
            stocks.append(stock)
    return stocks


def _normalize_stock(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise PickError("ladder 中的股票必须是对象")
    market = raw.get("market")
    code = raw.get("code")
    if not isinstance(market, str) or not market or not isinstance(code, str) or not code:
        raise PickError("候选股票缺少 market 或 code")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise PickError(f"{market} {code} 缺少 name")
    sectors_raw = raw.get("sectors")
    sectors = [] if sectors_raw is None else sectors_raw
    if not isinstance(sectors, list) or any(not isinstance(item, str) for item in sectors):
        raise PickError(f"{market} {code} 的 sectors 必须是字符串数组或 null")
    streak = _integer(raw.get("streak_height"), f"{market} {code} 的 streak_height")
    if streak is None:
        raise PickError(f"{market} {code} 缺少 streak_height")
    seal_amount = _number(raw.get("seal_amount"), f"{market} {code} 的 seal_amount")
    stock_float_market_cap = _number(
        raw.get("stock_float_market_cap"),
        f"{market} {code} 的 stock_float_market_cap",
    )
    return {
        "market": market,
        "code": code,
        "name": name,
        "direction": raw.get("direction"),
        "closed_at_limit": raw.get("closed_at_limit"),
        "streak_height": streak,
        "limit_rate_bp": _integer(raw.get("limit_rate_bp"), f"{market} {code} 的 limit_rate_bp"),
        "sectors": list(dict.fromkeys(sectors)),
        "first_limit_time": _text_or_none(raw.get("first_limit_time"), f"{market} {code} 的 first_limit_time"),
        "seal_ratio": _number(raw.get("seal_ratio"), f"{market} {code} 的 seal_ratio"),
        "seal_amount": seal_amount,
        "close_price": _number(raw.get("close_price"), f"{market} {code} 的 close_price"),
        "stock_float_market_cap": stock_float_market_cap,
        "seal_to_float_ratio": _seal_to_float_ratio(seal_amount, stock_float_market_cap),
    }


def _seal_to_float_ratio(seal_amount: float | None, stock_float_market_cap: float | None) -> float | None:
    """封单额 / 流通市值。空或 0 市值时为 null，不改写 seal_ratio。"""
    if seal_amount is None or stock_float_market_cap is None or stock_float_market_cap == 0:
        return None
    return seal_amount / stock_float_market_cap


def _integer(value: Any, label: str) -> int | None:
    number = _number(value, label)
    if number is None:
        return None
    if isinstance(value, float) and not value.is_integer():
        raise PickError(f"{label} 必须是整数")
    return int(number)


def _number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PickError(f"{label} 必须是数值或 null")
    number = float(value)
    if not math.isfinite(number):
        raise PickError(f"{label} 必须是有限数值")
    return number


def _text_or_none(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise PickError(f"{label} 必须是字符串或 null")
    return value


def _strong_sectors(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for stock in stocks:
        for sector in stock["sectors"]:
            grouped.setdefault(sector, []).append(stock)
    ranked = sorted(
        (
            {"theme": theme, "stocks": members, **_sector_stats(members)}
            for theme, members in grouped.items()
        ),
        key=lambda item: (
            -item["limit_up_count"],
            -item["max_streak"],
            item["earliest_limit_time"] is None,
            item["earliest_limit_time"] or "",
            item["seal_amount_sum"] is None,
            -(item["seal_amount_sum"] or 0),
            item["theme"],
        ),
    )
    return ranked[:STRONG_SECTOR_LIMIT]


def _sector_stats(members: list[dict[str, Any]]) -> dict[str, Any]:
    times = [item["first_limit_time"] for item in members if item["first_limit_time"] is not None]
    seals = [item["seal_amount"] for item in members if item["seal_amount"] is not None]
    return {
        "limit_up_count": len(members),
        "max_streak": max(item["streak_height"] for item in members),
        "earliest_limit_time": min(times) if times else None,
        "seal_amount_sum": sum(seals) if seals else None,
    }


def _sector_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "theme": item["theme"],
        "limit_up_count": item["limit_up_count"],
        "max_streak": item["max_streak"],
        "earliest_limit_time": item["earliest_limit_time"],
        "seal_amount_sum": item["seal_amount_sum"],
        "basis": (
            f"涨停{item['limit_up_count']}家，最高{item['max_streak']}板，"
            f"最早涨停{_or_missing(item['earliest_limit_time'])}，"
            f"封单额合计{_format_amount(item['seal_amount_sum'])}"
        ),
    }


def _select_leader(
    stocks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    height = max(item["streak_height"] for item in stocks)
    tied = [item for item in stocks if item["streak_height"] == height]
    ordered = sorted(tied, key=_leader_sort_key)
    return ordered[0], ordered[1:]


def _leader_sort_key(stock: dict[str, Any]) -> tuple[Any, ...]:
    return (
        stock["first_limit_time"] is None,
        stock["first_limit_time"] or "",
        stock["seal_ratio"] is None,
        -(stock["seal_ratio"] or 0),
        stock["seal_amount"] is None,
        -(stock["seal_amount"] or 0),
        stock["market"],
        stock["code"],
    )


def _leader_row(
    role: str,
    theme: str | None,
    winner: dict[str, Any],
    tied: list[dict[str, Any]],
    *,
    tied_label: str = "同高度还有",
) -> dict[str, Any]:
    row = _stock_ref(winner)
    row.update(
        {
            "role": role,
            "theme": theme,
            "undetermined": False,
            "streak_height": winner["streak_height"],
            "first_limit_time": winner["first_limit_time"],
            "seal_ratio": winner["seal_ratio"],
            "seal_amount": winner["seal_amount"],
            "tied": [_stock_ref(item) | {"streak_height": item["streak_height"]} for item in tied],
            "basis": _leader_basis(winner, tied, tied_label=tied_label),
        }
    )
    return row


def _leader_basis(
    winner: dict[str, Any],
    tied: list[dict[str, Any]],
    *,
    tied_label: str = "同高度还有",
) -> str:
    parts = [
        f"{winner['streak_height']}板",
        f"首次涨停{_or_missing(winner['first_limit_time'])}",
        f"封成比{_format_ratio(winner['seal_ratio'])}",
        f"封单额{_format_amount(winner['seal_amount'])}",
    ]
    if not tied:
        return "，".join(parts)
    others = "、".join(f"{item['market']} {item['code']} {item['name']}" for item in tied)
    business_keys_all_missing = (
        winner["first_limit_time"] is None
        and winner["seal_ratio"] is None
        and winner["seal_amount"] is None
    )
    if business_keys_all_missing:
        return (
            f"{winner['streak_height']}板，首次涨停时间、封成比、封单额均缺失；"
            f"按 market/code 顺序展示，其余同高度股票为 {others}"
        )
    parts.append(f"{tied_label} {others}，按首次涨停时间、封成比、封单额、market、code 取本只")
    return "，".join(parts)


def _intraday_row(theme: str, stocks: list[dict[str, Any]]) -> dict[str, Any]:
    timed = [item for item in stocks if item["first_limit_time"] is not None]
    if not timed:
        return {
            "role": "日内龙头",
            "theme": theme,
            "undetermined": True,
            "market": None,
            "code": None,
            "name": None,
            "streak_height": None,
            "first_limit_time": None,
            "seal_ratio": None,
            "seal_amount": None,
            "tied": [],
            "basis": MESSAGE_INTRADAY_UNDETERMINED,
        }
    ordered = sorted(timed, key=_leader_sort_key)
    winner = ordered[0]
    tied = [item for item in ordered[1:] if item["first_limit_time"] == winner["first_limit_time"]]
    return _leader_row("日内龙头", theme, winner, tied, tied_label="同一涨停时间还有")


def _split_rows(
    stocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], list[str]]]]:
    eligible: list[dict[str, Any]] = []
    unclassified: list[tuple[dict[str, Any], list[str]]] = []
    for stock in stocks:
        if stock["streak_height"] not in (1, 2):
            continue
        missing = _row_missing(stock)
        if missing:
            unclassified.append((stock, missing))
        else:
            eligible.append(stock)
    return eligible, unclassified


def _row_missing(stock: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if stock["close_price"] is None:
        missing.append("close_price")
    cap = stock["stock_float_market_cap"]
    if cap is None or cap == 0:
        missing.append("stock_float_market_cap")
    if stock["limit_rate_bp"] is None:
        missing.append("limit_rate_bp")
    if stock["seal_ratio"] is None:
        missing.append("seal_ratio")
    if stock["seal_amount"] is None:
        missing.append("seal_amount")
    if stock["first_limit_time"] is None:
        missing.append("first_limit_time")
    return missing


def _is_row1(stock: dict[str, Any]) -> bool:
    """一排三道门槛同时成立：收盘价 < 30、流通市值 < 100 亿、10cm。"""
    price = stock["close_price"]
    cap = stock["stock_float_market_cap"]
    return (
        price is not None
        and price < ROW1_MAX_CLOSE_PRICE
        and cap is not None
        and 0 < cap < ROW1_MAX_FLOAT_CAP
        and stock["limit_rate_bp"] == ROW1_LIMIT_RATE_BP
    )


def _strength_sort_key(stock: dict[str, Any]) -> tuple[Any, ...]:
    """封锁强度五键。前两键打平后才比较绝对封单额，然后才是首次涨停时间。"""
    return (
        stock["seal_ratio"] is None,
        -(stock["seal_ratio"] or 0),
        stock["seal_to_float_ratio"] is None,
        -(stock["seal_to_float_ratio"] or 0),
        stock["seal_amount"] is None,
        -(stock["seal_amount"] or 0),
        stock["first_limit_time"] is None,
        stock["first_limit_time"] or "",
        stock["market"],
        stock["code"],
    )


def _row1_sort_key(stock: dict[str, Any]) -> tuple[Any, ...]:
    """过了价格、市值、10cm 之后：二板优先于首板，再按封锁强度五键。"""
    return (-stock["streak_height"], *_strength_sort_key(stock))


def _capped_unclassified(
    unclassified: list[tuple[dict[str, Any], list[str]]],
) -> list[tuple[dict[str, Any], list[str]]]:
    ordered = sorted(unclassified, key=lambda item: (item[0]["market"], item[0]["code"]))
    return ordered[:ROW_DISPLAY_LIMIT]


def _unclassifiable_message(unclassified: list[tuple[dict[str, Any], list[str]]]) -> str:
    missing = [
        field
        for field in ROW_FIELDS
        if any(field in item_missing for _stock, item_missing in unclassified)
    ]
    labels = "、".join(FIELD_LABELS[field] for field in missing)
    zero_cap = any(
        stock["stock_float_market_cap"] == 0
        for stock, item_missing in unclassified
        if "stock_float_market_cap" in item_missing
    )
    if zero_cap and all(
        stock["stock_float_market_cap"] == 0 or "stock_float_market_cap" not in item_missing
        for stock, item_missing in unclassified
    ) and missing == ["stock_float_market_cap"]:
        return f"首板和二板的个股流通市值为 0，共{len(unclassified)}只，无法分排"
    return f"首板和二板的{labels}未保存，共{len(unclassified)}只，无法分排"


def _candidate_row(stock: dict[str, Any], *, missing: list[str]) -> dict[str, Any]:
    row = _stock_ref(stock)
    row.update(
        {
            "streak_height": stock["streak_height"],
            "close_price": stock["close_price"],
            "stock_float_market_cap": stock["stock_float_market_cap"],
            "limit_rate_bp": stock["limit_rate_bp"],
            "seal_ratio": stock["seal_ratio"],
            "seal_to_float_ratio": stock["seal_to_float_ratio"],
            "seal_amount": stock["seal_amount"],
            "first_limit_time": stock["first_limit_time"],
            "missing_fields": missing,
            "basis": _candidate_basis(stock, missing),
        }
    )
    return row


def _candidate_basis(stock: dict[str, Any], missing: list[str]) -> str:
    facts = (
        f"{stock['streak_height']}板，涨停限幅{_format_limit_rate(stock['limit_rate_bp'])}，"
        f"封成比{_format_ratio(stock['seal_ratio'])}，"
        f"封单额/流通市值{_format_ratio(stock['seal_to_float_ratio'])}，"
        f"封单额{_format_amount(stock['seal_amount'])}，"
        f"首次涨停{_or_missing(stock['first_limit_time'])}"
    )
    if not missing:
        return facts
    notes: list[str] = []
    cap = stock["stock_float_market_cap"]
    null_fields = [
        field
        for field in missing
        if not (field == "stock_float_market_cap" and cap == 0)
    ]
    if cap == 0 and "stock_float_market_cap" in missing:
        notes.append("个股流通市值为 0")
    if null_fields:
        notes.append("数据缺失：" + "、".join(FIELD_LABELS[item] for item in null_fields))
    return f"{facts}；" + "；".join(notes)


def _stock_ref(stock: dict[str, Any]) -> dict[str, Any]:
    return {"market": stock["market"], "code": stock["code"], "name": stock["name"]}


def _or_missing(value: str | None) -> str:
    return value if value is not None else "缺失"


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "缺失"
    return f"{value * 100:.2f}%"


def _format_amount(value: float | None) -> str:
    if value is None:
        return "缺失"
    if abs(value) >= ONE_HUNDRED_MILLION:
        return f"{value / ONE_HUNDRED_MILLION:.2f}亿元"
    return f"{value / 10_000:.2f}万元"


def _format_limit_rate(value: int | None) -> str:
    if value is None:
        return "缺失"
    if value % 100 == 0:
        return f"{value // 100}%"
    return f"{value}bp"
