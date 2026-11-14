---
name: streak-picker
description: "A股连板选股。用户要求从连板或每日梯队里筛选、排序、挑出候选、整理关注名单，或问强势板块、题材、总龙头、板块龙头、日内龙头、一排二排时使用。只读 daily-market-review 已保存的复盘结果。保存、补齐、修正或查看市场复盘时不使用本 skill。"
metadata:
  author: stock-pilot
  version: 0.1.0
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

用户要求连板选股、筛选候选、整理关注名单，或问强势板块、题材归类、总龙头、板块龙头、日内龙头、一排、二排时，按本文件执行。

保存、补齐、修正或查看市场复盘、涨跌停名单、每日梯队时，改用 `daily-market-review`。查看梯队是复盘 skill 的读取，不是选股。

## 数据

只读复盘 skill 的 JSON CLI。先取得复盘 skill 目录的绝对路径，替换下面的 `<review-skill-dir>`：

```bash
python3 "<review-skill-dir>/scripts/cli.py" get --date 2026-08-21
```

目录按这个顺序查找已安装的复盘版本包，找到第一个含 `scripts/cli.py` 的路径后停止：

```text
MARKETREVIEW_SKILL_DIR
> ~/.codex/skills/daily-market-review
> ~/.cursor/skills/daily-market-review
```

这三处都是安装位置。不要改用源码仓库里的 `skills/daily-market-review/`。三处都不存在时，说明找不到已安装的 `daily-market-review`，不要改去打开 `~/.marketreview/market_review.sqlite3`，也不要 import `marketreview`。

`get` 的输出格式、交易日和展示口径以复盘 skill 的 `SKILL.md` 为准。本 skill 不保存自己的账本。候选和命中依据只出现在当次回复里，不写入 `market_review` 的表。

封单、成交额、题材这类市场事实归复盘 skill 的事件字段。排序和过滤的可执行口径是本 skill 的 `scripts/streakpicker/pick.py`。本文件说明触发、展示和边界。计算以 `pick` 的输出为准，不要在回复里重算、改排序或增删候选。

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

`get` 成功之后先看 `pick` 的 `status`，三种空结果分开说：

| `status` | 条件 | 回复 |
| --- | --- | --- |
| `no_record` | `review` 为 `null` 且 `events` 为空 | 库内无记录。停止 |
| `no_closed_limit_up` | `ladder.groups` 为空，但 `review` 已有记录，或 `events` 非空 | 库内无收盘涨停事件。停止 |
| `unclassifiable_rows` | 候选池非空，但首板和二板里没有一只三项判定字段都有值 | 一排和二排留空，说明 `message`。强势板块和龙头照常输出 |
| `ok` | 候选池非空，且至少有一只首板或二板可以判定 | 按输出规则渲染三张表；`unclassified_rows` 里的股票单独列出 |

`no_closed_limit_up` 只说明库内没有收盘涨停事件。有炸板或跌停事件时仍然用这一句。

## 选股规则

### 1. 题材归类

- 按涨停原因（`limit_up_reasons`）**原文**归类题材。不自动合并近义词，不自动推断板块层级，不用 `sectors` 替代。
- 一只股票有多个涨停原因时，分别计入每个原文对应的题材；同一股票在同一题材内只计一次。
- `limit_up_reasons` 为空的股票不参与题材归类和强势板块排序，但仍参与总龙头和一排 / 二排的判定。

**强势板块排序**（只对收盘涨停计数），排序键依次为：

1. 涨停家数（题材内收盘涨停股票数），多者优先；
2. 板块内最高连板（最高 `streak_height`），高者优先；
3. 板块内最早涨停时间（板块内最小的 `first_limit_time`），早者优先；`first_limit_time` 为 `null` 的股票不参与比较；板块内全部缺失时该键视为缺失，排在有值板块之后；
4. 封单额合计（板块内 `seal_amount` 求和），大者优先；合计只统计有值个股，缺值个股不补 `0`；板块内全部缺失时合计留空，排在有合计值板块之后；
5. 题材原文的 Unicode 码位升序。前四项都相同时用它决定谁进入前 3，保证切分稳定。

取前 3 为强势板块。不足 3 个则全部列出。

### 2. 龙头（三类，分别列出）

