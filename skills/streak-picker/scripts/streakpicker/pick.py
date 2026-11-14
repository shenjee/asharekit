"""按 SKILL.md 的选股规则，把一次 get 结果分成三张表。

排序和筛选以本模块为准。展示单位在这里算好，调用方按输出顺序渲染，不另行重算。
"""

from __future__ import annotations

from typing import Any

ONE_HUNDRED_MILLION = 100_000_000
ROW1_PRICE_LIMIT = 30
ROW1_CAP_LIMIT = 10_000_000_000
ROW1_LIMIT_RATE_BP = 1000
STRONG_SECTOR_LIMIT = 3

STATUS_OK = "ok"
STATUS_NO_RECORD = "no_record"
STATUS_NO_CLOSED_LIMIT_UP = "no_closed_limit_up"
STATUS_NO_ROW_CANDIDATES = "no_row_candidates"
STATUS_UNCLASSIFIABLE_ROWS = "unclassifiable_rows"

MESSAGE_NO_RECORD = "库内无记录"
MESSAGE_NO_CLOSED_LIMIT_UP = "库内无收盘涨停事件"
MESSAGE_INTRADAY_UNDETERMINED = "数据缺失，无法判定"
MESSAGE_NO_ROW_CANDIDATES = "候选池内没有首板或二板"

