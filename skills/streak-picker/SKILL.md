---
name: streak-picker
description: "A股连板选股。用户要求从连板或每日梯队里筛选、排序、挑出候选、整理关注名单，或问强势板块、题材、总龙头、板块龙头、日内龙头、一排二排时使用。只读 daily-market-review 已保存的复盘结果。保存、补齐、修正或查看市场复盘时不使用本 skill。"
metadata:
  author: stock-pilot
  version: 0.4.1
  category: finance
  tags:
    - a-share
    - streak
    - limit-up
    - stock-picker
    - 连板选股
    - 连板
---

# 连板选股

从 `daily-market-review` 已保存的连板里筛选、排序，给出候选和命中依据。不写买卖指令。

## 触发场景

用户要求连板选股、筛选候选、整理关注名单，或问强势板块、题材（板块归类口径见选股规则）、总龙头、板块龙头、日内龙头、一排、二排时，按本文件执行。

保存、补齐、修正或查看市场复盘、涨跌停名单、每日梯队时，改用 `daily-market-review`。查看梯队是复盘 skill 的读取，不是选股。

## 数据

只读复盘 skill 的 JSON CLI。`<skill-dir>` 是本文件所在目录（`streak-picker` 的安装目录）：

```bash
python3 "<skill-dir>/../daily-market-review/scripts/cli.py" get --date 2026-08-21
```

本 skill 与 `daily-market-review` 同属 asharekit 套件，安装时放在同一个 skill 目录、互为同级目录。同级目录是唯一依据，不查其他位置，不用环境变量。同级目录里没有 `daily-market-review`（或没有 `scripts/cli.py`）时，说明套件没有完整安装：报告「找不到已安装的 daily-market-review，请重新安装 asharekit 套件版本包」，停止。不要改用源码仓库里的 `skills/daily-market-review/`，不要打开 `~/.marketreview/market_review.sqlite3`，也不要 import `marketreview`。

`get` 的输出格式、交易日和展示口径以复盘 skill 的 `SKILL.md` 为准。本 skill 不保存自己的账本。候选和命中依据只出现在当次回复里，不写入 `market_review` 的表。

封单、成交额、板块这类市场事实归复盘 skill 的事件字段。排序和过滤的可执行口径是本 skill 的 `scripts/streakpicker/pick.py`。本文件说明触发、展示和边界。计算以 `pick` 的输出为准，不要在回复里重算、改排序或增删候选。

`<skill-dir>` 是本文件所在目录。`get` 成功后，把同一次完整 JSON 交给：

```bash
python3 "<skill-dir>/scripts/cli.py" pick --input -
```

`pick` 只读这份 JSON，不访问数据库，也不调用复盘 skill 的写入命令。

## 日期规则

跟随复盘 skill：未指定日期时取最近一个已收盘交易日。用户说「今天」「今日」的口径同复盘 skill：当前为交易日且已过 15:00（Asia/Shanghai）→ 当日；否则回退最近一个已收盘交易日。交易日用已定位的复盘 skill 目录里的 `assets/trading_calendar.json` 判断：周六、周日，或该日期出现在对应年份的 `closed_dates` 里，都不是交易日。年份不在文件里时，说明交易日历没有这一年，停止。

用户显式给出日历日期时，先做上面的交易日判断。不是交易日：说明「不是交易日」，停止，不调用 `get`。是交易日时按该日期调用 `get`，再交给 `pick`。不要把非交易日的空结果说成库内无记录，也不要改写成最近交易日，也不要自己去抓行情再筛选。

## 读库失败

`get` 未成功（`DB_UNAVAILABLE`、`CONFIG_MISSING`、`REMOTE_FORBIDDEN`、`REMOTE_UNAVAILABLE` 等）时：

- 明示数据库状态为未知 / 不可用，给出脱敏后的错误码与 `message`。
- 不要根据失败推断库内有没有数据，不要改成自己抓行情，停止本次选股。
- 按复盘 skill 的「读库失败」一节定位错误原因。

## 候选池

`pick` 只取 `ladder.groups` 里的股票：`direction=up`、`closed_at_limit=true`、`streak_height>=1` 的收盘涨停。炸板（`broken_limit_up`）、打开跌停和收盘跌停都不参与归类、排序和筛选。

`get` 成功之后按 `pick` 的 `status` 分别处理：

