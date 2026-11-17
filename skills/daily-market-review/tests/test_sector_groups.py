"""收盘涨停所属板块：按概念圈组、求交，再写回 sectors。"""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401

from marketreview.sector_groups import PoolStock, classify_limit_ups
from marketreview.stock_boards import StockBoard, load_stock_boards

# #24 验收：2026-11-13 的 37 只有效涨停。
NAMES = [
    "飞乐音响",
    "福达股份",
    "日盈电子",
    "福龙马",
    "中马传动",
    "天普股份",
    "维通利",
    "日发精机",
    "东方中科",
    "美晨科技",
    "华胜天成",
    "文投控股",
    "中国电影",
    "横店影视",
    "南威软件",
    "凯撒文化",
    "湖北广电",
    "儒意电影",
    "金逸影视",
    "幸福蓝海",
    "金辰股份",
    "兴业股份",
    "北纬科技",
    "华东重机",
    "天邦食品",
    "金新农",
    "通化金马",
    "华孚时尚",
    "广百股份",
    "法狮龙",
    "新能股份",
    "国统股份",
    "岳阳兴长",
    "世龙实业",
    "兴欣新材",
    "好当家",
    "皮阿诺",
]

EXPECTED_GROUPS = [
    (("新能源汽车",), {"飞乐音响", "福达股份", "日盈电子", "福龙马", "中马传动", "天普股份", "维通利", "日发精机", "东方中科", "美晨科技"}),
    (("AI应用",), {"华胜天成", "文投控股", "中国电影", "横店影视", "福达股份", "南威软件", "凯撒文化", "东方中科"}),
    (("文化传媒概念",), {"文投控股", "中国电影", "横店影视", "湖北广电", "凯撒文化", "儒意电影", "金逸影视", "幸福蓝海"}),
    (("芯片概念",), {"华胜天成", "飞乐音响", "日盈电子", "金辰股份", "兴业股份", "北纬科技", "华东重机", "东方中科"}),
    (("机器人概念",), {"福达股份", "日盈电子", "福龙马", "天邦食品", "北纬科技", "日发精机", "金新农"}),
    (("DeepSeek概念",), {"华胜天成", "南威软件", "通化金马", "华孚时尚", "华东重机", "东方中科"}),
    (("IP经济(谷子经济)",), {"中国电影", "横店影视", "广百股份", "凯撒文化", "儒意电影"}),
    (("东数西算(算力)",), {"华胜天成", "南威软件", "法狮龙", "维通利", "华孚时尚"}),
    (("风电",), {"兴业股份", "新能股份", "维通利", "国统股份", "日发精机"}),
    (("锂电池概念",), {"福龙马", "兴业股份", "岳阳兴长", "世龙实业"}),
    (("智能家居",), {"日盈电子", "法狮龙", "皮阿诺"}),
    (("物联网",), {"北纬科技", "南威软件", "皮阿诺"}),
    (("预制菜",), {"天邦食品", "好当家", "广百股份"}),
    (("光刻胶",), {"兴业股份", "兴欣新材"}),
]

EXPECTED_SECTORS = {
    "飞乐音响": ("新能源汽车",),
    "福达股份": ("新能源汽车",),
    "日盈电子": ("新能源汽车",),
    "福龙马": ("新能源汽车",),
    "中马传动": ("新能源汽车",),
    "天普股份": ("新能源汽车",),
    "维通利": ("新能源汽车",),
    "日发精机": ("新能源汽车",),
    "东方中科": ("新能源汽车",),
    "美晨科技": ("新能源汽车",),
    "华胜天成": ("AI应用", "芯片概念"),
    "文投控股": ("AI应用", "文化传媒概念"),
    "中国电影": ("AI应用", "文化传媒概念"),
    "横店影视": ("AI应用", "文化传媒概念"),
    "南威软件": ("AI应用",),
    "凯撒文化": ("AI应用", "文化传媒概念"),
    "湖北广电": ("文化传媒概念",),
    "儒意电影": ("文化传媒概念",),
    "金逸影视": ("文化传媒概念",),
    "幸福蓝海": ("文化传媒概念",),
    "金辰股份": ("芯片概念",),
    "兴业股份": ("芯片概念",),
    "北纬科技": ("芯片概念",),
    "华东重机": ("芯片概念",),
    "天邦食品": ("机器人概念",),
    "金新农": ("机器人概念",),
    "通化金马": ("DeepSeek概念",),
    "华孚时尚": ("DeepSeek概念",),
    "法狮龙": ("东数西算(算力)",),
    "广百股份": ("IP经济(谷子经济)",),
    "新能股份": ("风电",),
    "国统股份": ("风电",),
    "岳阳兴长": ("锂电池概念",),
    "世龙实业": ("锂电池概念",),
    "兴欣新材": ("光刻胶",),
    "好当家": ("预制菜",),
    "皮阿诺": ("智能家居", "物联网"),
}


