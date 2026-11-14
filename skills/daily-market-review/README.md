# Daily Market Review

当前版本：**0.5.0**（本 skill 的口径版本；发布与安装以 asharekit 套件版本为准）。每日资本市场总体复盘 Skill，用于整理、保存和查看指定交易日的市场复盘数据。

## 功能

- 整理、补充和修正市场宽度、指数、成交额、市值、估值及两融等复盘字段
- 保存涨停、跌停、炸板和连板事件
- 保存事件扩展信息，并按连板高度生成每日梯队视图
- 读取已保存的数据并生成统计摘要
- 多个 Agent / 电脑连接同一 Supabase 项目时共享同一份云端账本

本 Skill 只提供数据整理与复盘，不提供买卖建议。连板选股在同仓库的 `streak-picker`。

## 系统要求

- Python 3.11 或更高版本
- 支持本地 Skill 的 Agent
- 默认云端模式：可访问已部署本项目迁移的 Supabase 项目，并配置 URL 与 Secret
- 云端备份、恢复和核验：额外安装兼容目标 PostgreSQL 版本的客户端工具 `pg_dump`、`psql`，并准备数据库管理连接与密码（日常查询不需要这些工具）

运行仅使用 Python 标准库，无需安装第三方 Python 依赖。

## 安装

只安装 GitHub Release 上的版本包。不要克隆源码仓库，也不要把源码目录放进 Agent 的 skill 目录。安装完成后不需要保存源码仓库。

