"""静态个股板块字典。"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
BOARDS_PATH = SKILL_ROOT / "assets" / "stock_boards.csv"
HEADER = ["股票代码", "股票简称", "同花顺一级行业", "同花顺二级行业", "同花顺三级行业", "所属概念"]
EXCHANGE_ORDER = {"SH": 0, "SZ": 1, "BJ": 2}
JUHE_CODE = "605166.SH"


def load_boards() -> list[dict[str, str]]:
    with BOARDS_PATH.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def concept_tokens(text: str) -> list[str]:
    return [part.strip() for part in text.split("、") if part.strip()]


class TestStockBoards(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_boards()
        cls.by_code = {row["股票代码"]: row for row in cls.rows}

    def test_header_and_row_count(self) -> None:
        with BOARDS_PATH.open(encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh))
        self.assertEqual(header, HEADER)
        self.assertEqual(len(self.rows), 5582)
        self.assertEqual(len(self.by_code), 5582)

    def test_sorted_by_exchange_then_code(self) -> None:
        keys = []
        for row in self.rows:
            code = row["股票代码"]
            number, suffix = code.split(".")
            self.assertEqual(len(number), 6)
            self.assertIn(suffix, EXCHANGE_ORDER)
            keys.append((EXCHANGE_ORDER[suffix], number, suffix))
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(self.rows[0]["股票代码"], "600000.SH")
        self.assertTrue(self.rows[-1]["股票代码"].endswith(".BJ"))

    def test_concepts_drop_only_this_stocks_industry_names(self) -> None:
        for row in self.rows:
            industries = {
                row["同花顺一级行业"],
                row["同花顺二级行业"],
                row["同花顺三级行业"],
            }
            tokens = concept_tokens(row["所属概念"])
            self.assertTrue(tokens, row["股票代码"])
            self.assertTrue(all(row[column] for column in HEADER))
            if row["股票代码"] == JUHE_CODE:
                continue
            self.assertTrue(industries.isdisjoint(tokens), row["股票代码"])

    def test_jinyi_example(self) -> None:
        row = self.by_code["002905.SZ"]
        self.assertEqual(row["股票简称"], "金逸影视")
        self.assertEqual(
            [row["同花顺一级行业"], row["同花顺二级行业"], row["同花顺三级行业"]],
            ["传媒", "影视院线", "影视院线Ⅲ"],
        )
        self.assertEqual(row["所属概念"], "文化传媒概念、职业教育、虚拟现实、粤港澳大湾区")

    def test_named_examples(self) -> None:
        kaisa = concept_tokens(self.by_code["002425.SZ"]["所属概念"])
        self.assertIn("文化传媒概念", kaisa)
        self.assertNotIn("游戏Ⅲ", kaisa)

        xingfu = concept_tokens(self.by_code["300528.SZ"]["所属概念"])
        self.assertIn("文化传媒概念", xingfu)
        self.assertIn("AI影视制作", xingfu)
        self.assertNotIn("影视院线Ⅲ", xingfu)

        guotong = concept_tokens(self.by_code["002205.SZ"]["所属概念"])
        self.assertNotIn("建筑材料", guotong)
        self.assertNotIn("水泥", guotong)

        gansu = concept_tokens(self.by_code["000552.SZ"]["所属概念"])
        self.assertIn("煤炭概念", gansu)
        self.assertIn("动力煤", gansu)
        self.assertIn("页岩气开采", gansu)
        self.assertTrue({"煤炭", "煤炭开采加工", "煤炭开采"}.isdisjoint(gansu))

        meidi = concept_tokens(self.by_code["000333.SZ"]["所属概念"])
        self.assertIn("CDU", meidi)
        self.assertTrue({"家用电器", "白色家电", "空调"}.isdisjoint(meidi))

        # 不是行业名的重复概念按原顺序留两份。
        yunwang = concept_tokens(self.by_code["002306.SZ"]["所属概念"])
        self.assertEqual(yunwang.count("BC电池"), 2)

    def test_juheshun_keeps_original_concepts(self) -> None:
        row = self.by_code[JUHE_CODE]
        self.assertEqual(row["股票简称"], "聚合顺")
        self.assertEqual(row["所属概念"], "基础化工、化学纤维、其他纤维")


if __name__ == "__main__":
    unittest.main()
