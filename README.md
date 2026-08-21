# qwen38-27b-coding

一组**纯 Python 标准库**编写的小型实用工具：系统资源监控、进程级资源监控、git 周报生成。无需安装任何第三方依赖，macOS / Linux 开箱即用。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `monitor.py` | 系统资源监控：CPU、内存、磁盘使用率，文本进度条展示 |
| `procm.py` | 进程级监控：按 CPU / 内存排序的 Top N 进程列表 |
| `weekly_report.py` | 基于 git log 自动生成开发周报（按仓库、按类型分类统计） |

## 环境要求

- **Python 3.9+**（已在 Python 3.13 下验证），无任何第三方依赖
- **macOS / Linux**（`monitor.py` 在 Windows 上不支持）
- `weekly_report.py` 需要目标目录是 git 仓库

## 使用方式

### 1. monitor.py — 系统资源监控

数据来源：macOS 使用 `top` / `sysctl` / `df`，Linux 使用 `/proc` 与 `df`。

```bash
python3 monitor.py              # 每 2 秒刷新一次，Ctrl+C 退出
python3 monitor.py --once       # 只输出一次快照后退出
python3 monitor.py -i 5         # 每 5 秒刷新
python3 monitor.py --threshold 90   # 任一指标 ≥ 90% 时给出警告
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-i, --interval` | `2.0` | 刷新间隔（秒） |
| `--once` | - | 输出单次快照后退出 |
| `--disk-path` | macOS: `/System/Volumes/Data`，Linux: `/` | 要监控磁盘使用率的路径 |
| `--threshold` | `95.0` | 警告阈值（百分比） |

### 2. procm.py — 进程级资源监控

数据来源：`ps -axo pid,pcpu,pmem,rss,comm`（macOS 与 Linux 通用）。

```bash
python3 procm.py                # 按 CPU 排序的 Top 10 进程
python3 procm.py --by mem      # 改为按内存排序
python3 procm.py -n 20         # 显示 Top 20
python3 procm.py -i 5          # 每 5 秒刷新，Ctrl+C 退出
python3 procm.py -g python     # 只显示名称包含 "python" 的进程
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-n, --top` | `10` | 显示的进程数量 |
| `--by` | `cpu` | 排序维度：`cpu` 或 `mem` |
| `-i, --interval` | `0`（单次） | 刷新间隔（秒），`0` 表示只输出一次 |
| `-g, --group` | - | 按进程名做子串过滤 |

### 3. weekly_report.py — git 周报生成

自动读取一个或多个 git 仓库在时间窗口内的提交，解析 Conventional Commit 前缀（`feat` / `fix` / `docs` …）归类，统计新增/删除行数，输出 Markdown 周报。

```bash
python3 weekly_report.py                    # 当前目录仓库，最近 7 天
python3 weekly_report.py ../repo1 ../repo2  # 指定多个仓库
python3 weekly_report.py -d 14              # 最近 14 天
python3 weekly_report.py --author 张三       # 只统计指定作者的提交
python3 weekly_report.py -o report.md       # 同时写入文件
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `repos`（位置参数） | `.`（当前目录） | 一个或多个仓库路径，非仓库目录会自动跳过 |
| `-d, --days` | `7` | 统计窗口（天） |
| `--author` | - | 按作者过滤（git `--author` 语法） |
| `-o, --output` | - | 将周报额外写入指定文件 |

## 注意事项

- `procm.py` 中的 `%CPU` 来自 `ps`，在 macOS 上是**1 分钟平均值**，不是瞬时值。
- `monitor.py` 在 macOS 上默认监控 `/System/Volumes/Data`（数据卷），这是 macOS 上更能反映真实磁盘占用的挂载点，可用 `--disk-path` 覆盖。
- `weekly_report.py` 对非 Conventional Commit 的提交会归入「其他」类别；提交信息中的 `feat(api):` 这类 scope 前缀会被自动剥离。