本 skill 属于 asharekit 套件，随套件版本包 `asharekit-vX.Y.Z.zip` 一起发布在 [shenjee/asharekit 的 Releases](https://github.com/shenjee/asharekit/releases)。套件整包安装：解压后把包内所有 skill 目录一起放入 Agent 的 skill 目录，保持同级——同套件的 `streak-picker` 靠同级目录找到本 skill。

不同 Agent 需要分别安装一份 Skill。云端模式是否共享取决于是否连接同一 Supabase 项目，与 `MARKETREVIEW_HOME` 无关；正式与测试账本应连接不同项目。本地 SQLite 模式只有解析到同一数据库文件时才共享；`MARKETREVIEW_HOME` 改变本地目录，`--db` 可覆盖该路径。

### 让 Agent 安装

把 Release 里的套件版本包交给 Agent，或让它从 Releases 下载后再安装。例如：

- 「请从 https://github.com/shenjee/asharekit/releases 安装最新的 asharekit 套件版本包，不要克隆源码仓库。」
- 「帮我安装 asharekit 套件的发布包」

安装完成后，先完成下文「云端配置模板」和「云端初始化」，或明确配置 `backend=sqlite` 使用本地模式，再开始使用。

### 手动安装

1. 打开项目的 [Releases 页面](https://github.com/shenjee/asharekit/releases)，下载最新的套件版本包 `asharekit-vX.Y.Z.zip`。请勿下载 GitHub 自动生成的 `Source code (zip)`。
2. 解压，得到并排的 skill 目录（含 `daily-market-review/`）。
3. 把这些目录一起放入所使用 Agent 的 Skill 目录，保持同级。

各 Agent 的 Skill 目录位置请参考其官方文档。安装完成后，重启或刷新 Agent，使其加载新 Skill；首次使用前仍须完成云端配置与初始化，或明确选择本地模式。

> **注意：** 请安装发布版本包，不要下载源码仓库。版本包仅包含运行所需文件，不含测试和开发内容。

## 使用

完成安装和后端配置后，可向 Agent 提出请求，例如：

- “保存 2026-08-21 的市场复盘数据”
- “补充今天的涨停和连板名单”
- “把这张截图里的复盘数据提取并保存”
- “查看 2026-08-21 的市场复盘”
- “查看今天的每日梯队”

写入时，Skill 可以根据用户提供的文字、图片、网页或 API 数据完成整理和校验。查看已保存数据时不会再去抓外部行情，也不会因为查看而改账。日常账本在 Supabase 上，所以这次读取要访问该项目；这和「不抓行情网站」是两件事。选择 SQLite 后端（`--backend sqlite` 或配置 `backend=sqlite`）时读取本地文件，不访问云端；禁止联网时不得调用默认云端读取，也不得未说明就改读本地副本。

## 当前限制

- 只允许写入已经收盘的 A 股交易日。
- 内置交易日历仅覆盖 **2025–2026 年**；使用 2027 年及以后或 2025 年以前的日期前，须先更新 `assets/trading_calendar.json` 中的交易日历数据，或安装已包含对应年份日历的新版本。
- 仅本地 SQLite：打开已有数据库时，会通过 `CREATE TABLE IF NOT EXISTS` 自动补齐新增表，不改写已有用户数据。涉及已有列变化的升级仍会在版本说明中单独说明；升级前建议备份用户数据。

## 用户数据

默认权威账本在 Supabase；明确选择 SQLite 时，以所选本地库为账本。Agent / 电脑通过各自配置中的 `supabase_url` 选择项目；指向同一项目才共享云端数据。默认配置位置为 `~/.marketreview/supabase.config`，`MARKETREVIEW_CONFIG_DIR` 可指定独立配置目录（其内仍需配置不同项目才能隔离云端数据）。Skill 安装目录只存放程序和内置资源，配置与 Secret 默认在 `~/.marketreview/`（也可由上述配置目录覆盖），升级或移除 Skill 不应删除用户配置与数据目录。

本地文件：

```text
~/.marketreview/market_review.sqlite3
```

这是可选本地库，在选择 SQLite 后端（命令行或配置）或 `sync` 指定来源/目标时使用；在云端模式下不保证它是最新副本。`MARKETREVIEW_HOME` 只改这份本地文件的目录，不选择后端。不要让多个用户账户共用同一个数据目录。

如需更改本地副本目录，可在启动 Agent 前设置 `MARKETREVIEW_HOME`：

```bash
export MARKETREVIEW_HOME="/path/to/marketreview-data"
```

本地库应定期做 SQLite 一致性备份；备份该目录不能代替云端 PostgreSQL 备份。

### 云端配置模板（默认模式必需）

日常默认后端是 Supabase。未写 `backend` 时用代码默认值 `supabase`。`~/.marketreview/supabase.config` 里的 `backend` 优先于代码默认值，所以两机都要写成 `supabase`，不能只改代码开关。缺 URL 或 Secret、鉴权失败或断网会报错停止，不会自动打开 SQLite。`--backend sqlite` 选择本地库，读和写都会落到该文件；它不是只读开关。`--db` 不能代替这个选择。

若本机尚无配置文件，CLI 在需要云端配置时会自动从 Skill 安装目录复制模板到 `~/.marketreview/`（已有文件不覆盖），并提示自行填写。也可手工复制。填好的文件只留在本机，不要提交 Git、打进发布包，或贴到对话 / 日志 / Issue。

```bash
mkdir -p ~/.marketreview
[ -e ~/.marketreview/supabase.config ] || cp "<skill-dir>/config/supabase.config.example" ~/.marketreview/supabase.config
[ -e ~/.marketreview/supabase.secret ] || cp "<skill-dir>/config/supabase.secret.example" ~/.marketreview/supabase.secret
chmod 600 ~/.marketreview/supabase.secret
```

将 `<skill-dir>` 换成本机已安装版本包的绝对路径。这个路径是解压后的 `daily-market-review` 目录，不是源码仓库。

| 项 | 本机位置 | 说明 |
| --- | --- | --- |
| 后端选择 | `~/.marketreview/supabase.config` 中 `backend` | 只能是 `sqlite` 或 `supabase`；日常写 `supabase`。省略时进程默认也是 `supabase` |
| 项目 URL | 同上 `supabase_url` | 控制台 Project URL，不含密钥 |
| Publishable | 同上 `supabase_publishable_key` | `sb_publishable_...`（旧名 anon 亦可）；低权限，可写在 config |
| Secret | `~/.marketreview/supabase.secret` | `sb_secret_...`（旧名 service_role 亦可）；高权限，单独文件、单行、权限 600 |

日常写 RPC 使用 Secret。`backend=sqlite`（或显式 `--backend sqlite`）时不要求云端凭证。使用 `supabase` 时必须已填写 URL 与 Secret；缺配置、鉴权失败或断网会明确报错，**不会**回退本地 SQLite。Secret 只放在 `supabase.secret`。`supabase.config` 里如果写了 Secret Key，命令会停止。

### 云端初始化

安装客户端、复制配置模板和填写凭证都不会自动部署云端数据库。新项目须由有数据库管理权限的维护者，使用管理连接或 SQL 编辑器，按文件编号依次执行发布包 `sql/migrations/` 中的 `0001`、`0002`、`0003`、`0004`、`0005`、`0006` 迁移；已有项目先核对已部署迁移，仅应用缺失部分。迁移包含表、函数、RPC wrappers 和服务端超时设置，不能只建表。现有项目迁移前先做云端备份。

部署完成后，用下方显式 Supabase 的 `get` 命令检查读取是否成功。缺表 / 函数 / RPC 时应核对项目和迁移部署，不要反复更换密钥。一次读取成功只是连通性检查，不能代替迁移完整性与备份恢复核验。

### 从 0.4.x 升级到 0.5.0

0.5.0 给涨停事件明细新增五个键（`seal_amount`、`seal_ratio`、`first_limit_time`、`close_price`、`stock_float_market_cap`），其中 `seal_ratio` 是读取派生字段（`seal_amount ÷ turnover_amount`），不入库。客户端不会自动部署云端迁移；**未部署 `0006` 前，日常复盘读写不受影响，只是其余四项写不进去，读取云端旧明细时缺键一律按 `null` 处理，不会报错。** 升级步骤：

1. 现有项目先做云端备份（Dashboard → Database → Backups，或按备份恢复流程）。
2. 部署 `0006`，二选一：
   - **SQL Editor**：Supabase Dashboard → SQL Editor，粘贴发布包 `sql/migrations/0006_limit_up_strength.sql` 全文执行；
   - **psql 管理连接**：`psql "postgresql://postgres:<数据库密码>@db.<项目ref>.supabase.co:5432/postgres" -f sql/migrations/0006_limit_up_strength.sql`。注意 `supabase.secret` 里的 Secret 是 API 密钥，不是数据库密码，不能用于 psql。
   `0006` 的列用 `ADD COLUMN IF NOT EXISTS`、函数用 `CREATE OR REPLACE`，重复执行不会失败；只部署 `0006` 即可，不需要重跑 `0001`–`0005`。
3. 用 `get` 回读任一交易日确认读取正常，再写一条带 `seal_amount` 和 `turnover_amount` 的明细，确认四项可写入、`seal_ratio` 读取时按公式算出。历史明细保持空值，不回填。

### 从 0.3.4 升级到 0.4.0

**更新程序不会自动上传旧 SQLite 数据。** 默认读取目标已改为 Supabase；空云端项目的「无复盘数据」不表示旧本地记录丢失。已有 `backend=sqlite` 配置仍优先于新版默认值。

1. 停止各端写入，确认旧库实际路径（包括 `--db` / `MARKETREVIEW_HOME`），为每份旧库做 SQLite 一致性备份并长期保留；有 WAL 时不要只复制主文件。安装 0.4.0 后刷新 Agent，核对实际加载的 `SKILL.md` 版本。
2. 按上文配置并初始化目标 Supabase 项目；已有云端数据先做云端备份。各电脑确认使用同一目标项目。若暂不迁移，明确设置 `backend=sqlite` 继续本地使用，这不代表已共享云端。
3. 使用新版本 CLI 对每份旧库依次执行 `sync push --source <旧库绝对路径>`。不要用日常保存命令循环搬运。遇到冲突逐组选择；`partial`、`needs_resolution` 或 `unknown` 均不表示完整迁移完成，须按同步报告处理。所有冲突和本地删除选择处理完毕、仅剩待下载项时，执行 `sync pull` 完整下载（不是按组下载）；待核验操作须先恢复，不能换机重提。
4. 核对每份源库的同步报告：应无未决冲突、本地删除选择、待下载或结果未知项，完整合并的状态为 `completed`。再显式从云端回读有代表性的历史日期，与备份中的原子字段、事件及梯队扩展核对；不能只以命令退出码或 `ok=true` 判断迁移完成。
5. 各电脑把日常配置统一为 `backend=supabase`，分别用不带后端参数的 `get` 回读核对。同步命令本身不会修改这个配置。完成云端备份及空白库恢复核验后，保留旧库备份作为迁移记录。

```bash
python3 "<skill-dir>/scripts/cli.py" sync push --source /absolute/path/to/old-market-review.sqlite3
python3 "<skill-dir>/scripts/cli.py" --backend supabase get --date 2026-08-21
python3 "<skill-dir>/scripts/cli.py" get --date 2026-08-21
```

示例日期请替换为旧库确有记录的历史交易日。需要回退时先停写并核对差异，见下节；不要直接启用过期本地库。

### 上传与完整下载（独立于日常 backend）

权威账本在云端。`sync push` 把一份本地库上传进去，`sync pull` 把云端完整下载到一份本地库。两者都不修改日常 `backend`，也不要求两台电脑的本地库保持一致。需要本机已填写 URL 与 Secret。省略 `--source` / `--target` 时按现有本地路径规则解析日常 SQLite。

回退：先停止写入，核对云端相对准备启用的那份旧 SQLite 差了什么，再决定下载或从云备份恢复。不能把过期本地库直接当成当前账本。`partial` 或「待下载」表示这次合并还没结束，不是云端缺少已提交的上传。

```bash
python3 "<skill-dir>/scripts/cli.py" sync push --source ~/.marketreview/market_review.sqlite3
python3 "<skill-dir>/scripts/cli.py" sync pull --target ~/.marketreview/market_review.sqlite3
```

冲突或本地删除待处理时，用组引用重复选择（可多次）：

- `--keep-cloud review:2026-08-21`
- `--adopt-local event:2026-08-21:sh:600519`
- `--restore-cloud` / `--delete-on-cloud`（本地删除待处理）

方向替换超时后的本机核验：`verify-pending`（过 8s 在途窗口且前像仍一致时才会受控重发）。

### 云端 PostgreSQL 备份（管理连接）

正式备份走数据库密码 + `pg_dump`（Session pooler；不用 transaction pooler，不用 Secret Key）。CLI：`scripts/pg_backup.py`（`backup` / `restore-blank` / `verify`）。成功包写入 `~/.marketreview/backups/supabase/<UTC>/`，含 `marketreview` schema、**`public.marketreview_*` wrappers**、迁移副本与校验清单；不进仓库。恢复须在空白库上核验通过才算有效。日常默认已是 Supabase。
