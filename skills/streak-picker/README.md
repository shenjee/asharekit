# 连板选股

当前版本：**0.1.0**。从 `daily-market-review` 已保存的连板里筛选、排序，并给出候选和命中依据。

## 本版会做什么

用户要求连板选股、筛选候选或整理关注名单时，按已定稿规则输出三张表：

- **强势板块**：按涨停原因（`limit_up_reasons`）原文归类题材，按涨停家数 → 板块内最高连板 → 板块内最早涨停时间 → 封单额合计排序，取前 3
- **龙头**：总龙头（全市场最高连板）、板块龙头（强势板块内最高连板）、日内龙头（强势板块内最早涨停），分别列出
- **一排 / 二排**：一排为首板或二板且收盘价 < 30 元、个股流通市值 < 100 亿、涨停限幅 10%（`limit_rate_bp` = 1000）；二排为其余首板 / 二板

每行给出命中依据，并带上 `market` 和 `code`。筛选和排序遇到 `null` 按「数据缺失」如实标注，不做估算。题材不足 3 个则全部列出。同高度的龙头用首次涨停时间、封成比、封单额，再用 `market`、`code` 决定一只。板块内完全没有首次涨停时间时，日内龙头记为「数据缺失，无法判定」。

计算由本 skill 的脚本完成，回复按它的输出渲染：

```bash
python3 "<review-skill-dir>/scripts/cli.py" get --date 2026-08-21 \
  | python3 "<skill-dir>/scripts/cli.py" pick --input -
```

`pick` 把空结果分成两种：`review` 为 `null` 且 `events` 为空时回复「库内无记录」；已经有复盘记录或事件、但没有收盘涨停时回复「库内无收盘涨停事件」。显式日期若不是交易日，在调用 `get` 之前回复「不是交易日」。不输出买卖指令，不写入复盘库，不调用复盘 skill 的保存命令。

一排和二排只收三项判定字段都有值的股票。字段缺失的首板或二板不进二排，列在 `unclassified_rows` 里，并写明缺的字段。当天首板和二板一只都判定不了时，两排留空，用一句话说明实际缺失的字段和只数，不逐行铺开；候选池里根本没有首板或二板时，说明「候选池内没有首板或二板」。

保存、补齐、修正或查看市场复盘时，使用 `daily-market-review`，不要使用本 skill。

## 和复盘 skill 的关系

本 skill 与 `daily-market-review` 并列，同在 asharekit 仓库的 `skills/` 下。它只读复盘结果：

```bash
python3 "<review-skill-dir>/scripts/cli.py" get --date 2026-08-21
```

`<review-skill-dir>` 是已经安装的复盘版本包，查找顺序：

1. `MARKETREVIEW_SKILL_DIR`
2. `~/.codex/skills/daily-market-review`
3. `~/.cursor/skills/daily-market-review`

这三处都是安装位置，不是源码仓库里的 `skills/daily-market-review/`。

本 skill 不 import `marketreview`，不直接打开 SQLite。选股结果不进入 `market_review` 的表。封单、成交额、题材这类市场事实归复盘 skill 的事件字段。排序和过滤规则归本 skill，见 `SKILL.md` 的「选股规则」一节。

## 读到的字段

一排 / 二排和龙头排序使用 `get` 结果里的 `seal_amount`、`seal_ratio`、`first_limit_time`、`close_price`、`stock_float_market_cap`。这些值从哪来由复盘 skill 决定。本 skill 不区分 Supabase、SQLite 或其他后端。读到 `null` 就按数据缺失处理，不估算，也不改用其他来源补齐。

## 安装

版本包命名为 `streak-picker-vX.Y.Z.zip`，发布在 [shenjee/asharekit 的 Releases](https://github.com/shenjee/asharekit/releases)。安装只使用这个版本包，解压后的目录才是 skill 目录。不要克隆源码仓库，也不要把源码目录放进 Agent 的 skill 目录。

本 skill 依赖已安装的 `daily-market-review` 版本包。选股前请确认复盘 skill 已安装且当日复盘已保存；库里没有记录时本 skill 只说明「库内无记录」，不会自己去抓行情。
