---
name: streak-picker
description: "A股连板选股。用户要求从连板或每日梯队里筛选、排序、挑出候选或整理关注名单时使用。只读 daily-market-review 已保存的复盘结果。保存、补齐、修正或查看市场复盘时不使用本 skill。"
metadata:
  author: stock-pilot
  version: 0.0.1
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

## 本版范围

版本 **0.0.1** 只确定和复盘 skill 的边界。选股规则还没有发布。

用户要求选股、筛选或整理关注名单时：

1. 说明选股规则尚未发布。
2. 停止。不要临时编造筛选标准，不要把临时标准说成本 skill 的方法。
3. 不要写入复盘库，不要调用 `save-review`、`save-events`、`save-event-details`、`delete-event`、`replace-direction` 或 `sync`。

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

封单、成交额、题材这类市场事实归复盘 skill 的事件字段。排序和过滤规则归本 skill，放在本目录的 `references/`。规则尚未发布，所以现在还没有这个目录。

## 边界

- 与 `daily-market-review` 是两个 skill。本 skill 不采集、不修订复盘账本
- 复盘库里没有目标日期的记录时，说明账本里没有这一天，不要改成自己去抓行情再筛选
- 不输出买入、卖出、仓位或止损指令
