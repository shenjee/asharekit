# Changelog

## 0.7.0

收盘涨停的所属板块改由静态板块字典计算，不再写入东财 `hybk`：

- `save-events` 在事件落库后，对当日已保存的收盘涨停按 `assets/stock_boards.csv` 圈组求交，把结论写回 `sectors`。炸板、跌停不参与。东财股池仍只补封单额、首次涨停时间、收盘价、个股流通市值和成交额；
- 去掉宽标，以及与该股自身同花顺一、二、三级行业同名的概念后，每个剩余概念把含有它的收盘涨停收成一组，1 只也可以成组。2 只及以上求交，交集里的词全部保留；单独成组只写这一个概念。全部成员已被更大组覆盖的组不单列。去掉已进入更大组的成员后，只剩 1 只也仍单列；
- 一只股票落在多组时，只保留人数最多的那组；人数并列则这些组都写入。只有 1 只的概念若该票已进入更大组，仍只写更大组。排除后没有可写概念的，才写入该股同花顺二级行业。字典没有的代码 `sectors` 留空，并在结果 `missing` 里列出；
- 历史日期和只出结果不写库用 `classify-sectors`（`--dry-run`）。`enrich-events` 不再写 `sectors`。

无数据库迁移：仍写入既有 `daily_price_limit_event_sector`。

## 0.6.0

新增 `enrich-events` 命令与东方财富股池数据源（`sources/eastmoney.py`，stdlib urllib，无第三方依赖）：

- `save-events` 在事件落库后自动用东方财富涨停/炸板股池（push2ex `getTopicZTPool` / `getTopicZBPool`）补齐当日向上事件的 `seal_amount`、`first_limit_time`、`close_price`、`stock_float_market_cap`、`turnover_amount` 和 `sectors`（东财行业标签 hybk，原文入库——接口自身可能截断长标签，如「房地产开发」→「房地产开」，按原文保存不修补）。拉源失败报 `SOURCE_UNAVAILABLE`，已写入的事件不回滚；
- `enrich-events` 留给历史回填和 `--dry-run`（只出补缺报告不写库）；
- **只补缺、不覆盖**：字段已有值或 `sectors` 非空（人工优先）时跳过；市场标志不一致的匹配拒绝写入并报告；
- 只处理 `direction=up` 的收盘涨停和炸板。跌停不补缺，也不进未匹配；
- 连板数对账（东财 `lbc` vs 账本 `streak_height`）只报告、不改账；未匹配的向上事件逐条列出；
- **不写 `limit_up_reasons`**：东财池没有涨停原因字段，原因文字维持人工喂入。

无数据库迁移：复用 0006 的明细列与既有 `daily_price_limit_event_sector` 多值表。

## 0.5.0

涨停事件明细新增五个键（`daily_price_limit_event_detail` 加四个可空列，`seal_ratio` 不入库、只出现在读取结果与云端 `detail_row_json` 中）：

| 键 | 含义 | 口径 |
| --- | --- | --- |
| `seal_amount` | 封单额 | 元，有限非负，来源原值 |
| `seal_ratio` | 封成比 | 读取派生字段，`seal_amount ÷ turnover_amount`，不入库；读取结果为小数（`2.07%` → `0.0207`）；缺任一端或成交额为 `0` 时为 `null`，不接受直接写入 |
| `first_limit_time` | 首次涨停时间 | Asia/Shanghai，保存为 `HH:MM:SS`，范围 `09:25:00`–`15:00:00`，只允许 `direction=up`；方向改为跌停时清空 |
| `close_price` | 收盘价 | 元/股，有限且大于 0 |
| `stock_float_market_cap` | 个股流通市值 | 元，有限且大于 0；不是总体复盘的 `float_market_cap` |

迁移 `0006_limit_up_strength.sql` 增加四个可空列并替换明细读写函数（`detail_row_json` 中的 `seal_ratio` 按公式实时计算），`json_limit_time` 使用 `CREATE OR REPLACE FUNCTION` 便于重复执行。已有明细保持空值，不回填历史。**部署该迁移后才能写入其余四项（`seal_ratio` 是读取派生字段，任何情况下都不写入）；未部署前读取云端旧 `detail_row_json`（缺这五个键）一律按 `null` 处理，不会失败。** 部署步骤（SQL Editor / psql 二选一）见 README「从 0.4.x 升级到 0.5.0」。

## 0.4.3

中位数涨跌幅按证券软件已展示的两位百分数入库，小数固定四位（`0.11%` → `0.0011`，半分远离零）。本地保存、同步上传，以及云端 `patch_review_fields` / `insert_sync_review` 都先取整，不再把原始浮点写入。

迁移 `0005_median_change_pct_scale.sql` 只替换写入函数，不改已经入库的长小数。已有项目部署该迁移后，历史长小数需要再保存一次，或另行按四位四舍五入更新。

## 0.4.2

连板连续性口径修正：停牌不中断连板，停牌日无成交不计入高度，复牌后收盘涨停在停牌前最后一个涨停交易日高度上加一。纯口径文档修正，无存储与代码变化。

## 0.4.1

回头波数统计口径修正：判定公式分母由收盘价改为最高价（`(收盘价 - 最高价) ÷ 最高价 <= -10%`，含恰好回落 10% 的个股）。纯口径文档修正，无存储与代码变化。

## 0.4.0

默认使用 Supabase 云端账本，显式 SQLite 仍可用。支持旧库上传合并、云端完整下载，以及 PostgreSQL 备份与空白库恢复核验。
