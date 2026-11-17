"""随包安装的同花顺个股板块字典。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .errors import MarketReviewError

_HEADER = ("股票代码", "股票简称", "同花顺一级行业", "同花顺二级行业", "同花顺三级行业", "所属概念")


def stock_boards_path() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "stock_boards.csv"


@dataclass(frozen=True)
class StockBoard:
    code: str
    name: str
    industry_l1: str
    industry_l2: str
    industry_l3: str
    concepts: tuple[str, ...]


def concept_tokens(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split("、") if part.strip())


@lru_cache(maxsize=1)
def load_stock_boards() -> dict[str, StockBoard]:
    """按 `600000.SH` 这种代码索引。文件随 skill 安装，缺失即无法计算板块。"""
    path = stock_boards_path()
    if not path.is_file():
        raise MarketReviewError(
            code="SECTOR_DICTIONARY_MISSING",
            message=f"个股板块字典不存在：{path}",
        )
    boards: dict[str, StockBoard] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _HEADER:
            raise MarketReviewError(
                code="SECTOR_DICTIONARY_MISSING",
                message="个股板块字典表头与 #22 不一致",
            )
        for row in reader:
            board = StockBoard(
                code=row["股票代码"],
                name=row["股票简称"],
                industry_l1=row["同花顺一级行业"],
                industry_l2=row["同花顺二级行业"],
                industry_l3=row["同花顺三级行业"],
                concepts=concept_tokens(row["所属概念"]),
            )
            boards[board.code] = board
    return boards
