# Changelog

## 0.1.0

落盘连板选股规则，替换 0.0.1 的占位行为（被问到选股时不再只回答「规则尚未发布」）：

- **题材归类**：按涨停原因（`limit_up_reasons`）原文归类，不合并近义词、不推断板块层级；强势板块按涨停家数 → 板块内最高连板 → 板块内最早涨停时间 → 封单额合计排序，取前 3
- **龙头**：总龙头（全市场最高连板）、板块龙头（强势板块内最高连板）、日内龙头（强势板块内最早涨停）分别列出；并列按首次涨停时间 → 封成比 → 封单额排序
- **一排 / 二排**：一排为首板或二板且收盘价严格 < 30 元、个股流通市值严格 < 100 亿、`limit_rate_bp` = 1000；二排为三项判定字段都有值、但确认不满足一排的首板 / 二板。判定字段为 `null` 的股票不进任何一排，列入 `unclassified_rows`；当天首板和二板都无法判定时，两排留空，`unclassifiable_rows` 按实际缺失字段和只数说明；候选池没有首板或二板时为 `no_row_candidates`
- **输出**：强势板块、龙头、一排 / 二排三张表，每行给命中依据和 `market`、`code`；空值一律按「数据缺失」如实标注
- **空结果**：显式日期先判断交易日，不是交易日直接说明。`get` 之后由 `scripts/cli.py pick` 区分「库内无记录」和「库内无收盘涨停事件」
- **并列**：龙头在首次涨停时间、封成比、封单额之后用 `market`、`code` 决定一只。三个业务键都缺失时，命中依据写明「均缺失；按 market/code 顺序展示」，不写成按缺失字段比较。强势板块不足 3 个则全部列出；四个排序键都相同时按题材原文的 Unicode 码位取前 3。板块内没有任何首次涨停时间时，日内龙头为「数据缺失，无法判定」
- **可执行口径**：`scripts/streakpicker/pick.py`，夹具和测试在 `tests/`

`seal_amount`、`seal_ratio`、`first_limit_time`、`close_price`、`stock_float_market_cap` 只使用 `get` 读到的值。值为 `null` 时按数据缺失处理，不区分数据存放在哪里。本 skill 仍只读复盘 CLI，不写库，不输出买卖指令。

**发布方式**：asharekit 改为整包发布，本 skill 不再单独出 `streak-picker-vX.Y.Z.zip`，随套件版本包 `asharekit-vX.Y.Z.zip` 一起发布。`daily-market-review` 由同级目录定位（`../daily-market-review`），删除 `MARKETREVIEW_SKILL_DIR` 和 `~/.codex`、`~/.cursor` 的查找链；同级目录找不到即报「找不到已安装的 daily-market-review」并停止。skill 文档里的版本号保留为口径记录，发布与安装以套件版本为准。

## 0.0.1

占位版。只确定与 `daily-market-review` 的边界（只读 `get`，禁止保存命令，不写买卖指令），选股规则未发布。