def _board(code: str, name: str, l2: str, concepts: tuple[str, ...], l1: str = "行业甲", l3: str = "行业丙") -> StockBoard:
    return StockBoard(code=code, name=name, industry_l1=l1, industry_l2=l2, industry_l3=l3, concepts=concepts)


def _stock(market: str, code: str, name: str) -> PoolStock:
    return PoolStock(market=market, code=code, name=name)


class November13AcceptanceTest(unittest.TestCase):
    def test_groups_and_sectors_match_issue_24(self) -> None:
        boards = load_stock_boards()
        by_name = {board.name: board for board in boards.values()}
        pool = []
        for name in NAMES:
            board = by_name[name]
            number, suffix = board.code.split(".")
            pool.append(_stock(suffix.lower(), number, name))

        result = classify_limit_ups(pool, boards)
        got_groups = [(group.sectors, {member.name for member in group.members}) for group in result.groups]
        self.assertEqual(got_groups, [(sectors, names) for sectors, names in EXPECTED_GROUPS])
        got_sectors = {}
        for stock in pool:
            got_sectors[stock.name] = result.sectors_by_stock[(stock.market, stock.code)]
        self.assertEqual(got_sectors, EXPECTED_SECTORS)
        self.assertEqual(result.missing, ())


class SectorRuleTest(unittest.TestCase):
    def test_smaller_group_covered_by_a_larger_one_is_not_listed(self) -> None:
        boards = {
            "600001.SH": _board("600001.SH", "甲", "行业A", ("手机游戏", "网络游戏", "融资融券")),
            "600002.SH": _board("600002.SH", "乙", "行业B", ("网络游戏", "手机游戏", "沪股通")),
            "000001.SZ": _board("000001.SZ", "丙", "行业C", ("手机游戏",)),
        }
        result = classify_limit_ups(
            [_stock("sh", "600001", "甲"), _stock("sh", "600002", "乙"), _stock("sz", "000001", "丙")],
            boards,
        )
        self.assertEqual(result.groups[0].sectors, ("手机游戏",))
        self.assertEqual(result.sectors_by_stock[("sz", "000001")], ("手机游戏",))
        pair = [group for group in result.groups if group.size == 2]
        self.assertEqual(pair, [])
        self.assertEqual(result.sectors_by_stock[("sh", "600001")], ("手机游戏",))

    def test_same_members_keep_both_concepts(self) -> None:
        boards = {
            "600001.SH": _board("600001.SH", "甲", "行业A", ("手机游戏", "网络游戏")),
            "600002.SH": _board("600002.SH", "乙", "行业B", ("网络游戏", "手机游戏")),
        }
        result = classify_limit_ups(
            [_stock("sh", "600001", "甲"), _stock("sh", "600002", "乙")],
            boards,
        )
        self.assertEqual([group.sectors for group in result.groups], [("手机游戏", "网络游戏")])
        self.assertEqual(result.sectors_by_stock[("sh", "600001")], ("手机游戏", "网络游戏"))

    def test_pair_keeps_the_leftover_on_the_smaller_concept(self) -> None:
        boards = {
            "600001.SH": _board("600001.SH", "兴业", "化工", ("芯片概念", "光刻胶")),
            "600002.SH": _board("600002.SH", "甲", "设备", ("芯片概念",)),
            "600003.SH": _board("600003.SH", "乙", "设备", ("芯片概念",)),
            "600004.SH": _board("600004.SH", "丙", "设备", ("芯片概念",)),
            "000001.SZ": _board("000001.SZ", "兴欣", "化学制品", ("光刻胶", "净水概念", "碳中和")),
        }
        result = classify_limit_ups(
            [
                _stock("sh", "600001", "兴业"),
                _stock("sh", "600002", "甲"),
                _stock("sh", "600003", "乙"),
                _stock("sh", "600004", "丙"),
                _stock("sz", "000001", "兴欣"),
            ],
            boards,
        )
        self.assertEqual([group.sectors for group in result.groups], [("芯片概念",), ("光刻胶",)])
        self.assertEqual(result.sectors_by_stock[("sh", "600001")], ("芯片概念",))
        self.assertEqual(result.sectors_by_stock[("sz", "000001")], ("光刻胶",))

    def test_solo_concepts_are_written_when_the_stock_has_no_larger_group(self) -> None:
        boards = {
            "000001.SZ": _board("000001.SZ", "兴欣", "化学制品", ("净水概念", "碳中和")),
        }
        result = classify_limit_ups([_stock("sz", "000001", "兴欣")], boards)
        self.assertEqual([group.sectors for group in result.groups], [("净水概念",), ("碳中和",)])
        self.assertEqual(result.sectors_by_stock[("sz", "000001")], ("净水概念", "碳中和"))

    def test_size_three_keeps_the_leftover_on_the_smaller_concept(self) -> None:
        boards = {
            "600001.SH": _board("600001.SH", "天邦", "养殖业", ("机器人概念", "预制菜")),
            "600002.SH": _board("600002.SH", "甲", "设备", ("机器人概念",)),
            "600003.SH": _board("600003.SH", "乙", "设备", ("机器人概念",)),
            "600004.SH": _board("600004.SH", "丙", "设备", ("机器人概念",)),
            "600005.SH": _board("600005.SH", "广百", "零售", ("IP经济(谷子经济)", "预制菜")),
            "600006.SH": _board("600006.SH", "丁", "传媒", ("IP经济(谷子经济)",)),
            "600007.SH": _board("600007.SH", "戊", "传媒", ("IP经济(谷子经济)",)),
            "600008.SH": _board("600008.SH", "己", "传媒", ("IP经济(谷子经济)",)),
            "600009.SH": _board("600009.SH", "好当家", "养殖业", ("预制菜", "乡村振兴")),
        }
        result = classify_limit_ups(
            [_stock("sh", f"60000{i}", name) for i, name in enumerate(
                ["", "天邦", "甲", "乙", "丙", "广百", "丁", "戊", "己", "好当家"], start=0
            ) if name],
            boards,
        )
        labels = [group.sectors for group in result.groups]
        self.assertEqual(labels, [("IP经济(谷子经济)",), ("机器人概念",), ("预制菜",)])
        self.assertEqual(result.sectors_by_stock[("sh", "600009")], ("预制菜",))

    def test_missing_code_is_reported_and_does_not_fail_the_group(self) -> None:
        boards = {
            "600001.SH": _board("600001.SH", "甲", "行业A", ("文化传媒概念",)),
            "600002.SH": _board("600002.SH", "乙", "行业B", ("文化传媒概念",)),
        }
        result = classify_limit_ups(
            [
                _stock("sh", "600001", "甲"),
                _stock("sh", "600002", "乙"),
                _stock("sz", "000000", "缺字典"),
            ],
            boards,
        )
        self.assertEqual(result.groups[0].sectors, ("文化传媒概念",))
        self.assertEqual(result.sectors_by_stock[("sz", "000000")], ())
        self.assertEqual([stock.name for stock in result.missing], ["缺字典"])

    def test_broad_tag_and_own_industry_do_not_form_a_group(self) -> None:
        boards = {
            "600001.SH": _board("600001.SH", "甲", "汽车零部件", ("融资融券", "汽车零部件")),
            "600002.SH": _board("600002.SH", "乙", "汽车零部件", ("融资融券", "汽车零部件")),
        }
        result = classify_limit_ups(
            [_stock("sh", "600001", "甲"), _stock("sh", "600002", "乙")],
            boards,
        )
        self.assertEqual(result.groups, ())
        self.assertEqual(result.sectors_by_stock[("sh", "600001")], ("汽车零部件",))

    def test_tied_groups_are_both_written_in_unicode_order(self) -> None:
        boards = {
            "600001.SH": _board("600001.SH", "甲", "服务", ("AI应用", "芯片概念")),
            "600002.SH": _board("600002.SH", "乙", "服务", ("AI应用",)),
            "600003.SH": _board("600003.SH", "丙", "服务", ("AI应用",)),
            "600004.SH": _board("600004.SH", "丁", "服务", ("AI应用",)),
            "000001.SZ": _board("000001.SZ", "戊", "软件", ("芯片概念",)),
            "000002.SZ": _board("000002.SZ", "己", "软件", ("芯片概念",)),
            "000003.SZ": _board("000003.SZ", "庚", "软件", ("芯片概念",)),
        }
        result = classify_limit_ups(
            [
                _stock("sh", "600001", "甲"),
                _stock("sh", "600002", "乙"),
                _stock("sh", "600003", "丙"),
                _stock("sh", "600004", "丁"),
                _stock("sz", "000001", "戊"),
                _stock("sz", "000002", "己"),
                _stock("sz", "000003", "庚"),
            ],
            boards,
        )
        self.assertEqual(result.sectors_by_stock[("sh", "600001")], ("AI应用", "芯片概念"))
        self.assertEqual(result.sectors_by_stock[("sh", "600002")], ("AI应用",))


if __name__ == "__main__":
    unittest.main()
