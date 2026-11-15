# 连板选股

当前版本：**0.4.1**（本 skill 的口径版本；发布与安装以 asharekit 套件版本为准）。从 `daily-market-review` 已保存的连板里筛选、排序，并给出候选和命中依据。

## 本版会做什么

用户要求连板选股、筛选候选或整理关注名单时，按已定稿规则输出短格式：

- **强势板块**：按板块（`sectors`，东方财富行业标签原文）归类，按涨停家数 → 板块内最高连板 → 板块内最早涨停时间 → 封单额合计排序，取前 3
- **龙头**：总龙头（全市场最高连板）、板块龙头（强势板块内最高连板）、日内龙头（强势板块内最早涨停），分别列出
- **一排 / 二排**：只从首板、二板里各选最多 3 只。一排必须同时满足收盘价严格 < 30 元、个股流通市值严格 < 100 亿、`limit_rate_bp = 1000`。过了这三道之后，二板优先于首板，再按封锁强度五键。10cm 不足 3 只时不拿 20cm / 30cm 补一排。二排从剩余股票里只按五键取 3 只，可以含没过价格、市值或 10cm 的股票，也可以含没进一排的 10cm。缺判定字段的进未归类

对用户只出短格式：强势板块、总龙头、板块龙头、日内龙头、一排 3 只、二排 3 只、未归类。未归类没有就写 0，有则最多 3 只。不要写「共 N 只，取前 3」。`null` 不补 0、不估算。板块不足 3 个则全部列出。同高度的龙头用首次涨停时间、封成比、封单额，再用 `market`、`code` 决定一只。板块内完全没有首次涨停时间时，日内龙头记为「数据缺失，无法判定」。

个股封锁强度的五键是：封成比（只读 `seal_ratio`，仍是封单额 / 成交额）→ `seal_to_float_ratio`（封单额 / 流通市值，现算，不覆盖 `seal_ratio`）→ 绝对封单额（只在前两键打平时）→ 首次涨停时间 → `market`、`code`。流通市值为空或为 0 时，`seal_to_float_ratio` 为 `null`。

计算由本 skill 的脚本完成，回复按它的输出渲染：

```bash
python3 "<skill-dir>/../daily-market-review/scripts/cli.py" get --date 2026-08-21 \
  | python3 "<skill-dir>/scripts/cli.py" pick --input -
```

`pick` 把空结果分成两种：`review` 为 `null` 且 `events` 为空时回复「库内无记录」；已经有复盘记录或事件、但没有收盘涨停时回复「库内无收盘涨停事件」。显式日期若不是交易日，在调用 `get` 之前回复「不是交易日」。不输出买卖指令，不写入复盘库，不调用复盘 skill 的保存命令。

一排和二排只收判定字段齐全的首板、二板。收盘价、流通市值、涨停限幅、`seal_ratio`、封单额、首次涨停时间有一个为 `null`，或流通市值为 0，就列在 `unclassified_rows` 里。当天这些股票一只都进不了两排时，两排留空，用一句话说明实际缺失的字段和只数；候选池里根本没有首板或二板时，说明「候选池内没有首板或二板」。

保存、补齐、修正或查看市场复盘时，使用 `daily-market-review`，不要使用本 skill。

## 和复盘 skill 的关系

本 skill 与 `daily-market-review` 同属 asharekit 套件，随同一个套件版本包发布，安装时在同一个 skill 目录下互为同级目录。它只读复盘结果：

```bash
python3 "<skill-dir>/../daily-market-review/scripts/cli.py" get --date 2026-08-21
```

`<skill-dir>` 是本 skill 的安装目录。同级目录是唯一依据，没有查找列表，也没有环境变量。同级目录里没有 `daily-market-review` 时说明套件没有完整安装，停止并提示重新安装套件版本包。源码仓库里的 `skills/daily-market-review/` 不是安装位置。

本 skill 不 import `marketreview`，不直接打开 SQLite。选股结果不进入 `market_review` 的表。封单、成交额、板块这类市场事实归复盘 skill 的事件字段。排序和过滤规则归本 skill，见 `SKILL.md` 的「选股规则」一节。`seal_to_float_ratio` 只在选股时现算，不写回 `seal_ratio`。

## 读到的字段

一排 / 二排使用 `get` 结果里的 `close_price`、`stock_float_market_cap`、`limit_rate_bp`、`seal_ratio`、`seal_amount`、`first_limit_time`。一排用收盘价、流通市值和 10cm 做门槛，再用二板优先和封锁强度排序。龙头排序使用 `first_limit_time`、`seal_ratio`、`seal_amount`。这些值从哪来由复盘 skill 决定。本 skill 不区分 Supabase、SQLite 或其他后端。读到 `null` 就按数据缺失处理，不估算，也不改用其他来源补齐。

## 安装

本 skill 不单独发布，随 asharekit 套件版本包 `asharekit-vX.Y.Z.zip` 一起发布在 [shenjee/asharekit 的 Releases](https://github.com/shenjee/asharekit/releases)。安装步骤见[仓库根 README](../../README.md)。解压后把 `daily-market-review/` 与 `streak-picker/` 一起放入 Agent 的 skill 目录，保持同级。不要克隆源码仓库，也不要把源码目录放进 Agent 的 skill 目录。

本 skill 依赖同级目录里的 `daily-market-review`。选股前请确认当日复盘已保存；库里没有记录时本 skill 只说明「库内无记录」，不会自己去抓行情。