| `status` | 条件 | 回复 |
| --- | --- | --- |
| `no_record` | `review` 为 `null` 且 `events` 为空 | 库内无记录。停止 |
| `no_closed_limit_up` | `ladder.groups` 为空，但 `review` 已有记录，或 `events` 非空 | 库内无收盘涨停事件。停止 |
| `no_row_candidates` | 候选池非空，但没有首板或二板（全部三板及以上） | 一排和二排留空，说明「候选池内没有首板或二板」。强势板块和龙头照常输出 |
| `unclassifiable_rows` | 有首板或二板，但每只都缺判定字段，一只都进不了两排 | 一排和二排留空。未归类最多列 3 只；回复按 `message` 说明缺的字段。强势板块和龙头照常输出 |
| `ok` | 候选池非空，且至少有一只首板或二板可以进两排 | 按短格式输出；`unclassified_rows` 有则最多列 3 只，没有则写 0 |

`no_closed_limit_up` 只说明库内没有收盘涨停事件。有炸板或跌停事件时仍然用这一句。

## 选股规则

### 1. 板块归类

- 按板块（`sectors`，东方财富行业标签 hybk 原文入库，长标签可能被数据源截断，按原文归类不修补）**原文**归类板块。不自动合并近义词，不自动推断板块层级，不用 `limit_up_reasons`（涨停原因）替代——涨停原因是数据商编辑归因产品，不参与自动归类。
- 一只股票有多个板块标签时，分别计入每个原文对应的板块；同一股票在同一板块内只计一次。
- `sectors` 为空的股票不参与板块归类和强势板块排序，但仍参与总龙头和一排 / 二排。
- 限幅不参与强势板块排序。封单额合计只表示板块热度，不表示板块里哪只股票更强。

**强势板块排序**（只对收盘涨停计数），排序键依次为：

1. 涨停家数（板块内收盘涨停股票数），多者优先；
2. 板块内最高连板（最高 `streak_height`），高者优先；
3. 板块内最早涨停时间（板块内最小的 `first_limit_time`），早者优先；`first_limit_time` 为 `null` 的股票不参与比较；板块内全部缺失时该键视为缺失，排在有值板块之后；
4. 封单额合计（板块内 `seal_amount` 求和），大者优先；合计只统计有值个股，缺值个股不补 `0`；板块内全部缺失时合计留空，排在有合计值板块之后；
5. 板块原文的 Unicode 码位升序。前四项都相同时用它决定谁进入前 3，保证切分稳定。

取前 3 为强势板块。不足 3 个则全部列出。

### 2. 龙头（三类，分别列出）

并列排序键统一为：首次涨停时间（`first_limit_time`，早者优先）→ 封成比（`seal_ratio`，大者优先）→ 封单额（`seal_amount`，大者优先）→ `market` 升序 → `code` 升序。前三个键为 `null` 时排在有值之后。三个业务键都缺失或都相同，仍用 `market`、`code` 决定一只，并在命中依据里列出其余同高度股票。三个业务键**都缺失**时，命中依据必须如实写明「首次涨停时间、封成比、封单额均缺失；按 market/code 顺序展示」，不得写成「按首次涨停时间、封成比、封单额……取本只」——那会误导读者以为缺失字段参与了比较。`seal_ratio` 只用 `get` 已经给出的值，不在本 skill 里重算。

- **总龙头**：全市场（候选池内）最高 `streak_height`，单独列出。同高度的其余股票写入 `tied`，命中依据用 `basis`。
- **板块龙头**：每个强势板块内最高 `streak_height` 的股票，并列时用同一套排序键。
- **日内龙头**：每个强势板块内 `first_limit_time` 最早的股票。同一时刻再按封成比 → 封单额 → `market` → `code`。板块内全部缺失 `first_limit_time` 时不点名，`undetermined` 为 true，`basis` 为「数据缺失，无法判定」。这种情况下不用封成比、封单额或代码代替时间。

龙头判定只排序、不改写复盘库里的 `is_leader` 字段；`is_leader` 是复盘事实，不是本 skill 的判定结果。高度和板块地位只表示市场身份，不是封锁强度。龙头排序不用 `seal_to_float_ratio`。

### 3. 个股封锁强度

