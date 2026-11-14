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

封单、成交额、题材这类市场事实归复盘 skill 的事件字段。排序和过滤规则归本 skill，就是本文件的「选股规则」一节。

## 日期规则

跟随复盘 skill：未指定日期时取最近一个已收盘交易日，用复盘 skill 的 `assets/trading_calendar.json` 判断交易日。用户说「今天」「今日」的口径同复盘 skill：当前为交易日且已过 15:00（Asia/Shanghai）→ 当日；否则回退最近一个已收盘交易日。

用户显式给出日历日期时按该日期调用 `get`。不是交易日或库里没有记录时，说明「库内无记录」并停止，不要改写成最近交易日，也不要自己去抓行情再筛选。

## 读库失败

`get` 未成功（`DB_UNAVAILABLE`、`CONFIG_MISSING`、`REMOTE_FORBIDDEN`、`REMOTE_UNAVAILABLE` 等）时：

- 明示数据库状态为未知 / 不可用，给出脱敏后的错误码与 `message`。
- 不要根据失败推断库内有没有数据，不要改成自己抓行情，停止本次选股。
- 按复盘 skill 的「读库失败」一节定位错误原因。

## 候选池

只取 `get` 返回的 `ladder.groups` 里的股票：`direction=up`、`closed_at_limit=true`、`streak_height>=1` 的收盘涨停。炸板（`broken_limit_up`）、打开跌停和收盘跌停都不参与本 skill 的任何归类、排序和筛选。

`ladder.groups` 为空时：说明库内无收盘涨停事件（或当日无记录），如实说明并停止，不要渲染成全市场零涨停。

## 选股规则

### 1. 题材归类

- 按涨停原因（`limit_up_reasons`）**原文**归类题材。不自动合并近义词，不自动推断板块层级，不用 `sectors` 替代。
- 一只股票有多个涨停原因时，分别计入每个原文对应的题材；同一股票在同一题材内只计一次。
- `limit_up_reasons` 为空的股票不参与题材归类和强势板块排序，但仍参与总龙头和一排 / 二排的判定。

**强势板块排序**（只对收盘涨停计数），排序键依次为：

1. 涨停家数（题材内收盘涨停股票数），多者优先；
2. 板块内最高连板（最高 `streak_height`），高者优先；
3. 板块内最早涨停时间（板块内最小的 `first_limit_time`），早者优先；`first_limit_time` 为 `null` 的股票不参与比较；板块内全部缺失时该键视为缺失，排在有值板块之后；
4. 封单额合计（板块内 `seal_amount` 求和），大者优先；合计只统计有值个股，缺值个股不补 `0`；板块内全部缺失时合计留空，排在有合计值板块之后。

取前 3 为强势板块。

### 2. 龙头（三类，分别列出）

并列排序键统一为：首次涨停时间（`first_limit_time`，早者优先）→ 封成比（`seal_ratio`，大者优先）→ 封单额（`seal_amount`，大者优先）。排序键为 `null` 时排在有值之后；全部缺失时无法分出先后，如实标注「数据缺失，无法判定先后」。

- **总龙头**：全市场（候选池内）最高 `streak_height`，单独列出。并列时按上述排序键取首位为总龙头，其余并列股在命中依据里列明。
- **板块龙头**：每个强势板块内最高 `streak_height` 的股票；并列时按同一套排序键取首位。
- **日内龙头**：每个强势板块内 `first_limit_time` 最早的股票。板块内全部缺失 `first_limit_time` 时标注「数据缺失，无法判定」，不得用其他字段代替推断。

龙头判定只排序、不改写复盘库里的 `is_leader` 字段；`is_leader` 是复盘事实，不是本 skill 的判定结果。

### 3. 一排 / 二排（候选名单）

只对首板（`streak_height=1`）和二板（`streak_height=2`）分类：

- **一排**：同时满足以下三项——
  - 收盘价**严格 < 30 元**（`close_price < 30`）；
  - 个股流通市值**严格 < 100 亿**（`stock_float_market_cap < 10_000_000_000` 元）；
  - 涨停限幅 10%（`limit_rate_bp = 1000`）。
- **二排**：其余首板 / 二板（含走趋势股），上述条件放开。

一排的三项条件必须全部**确认满足**。任一项为 `null` 时不得估算，该股票不进一排，归入二排，并在命中依据里如实标注缺失字段。

### 4. 输出

三张表：**强势板块**、**龙头**（总龙头 / 板块龙头 / 日内龙头）、**一排 / 二排**。每行给出命中依据，写明引用的字段值：

- 强势板块表：题材原文、涨停家数、最高连板、最早涨停时间、封单额合计，以及排序依据。
- 龙头表：类别、所属题材（总龙头除外）、股票、连板高度，以及并列排序用到的字段值。
- 一排 / 二排表：股票、连板高度、收盘价、个股流通市值、`limit_rate_bp`，以及命中一排的三项条件值；归入二排的写明原因（哪一项不满足或哪个字段缺失）。

空值规则：

- 筛选和排序遇到 `null` 一律按「数据缺失」如实标注，不得估算、不得补 `0`。
- 五个新键（`seal_amount`、`seal_ratio`、`first_limit_time`、`close_price`、`stock_float_market_cap`）依赖云端迁移 `0006_limit_up_strength.sql`。未部署前读取结果为 `null`，全部按数据缺失处理；不要因此改用其他来源补齐。

展示口径（与复盘 skill 一致）：

- `seal_ratio` 读取结果为小数，展示为百分数（`0.0207` → `2.07%`）。
- `first_limit_time` 展示为 `HH:MM:SS`。跌停方向无此字段，本 skill 也不取跌停事件。
- 收盘价保留两位小数；封单额展示为万元或亿元；个股流通市值展示为亿元。

## 边界

- 与 `daily-market-review` 是两个 skill。本 skill 不采集、不修订复盘账本
- 只读。禁止调用 `save-review`、`save-events`、`save-event-details`、`delete-event`、`replace-direction`、`sync`
- 复盘库里没有目标日期的记录时，说明账本里没有这一天，不要改成自己去抓行情再筛选
- 不输出买入、卖出、仓位或止损指令；只给候选名单和命中依据
- 选股结果只出现在当次回复里，不写库、不落盘
