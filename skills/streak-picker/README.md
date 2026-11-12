# 连板选股

当前版本：**0.0.1**。从 `daily-market-review` 已保存的连板里筛选、排序，并给出候选和命中依据。

本版只确定边界。选股规则还没有写入本 skill，也没有 GitHub Release 版本包，所以还不能安装。不要把本目录放进 Agent 的 skill 目录。

## 本版会做什么

用户要求连板选股、筛选候选或整理关注名单时：

- 说明选股规则尚未发布
- 停止，不临时编造筛选标准
- 不写入复盘库，不调用复盘 skill 的保存命令
- 不给出买卖指令

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

本 skill 不 import `marketreview`，不直接打开 SQLite。选股结果不进入 `market_review` 的表。封单、成交额、题材这类市场事实归复盘 skill 的事件字段。排序和过滤规则归本 skill。

规则发布后，版本包将命名为 `streak-picker-vX.Y.Z.zip`。安装只使用这个版本包，解压后的目录才是 skill 目录。
