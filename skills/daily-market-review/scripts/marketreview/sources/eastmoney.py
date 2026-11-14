"""东方财富涨停/炸板股池访问（push2ex 接口，stdlib only）。

字段口径（2026-11 实测）：
- p：最新价 ×1000；fund：封板资金（元）；ltsz：流通市值（元）
- fbt/lbt：HHMMSS 整数（如 92500 → "09:25:00"）
- lbc：连板数（仅涨停池）；zttj.ct/days：N 日涨停统计
- hybk：所属行业短标签。接口自身可能截断（如「房地产开发」→「房地产开」），按原文入库，不修补
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

_BASE_URL = "https://push2ex.eastmoney.com/"
_QUERY = (
    "ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt"
    "&Pageindex=0&pagesize=1000&sort=fbt:asc&date={date}"
)


class EastMoneyPoolError(RuntimeError):
    """东财股池拉取失败或返回结构异常。"""


@dataclass(frozen=True)
class LimitPoolStock:
    market: str
    code: str
    name: str
    industry: str | None
    close_price: float | None
    seal_amount: float | None
    first_limit_time: str | None
    stock_float_market_cap: float | None
    turnover_amount: float | None
    streak_height: int | None
    broken_count: int | None


def _market_of(code: str, m_flag: object) -> str:
    # 代码前缀优先：60/68 → sh；0/3 → sz；4/8/920 → bj；m 标志（1=sh，0=sz）兜底
    if code.startswith(("60", "68")):
        return "sh"
    if code.startswith(("0", "3")):
        return "sz"
    if code.startswith(("4", "8", "920")):
        return "bj"
    return {1: "sh", 0: "sz"}.get(m_flag, "sz")


def _price(raw: object) -> float | None:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    return round(float(raw) / 1000, 2)


def _yuan(raw: object) -> float | None:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    return float(raw)


def _limit_time(raw: object) -> str | None:
    if not isinstance(raw, int) or isinstance(raw, bool):
        return None
    text = f"{raw:06d}"
    if len(text) != 6:
        return None
    return f"{text[0:2]}:{text[2:4]}:{text[4:6]}"


def _industry(raw: object) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def _int_or_none(raw: object) -> int | None:
    if not isinstance(raw, int) or isinstance(raw, bool):
        return None
    return raw


def _parse_stock(item: object, *, closed: bool) -> LimitPoolStock:
    if not isinstance(item, dict):
        raise EastMoneyPoolError(f"股池记录不是对象：{item!r}")
    code = item.get("c")
    name = item.get("n")
    if not isinstance(code, str) or not code or not isinstance(name, str) or not name:
        raise EastMoneyPoolError(f"股池记录缺少代码或名称：{item!r}")
    streak = _int_or_none(item.get("lbc")) if closed else None
    if streak is None and closed:
        zttj = item.get("zttj")
        if isinstance(zttj, dict):
            streak = _int_or_none(zttj.get("ct"))
    return LimitPoolStock(
        market=_market_of(code, item.get("m")),
        code=code,
        name=name,
        industry=_industry(item.get("hybk")),
        close_price=_price(item.get("p")),
        seal_amount=_yuan(item.get("fund")) if closed else None,
        first_limit_time=_limit_time(item.get("fbt")),
        stock_float_market_cap=_yuan(item.get("ltsz")),
        turnover_amount=_yuan(item.get("amount")),
        streak_height=streak,
        broken_count=_int_or_none(item.get("zbc")),
    )


class EastMoneyLimitPoolClient:
    TIMEOUT = 15
    MAX_RETRIES = 3

    @classmethod
    def fetch_zt_pool(cls, trade_date: str) -> list[LimitPoolStock]:
        """收盘涨停股池。trade_date 为 YYYY-MM-DD。"""
        return cls._fetch_pool("getTopicZTPool", trade_date, closed=True)

    @classmethod
    def fetch_zb_pool(cls, trade_date: str) -> list[LimitPoolStock]:
        """炸板股池。trade_date 为 YYYY-MM-DD。"""
        return cls._fetch_pool("getTopicZBPool", trade_date, closed=False)

    @classmethod
    def _fetch_pool(cls, endpoint: str, trade_date: str, *, closed: bool) -> list[LimitPoolStock]:
        compact = trade_date.replace("-", "")
        payload = cls._fetch_json(f"{_BASE_URL}{endpoint}?{_QUERY.format(date=compact)}")
        if not isinstance(payload, dict) or payload.get("rc") != 0:
            raise EastMoneyPoolError(f"东财股池返回异常：{endpoint} rc={payload.get('rc') if isinstance(payload, dict) else payload!r}")
        data = payload.get("data")
        if data is None:
            # 接口对无数据日期返回 data: null（如非交易日），按空池处理
            return []
        if not isinstance(data, dict) or not isinstance(data.get("pool"), list):
            raise EastMoneyPoolError(f"东财股池返回结构异常：{endpoint} 缺少 data.pool")
        return [_parse_stock(item, closed=closed) for item in data["pool"]]

    @classmethod
    def _fetch_json(cls, url: str) -> object:
        last_error: Exception | None = None
        for _ in range(cls.MAX_RETRIES):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "daily-market-review/0.1"})
                with urllib.request.urlopen(request, timeout=cls.TIMEOUT) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
        raise EastMoneyPoolError(f"东财股池请求失败：{last_error}")