全池用下面五键，不按市值分组，也不设全市场固定线。两个相对量打平之后才看绝对封单额。「接近」就是前两键打平，不另设百分比带宽。限幅不参与这五键。

1. 封成比 `seal_ratio`，高者优先。只用 `get` 已有值，含义仍是封单额 / 成交额。
2. `seal_to_float_ratio` = 封单额 / 流通市值，高者优先。使用时现算，不入库，不覆盖 `seal_ratio`。流通市值为 `null` 或 `0` 时，这个比值为 `null`。
3. 绝对封单额，大者优先。只在前两键打平时比较。
4. 首次涨停时间，早者优先。早启动不等于收盘仍强。
5. `market` 升序，然后 `code` 升序。

### 4. 一排 / 二排

只从首板（`streak_height=1`）和二板（`streak_height=2`）里选。三板及以上不进这两排。各输出最多 3 只。

判定字段为 `close_price`、`stock_float_market_cap`、`limit_rate_bp`、`seal_ratio`、`seal_amount`、`first_limit_time`。有一个为 `null`，或流通市值为 `0`，就进 `unclassified_rows`，不参与两排排序。`sectors` 为空不影响这两排。

- **一排**必须同时满足三道门槛：收盘价严格 < 30 元、个股流通市值严格 < 100 亿、`limit_rate_bp = 1000`（10cm）。收盘价等于 30 元，或流通市值等于 100 亿，都不进一排。过了这三道之后再排序：二板优先于首板，然后用第 3 节的五键，取前 3。10cm 不足 3 只时名额留空，20cm、30cm 不补进一排。
- **二排**：从没有进入一排的首板、二板里，只按第 3 节的五键再取最多 3 只。这里包括没过价格、市值或 10cm 的股票，也包括过了三道门槛但没有进入一排前 3 的 10cm。不与一排重复。二排只按封锁强度从剩余里取，不把「不满足一排」写成它的定义。

首板和二板一只都进不了两排时，`status` 为 `unclassifiable_rows`，两排留空，用 `message` 说明实际缺失的字段和只数。至少有一只能进两排时，`status` 为 `ok`。候选池里没有首板或二板时，`status` 为 `no_row_candidates`。

不要把「不是 10cm」或「不满足某项价格、市值门槛」写成二排。不要写「共 N 只，取前 3」。`pick` 不输出 `row1_total`、`row2_total`、`unclassified_total`。

### 5. 输出

对用户只出短格式，先给结论，顺序固定：

- 强势板块：板块原文、涨停家数、最高连板
- 总龙头
- 板块龙头
- 日内龙头：`undetermined` 为 true 时只写板块和「数据缺失，无法判定」
- 一排：最多 3 只，每只写 `market`、`code`、名称
- 二排：最多 3 只，每只写 `market`、`code`、名称
- 未归类：一只都没有就写 0；有则最多 3 只，写出 `market`、`code` 和缺失字段

龙头行写名称、`market`、`code`、连板高度。安装核对、补缺预演、口径说明、字段明细和代码不要跟这份名单写在同一段。需要解释某只为什么入选时另说。`basis` 留在 `pick` 的 JSON 里，不要塞进名单。

空值规则：

- `null` 不补 `0`、不估算。龙头并列时，缺值排在有值之后。
- `seal_amount`、`seal_ratio`、`first_limit_time`、`close_price`、`stock_float_market_cap` 只使用 `get` 读到的值。
- `seal_to_float_ratio` 只由封单额和流通市值现算。流通市值为 `null` 或 `0` 时为 `null`。

展示口径（与复盘 skill 一致）：

- `seal_ratio` 和 `seal_to_float_ratio` 都是小数，展示为百分数（`0.0207` → `2.07%`）。
- `first_limit_time` 展示为 `HH:MM:SS`。
- 封单额展示为万元或亿元；个股流通市值展示为亿元。

## 边界

- 与 `daily-market-review` 是两个 skill。本 skill 不采集、不修订复盘账本
- 只读。禁止调用 `save-review`、`save-events`、`save-event-details`、`delete-event`、`replace-direction`、`sync`
- `pick` 返回 `no_record` 时说明「库内无记录」，不要改成自己去抓行情再筛选
- 不输出买入、卖出、仓位或止损指令；只给候选名单和命中依据
- 选股结果只出现在当次回复里，不写库、不落盘
