# asharekit

A 股市场 skill 集。当前有两个互相独立的 skill：一个记录收盘后的市场复盘，一个从已保存的连板里选股。

仓库是 [shenjee/asharekit](https://github.com/shenjee/asharekit)。这个仓库只用于开发和打包。Agent 加载的 skill 只来自 GitHub Release 的版本包，不来自本仓库的任何目录。

## 目录

```text
asharekit/
├── README.md
├── LICENSE
├── .github/workflows/tests.yml
└── skills/
    ├── daily-market-review/     # 每日市场复盘，当前 0.4.3
    └── streak-picker/           # 连板选股，当前 0.0.1
```

每个 skill 自己有版本号、`SKILL.md` 和发布包。改选股规则不升复盘的数据库版本。

| | `daily-market-review` | `streak-picker` |
| --- | --- | --- |
| 做什么 | 采集、校验、保存、展示已收盘日的涨跌停、连板高度、每日梯队、市场宽度、两融、指数、成交额、市值与估值 | 从已保存的连板里筛选、排序，给出候选和命中依据 |
| 数据 | 拥有复盘账本。默认 Supabase，显式 `--backend sqlite` 使用本地库 | 只读复盘 skill 的 `get`。不写复盘库。选股结果不进 `market_review` 的表 |
| 触发 | 保存、补齐、修正、查看复盘和梯队 | 选股、筛选、哪些连板值得看 |
| 发布包 | `daily-market-review-vX.Y.Z.zip`，解压后根目录是 `daily-market-review/SKILL.md` | 规则发布后再打 `streak-picker-vX.Y.Z.zip` |

两边都给出事实或候选依据，不写买卖指令。市场事实补进复盘 skill 的事件字段。排序和过滤规则留在 `streak-picker`。

## 安装

每个 skill 单独安装，而且只安装 GitHub Release 上的版本包。不要克隆本仓库来安装，也不要把 `skills/` 下的目录放进 Agent 的 skill 目录。

版本包解压后的目录才是安装目录。GitHub 自动生成的 Source code 压缩包是源码仓库，不能当作 skill。

### daily-market-review

当前发布版本是 **0.4.3**。从 [Releases](https://github.com/shenjee/asharekit/releases) 下载 `daily-market-review-vX.Y.Z.zip`。安装步骤、云端配置和升级说明在版本包内的 README；源码里的同一份见 [skills/daily-market-review/README.md](skills/daily-market-review/README.md)。

### streak-picker

当前版本是 **0.0.1**，只写了边界，选股规则还没有发布，所以没有版本包，也不能安装。说明见 [skills/streak-picker/README.md](skills/streak-picker/README.md)。规则发布并上传 `streak-picker-vX.Y.Z.zip` 之后，才按同一个办法安装。

## 两个 skill 怎么配合

选股 skill 不 import `marketreview`，不直接打开 SQLite。它调用已经安装的复盘 CLI：

```bash
python3 "<review-skill-dir>/scripts/cli.py" get --date 2026-08-21
```

`<review-skill-dir>` 是已经安装的复盘版本包，按这个顺序找：

1. 环境变量 `MARKETREVIEW_SKILL_DIR`
2. `~/.codex/skills/daily-market-review`
3. `~/.cursor/skills/daily-market-review`

这三处都是安装位置。源码仓库里的 `skills/daily-market-review/` 不在查找范围内。

复盘账本仍由 `daily-market-review` 写入。云端模式下，多个 Agent 连接同一个 Supabase 项目才共享同一份账本。

## 开发

开发和安装分开。在本仓库里改代码、跑测试、打版本包。Agent 用的那一份只在 Release 安装之后才更换，不把工作副本链到 skill 目录。

复盘 skill 的字段、测试和打包见 [skills/daily-market-review/CONTRIBUTING.md](skills/daily-market-review/CONTRIBUTING.md)。

在仓库根目录运行测试：

```bash
python3 -m unittest discover -s skills/daily-market-review/tests -p 'test_*.py'
```

GitHub Actions 跑同一条命令。流水线自建隔离 PostgreSQL，不读取 Secret、数据库密码或 `~/.marketreview`。

## 许可证

[MIT](LICENSE)