并列排序键统一为：首次涨停时间（`first_limit_time`，早者优先）→ 封成比（`seal_ratio`，大者优先）→ 封单额（`seal_amount`，大者优先）→ `market` 升序 → `code` 升序。前三个键为 `null` 时排在有值之后。三个业务键都缺失或都相同，仍用 `market`、`code` 决定一只，并在命中依据里列出其余同高度股票。`seal_ratio` 只用 `get` 已经给出的值，不在本 skill 里重算。

- **总龙头**：全市场（候选池内）最高 `streak_height`，单独列出。同高度的其余股票写入 `tied`，命中依据用 `basis`。
- **板块龙头**：每个强势板块内最高 `streak_height` 的股票，并列时用同一套排序键。
- **日内龙头**：每个强势板块内 `first_limit_time` 最早的股票。同一时刻再按封成比 → 封单额 → `market` → `code`。板块内全部缺失 `first_limit_time` 时不点名，`undetermined` 为 true，`basis` 为「数据缺失，无法判定」。这种情况下不用封成比、封单额或代码代替时间。

龙头判定只排序、不改写复盘库里的 `is_leader` 字段；`is_leader` 是复盘事实，不是本 skill 的判定结果。

### 3. 一排 / 二排（候选名单）

只对首板（`streak_height=1`）和二板（`streak_height=2`）分类：

- **一排**：同时满足以下三项——
  - 收盘价**严格 < 30 元**（`close_price < 30`）；
  - 个股流通市值**严格 < 100 亿**（`stock_float_market_cap < 10_000_000_000` 元）；
  - 涨停限幅 10%（`limit_rate_bp = 1000`）。
- **二排**：三项判定字段都有值、但确认不满足一排的首板 / 二板。收盘价、个股流通市值、涨停限幅都读得到，才谈得上「不满足」。
- **无法分排**：三项判定字段任一为 `null` 的首板 / 二板。不估算，不进一排，也不进二排，列入 `unclassified_rows`，并写明缺失字段。

首板和二板里一只都判定不了时，一排和二排都留空，`status` 为 `unclassifiable_rows`。这种情况下不逐行铺开，用 `message` 说明缺的是哪些字段、涉及多少只。只要有一只首板或二板能判定，`status` 仍为 `ok`；缺字段的那几只仍写在 `unclassified_rows` 里，方便回补复盘数据。

### 4. 输出

三张表：**强势板块**、**龙头**（总龙头 / 板块龙头 / 日内龙头）、**一排 / 二排**。行序用 `pick` 的数组顺序。点到股票的行都带 `market` 和 `code`，命中依据用该行的 `basis`：

- 强势板块表：题材原文、涨停家数、最高连板、最早涨停时间、封单额合计、`basis`。
- 龙头表：类别、所属题材（总龙头除外）、`market`、`code`、名称、连板高度、`basis`。`tied` 里的同高度股票也写出 `market` 和 `code`。日内龙头 `undetermined` 为 true 时，这一行只保留题材和 `basis`。
- 一排 / 二排表：`market`、`code`、名称、连板高度、收盘价、个股流通市值、`limit_rate_bp`、`basis`。归入二排时，`basis` 写明未满足的一排条件。`unclassified_rows` 单独列出，写出 `market`、`code` 和缺失字段；这些行不是二排，也不是「已确认不满足」。

空值规则：

- 筛选和排序遇到 `null` 一律按「数据缺失」如实标注，不得估算、不得补 `0`。
- `seal_amount`、`seal_ratio`、`first_limit_time`、`close_price`、`stock_float_market_cap` 只使用 `get` 读到的值。值为 `null` 时按数据缺失处理，不估算，不改用其他来源补齐。本 skill 不关心这些值存在 Supabase、SQLite 还是别处。

展示口径（与复盘 skill 一致）：

- `seal_ratio` 读取结果为小数，展示为百分数（`0.0207` → `2.07%`）。
- `first_limit_time` 展示为 `HH:MM:SS`。跌停方向无此字段，本 skill 也不取跌停事件。
- 收盘价保留两位小数；封单额展示为万元或亿元；个股流通市值展示为亿元。

## 边界

- 与 `daily-market-review` 是两个 skill。本 skill 不采集、不修订复盘账本
- 只读。禁止调用 `save-review`、`save-events`、`save-event-details`、`delete-event`、`replace-direction`、`sync`
- `pick` 返回 `no_record` 时说明「库内无记录」，不要改成自己去抓行情再筛选
- 不输出买入、卖出、仓位或止损指令；只给候选名单和命中依据
- 选股结果只出现在当次回复里，不写库、不落盘
