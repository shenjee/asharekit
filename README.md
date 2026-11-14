# asharekit

A 股市场 skill 套件。当前包含两个互相配合的 skill：一个记录收盘后的市场复盘，一个从已保存的连板里选股。

仓库是 [shenjee/asharekit](https://github.com/shenjee/asharekit)。这个仓库只用于开发和打包。Agent 加载的 skill 只来自 GitHub Release 的套件版本包，不来自本仓库的任何目录。

## 套件约定

- **整包发布，整包安装。** 发布单位是套件，版本包 `asharekit-vX.Y.Z.zip` 里包含全部 skill。套件一个版本号；各 skill 文档里的版本号是该 skill 的口径记录，不对应独立发布包。
- **同一个安装目录。** 套件里的 skill 目录一起放进 Agent 的 skill 目录，互为同级。sibling 关系由安装方式保证，是 skill 之间互相找到对方的唯一依据，不需要查找列表或环境变量。各 Agent 的 skill 目录位置参考其官方文档。
- 源码仓库的 `skills/` 不是安装位置。

## 目录

```text
asharekit/
├── README.md
├── LICENSE
├── .github/workflows/tests.yml
└── skills/
    ├── daily-market-review/     # 每日市场复盘
    └── streak-picker/           # 连板选股
```

| | `daily-market-review` | `streak-picker` |
| --- | --- | --- |
| 做什么 | 采集、校验、保存、展示已收盘日的涨跌停、连板高度、每日梯队、市场宽度、两融、指数、成交额、市值与估值 | 从已保存的连板里筛选、排序，给出候选和命中依据 |
| 数据 | 拥有复盘账本。默认 Supabase，显式 `--backend sqlite` 使用本地库 | 只读复盘 skill 的 `get`。不写复盘库。选股结果不进 `market_review` 的表 |
| 触发 | 保存、补齐、修正、查看复盘和梯队 | 选股、筛选、哪些连板值得看 |

两边都给出事实或候选依据，不写买卖指令。市场事实补进复盘 skill 的事件字段。排序和过滤规则留在 `streak-picker`。

## 安装

只安装 GitHub Release 上的套件版本包。不要克隆本仓库来安装，也不要把源码目录放进 Agent 的 skill 目录。

1. 打开 [Releases](https://github.com/shenjee/asharekit/releases)，下载最新的 `asharekit-vX.Y.Z.zip`。不要下载 GitHub 自动生成的 `Source code (zip)`。
2. 解压，得到并排的 skill 目录（`daily-market-review/`、`streak-picker/`）。
3. 把这些目录**一起**放入所使用 Agent 的 skill 目录。各 Agent 的 skill 目录位置请参考其官方文档。
4. 重启或刷新 Agent 加载新 skill。

套件版本接续 daily-market-review 的发布线：0.5.0 及以前是单 skill 发布，下一个套件版本为 0.6.0。`daily-market-review` 的云端配置与初始化见 [skills/daily-market-review/README.md](skills/daily-market-review/README.md)；`streak-picker` 无需配置。

## 两个 skill 怎么配合

选股 skill 不 import `marketreview`，不直接打开 SQLite。它调用同级目录里的复盘 CLI：

```bash
python3 "<skill-dir>/../daily-market-review/scripts/cli.py" get --date 2026-08-21
```

`<skill-dir>` 是 `streak-picker` 的安装目录。同级目录里没有 `daily-market-review` 时，说明套件没有完整安装，停止并提示重新安装套件版本包。源码仓库里的 `skills/daily-market-review/` 不是安装位置。

复盘账本仍由 `daily-market-review` 写入。云端模式下，多个 Agent 连接同一个 Supabase 项目才共享同一份账本。

## 开发

开发和安装分开。在本仓库里改代码、跑测试、打套件版本包。Agent 用的那一份只在 Release 安装之后才更换，不把工作副本链到 skill 目录。

套件版本包的打包内容（各 skill 应包含的运行文件）与发布检查清单见 [skills/daily-market-review/CONTRIBUTING.md](skills/daily-market-review/CONTRIBUTING.md)。

在仓库根目录运行测试：

```bash
python3 -m unittest discover -s skills/daily-market-review/tests -p 'test_*.py'
python3 -m unittest discover -s skills/streak-picker/tests -p 'test_*.py'
```

GitHub Actions 跑这两条命令。流水线自建隔离 PostgreSQL，不读取 Secret、数据库密码或 `~/.marketreview`。

## 许可证

[MIT](LICENSE)