ROW_FIELDS = ("close_price", "stock_float_market_cap", "limit_rate_bp")
FIELD_LABELS = {
    "close_price": "收盘价",
    "stock_float_market_cap": "个股流通市值",
    "limit_rate_bp": "涨停限幅",
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
    row1 = [_candidate_row(stock, missing=[], unmet=[]) for stock in _row_sorted(_row1(stocks))]
    row2 = [
        _candidate_row(stock, missing=[], unmet=unmet)
        for stock, unmet in _row2(stocks)
    ]
    unclassified = [
        _candidate_row(stock, missing=missing, unmet=[])
        for stock, missing in _unclassified_rows(stocks)
    ]
    has_classified_rows = bool(row1 or row2)
    status = STATUS_OK
    message = None
    if not any(item["streak_height"] in (1, 2) for item in stocks):
        status = STATUS_NO_ROW_CANDIDATES
        message = MESSAGE_NO_ROW_CANDIDATES
    elif not has_classified_rows and unclassified:
        status = STATUS_UNCLASSIFIABLE_ROWS
        message = _unclassifiable_message(unclassified)
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
        "row1": row1,
        "row2": row2,
        "unclassified_rows": unclassified,
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
            identity = (stock["market"], stock["code"])
            if identity in seen:
                raise PickError(f"候选池有重复股票：{stock['market']} {stock['code']}")
            seen.add(identity)
            if (
                stock["direction"] == "up"
                and stock["closed_at_limit"] is True
                and stock["streak_height"] >= 1
            ):
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
    reasons_raw = raw.get("limit_up_reasons")
    reasons = [] if reasons_raw is None else reasons_raw
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise PickError(f"{market} {code} 的 limit_up_reasons 必须是字符串数组或 null")
    streak = _integer(raw.get("streak_height"), f"{market} {code} 的 streak_height")
    if streak is None:
        raise PickError(f"{market} {code} 缺少 streak_height")
    return {
        "market": market,
        "code": code,
        "name": name,
        "direction": raw.get("direction"),
        "closed_at_limit": raw.get("closed_at_limit"),
        "streak_height": streak,
        "limit_rate_bp": _integer(raw.get("limit_rate_bp"), f"{market} {code} 的 limit_rate_bp"),
        "limit_up_reasons": list(dict.fromkeys(reasons)),
        "first_limit_time": _text_or_none(raw.get("first_limit_time"), f"{market} {code} 的 first_limit_time"),
        "seal_ratio": _number(raw.get("seal_ratio"), f"{market} {code} 的 seal_ratio"),
        "seal_amount": _number(raw.get("seal_amount"), f"{market} {code} 的 seal_amount"),
        "close_price": _number(raw.get("close_price"), f"{market} {code} 的 close_price"),
        "stock_float_market_cap": _number(
            raw.get("stock_float_market_cap"),
            f"{market} {code} 的 stock_float_market_cap",
        ),
    }


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
    return float(value)


def _text_or_none(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise PickError(f"{label} 必须是字符串或 null")
    return value


def _strong_sectors(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for stock in stocks:
        for reason in stock["limit_up_reasons"]:
            grouped.setdefault(reason, []).append(stock)
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
            "basis": _leader_basis(winner, tied),
        }
    )
    return row


def _leader_basis(winner: dict[str, Any], tied: list[dict[str, Any]]) -> str:
    parts = [
        f"{winner['streak_height']}板",
        f"首次涨停{_or_missing(winner['first_limit_time'])}",
        f"封成比{_format_ratio(winner['seal_ratio'])}",
        f"封单额{_format_amount(winner['seal_amount'])}",
    ]
    if tied:
        others = "、".join(f"{item['market']} {item['code']} {item['name']}" for item in tied)
        parts.append(f"同高度还有 {others}，按首次涨停时间、封成比、封单额、market、code 取本只")
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
    row = _leader_row("日内龙头", theme, winner, tied)
    row["basis"] = _leader_basis(winner, tied).replace("同高度还有", "同一涨停时间还有", 1)
    return row


def _unclassifiable_message(unclassified: list[dict[str, Any]]) -> str:
    missing = [
        field
        for field in ROW_FIELDS
        if any(field in item["missing_fields"] for item in unclassified)
    ]
    labels = "、".join(FIELD_LABELS[field] for field in missing)
    return f"首板和二板的{labels}未保存，共{len(unclassified)}只，无法分排"


def _row1(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [stock for stock in stocks if _row_split(stock) == (None, None)]


def _row2(stocks: list[dict[str, Any]]) -> list[tuple[dict[str, Any], list[str]]]:
    chosen: list[tuple[dict[str, Any], list[str]]] = []
    for stock in _row_sorted([item for item in stocks if item["streak_height"] in (1, 2)]):
        missing, unmet = _row_split(stock)
        if missing is None or missing:
            continue
        chosen.append((stock, unmet))
    return chosen


def _unclassified_rows(stocks: list[dict[str, Any]]) -> list[tuple[dict[str, Any], list[str]]]:
    chosen: list[tuple[dict[str, Any], list[str]]] = []
    for stock in _row_sorted([item for item in stocks if item["streak_height"] in (1, 2)]):
        missing, _unmet = _row_split(stock)
        if missing:
            chosen.append((stock, missing))
    return chosen


def _row_split(stock: dict[str, Any]) -> tuple[list[str], list[str]] | tuple[None, None]:
    if stock["streak_height"] not in (1, 2):
        return [], []
    missing: list[str] = []
    unmet: list[str] = []
    if stock["close_price"] is None:
        missing.append("close_price")
    elif stock["close_price"] >= ROW1_PRICE_LIMIT:
        unmet.append("收盘价不低于30元")
    if stock["stock_float_market_cap"] is None:
        missing.append("stock_float_market_cap")
    elif stock["stock_float_market_cap"] >= ROW1_CAP_LIMIT:
        unmet.append("个股流通市值不低于100亿")
    if stock["limit_rate_bp"] is None:
        missing.append("limit_rate_bp")
    elif stock["limit_rate_bp"] != ROW1_LIMIT_RATE_BP:
        unmet.append("涨停限幅不是10%")
    if not missing and not unmet:
        return None, None
    return missing, unmet


def _row_sorted(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(stocks, key=lambda item: (-item["streak_height"], item["market"], item["code"]))


def _candidate_row(
    stock: dict[str, Any],
    *,
    missing: list[str],
    unmet: list[str],
) -> dict[str, Any]:
    row = _stock_ref(stock)
    row.update(
        {
            "streak_height": stock["streak_height"],
            "close_price": stock["close_price"],
            "stock_float_market_cap": stock["stock_float_market_cap"],
            "limit_rate_bp": stock["limit_rate_bp"],
            "missing_fields": missing,
            "unmet": unmet,
            "basis": _candidate_basis(stock, missing, unmet),
        }
    )
    return row


def _candidate_basis(stock: dict[str, Any], missing: list[str], unmet: list[str]) -> str:
    facts = (
        f"{stock['streak_height']}板，收盘价{_format_price(stock['close_price'])}，"
        f"个股流通市值{_format_cap(stock['stock_float_market_cap'])}，"
        f"涨停限幅{_format_limit_rate(stock['limit_rate_bp'])}"
    )
    if not missing and not unmet:
        return f"{facts}，三项都确认满足"
    notes: list[str] = []
    if missing:
        notes.append("数据缺失：" + "、".join(FIELD_LABELS[item] for item in missing))
    if unmet:
        notes.append("未满足：" + "、".join(unmet))
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


def _format_cap(value: float | None) -> str:
    if value is None:
        return "缺失"
    return f"{value / ONE_HUNDRED_MILLION:.2f}亿元"


def _format_price(value: float | None) -> str:
    if value is None:
        return "缺失"
    return f"{value:.2f}元"


def _format_limit_rate(value: int | None) -> str:
    if value is None:
        return "缺失"
    if value % 100 == 0:
        return f"{value // 100}%"
    return f"{value}bp"
