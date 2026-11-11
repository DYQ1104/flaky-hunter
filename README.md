# flaky-hunter

> 找出不稳定的测试，并定位是谁污染了它。

`flaky-hunter` 是一个离线可用的 flaky test 检测与归因 CLI：跑 N 轮测试，给出每个用例的不稳定评分，把失败按根因聚类，并对「单独跑通过、全量跑失败」的用例自动**二分定位**出最小的污染源集合。

```
flaky-hunter 1.0.0  ·  session 6d6fa1  ·  adapter pytest
Rounds: 10/10   Tests: 6   Duration: 5.2s

OVERVIEW
  flaky 2   broken 2   stable 2   insufficient 0

FLAKY TESTS (by score)
   #  SCORE     RATE  ROOT CAUSE          TEST
   1   84     3/10  network             tests/test_network_flaky.py::test_fetch_remote
   2   64     2/10  timeout             tests/test_slow_timeout.py::test_slow_call

LOCATED POLLUTERS
  tests/test_order_victim.py::test_read_shared_state
    status: FOUND  probes: 10  confidence: high
    <- tests/test_order_polluter.py::test_write_shared_state
    reproduce:
      python -m pytest -q tests/test_order_polluter.py::test_write_shared_state tests/test_order_victim.py::test_read_shared_state

BROKEN (100% failed — fix these first)
  tests/test_broken.py::test_always_fails   10/10
  tests/test_order_victim.py::test_read_shared_state   10/10  -> 顺序依赖，见 LOCATED POLLUTERS
```

## 能力

- **多轮统计**：按用例聚合执行结果，输出 `flaky / broken / stable / insufficient` 四类分桶
- **0~100 评分**：Gini 不稳定度 × 样本置信度，避免「失败率越高越优先」的错误排序
- **失败签名聚类**：归一化时间戳、端口、临时路径、异常类型，把同一根因的失败聚在一起
- **根因标签**：`timeout` / `network` / `data-residue` / `concurrency` / `resource` / `assertion-mismatch`
- **污染源定位**：基线实验 → 二分最小失败前缀 → 贪心最小化 → 复核，输出可复现命令
- **三种报告**：terminal / JSON / Markdown；JSON 带完整 probe 证据
- **可复现元数据**：报告记录 `schema_version` / `tool_version` / 执行命令 / 工作目录，并单独统计 skipped 用例

## 安装

```bash
pip install flaky-hunter
# 可选：Python < 3.11 读取配置文件需要 tomli
pip install "flaky-hunter[toml]"
```

从源码安装：

```bash
pip install -e .
```

要求 Python 3.9+；推荐 3.11+（内置 `tomllib`）。

## 快速开始

```bash
fh demo
```

`fh demo` 会把内置示例仓库复制到临时目录，跑 10 轮并完成一次定位，不写入当前工作目录。

> 示例仓库通过 `FH_ROUND` 环境变量制造确定性失败，因此每次演示结果一致。

## 常用命令

```bash
# 10 轮 + 自动定位
fh run -c "pytest -q --junitxml={report}" -n 10

# 夜间任务：20 轮，评分 ≥ 60 时以退出码 2 拦截，只报告相对基线的增量
fh run -c "pytest -q --junitxml={report}" -n 20 \
       --fail-on-score 60 \
       --baseline flaky-baseline.json \
       --format json --output flaky-report.json

# 只分析已有报告（支持 JUnit XML / pytest-json-report）
fh analyze "reports/*.xml" --format markdown --output flaky-report.md

# 用 pytest 收集结果把 classname::name 补全为可执行 nodeid
fh analyze "reports/*.xml" --cwd . --format json --output flaky-report.json

# 对单个用例做定位（路径支持唯一后缀匹配）
fh locate tests/test_order_victim.py::test_read_shared_state
```

退出码：`0` 正常、`1` 工具错误、`2` 命中门禁、`3` 未采集到结果。

## 工作原理

### 1. 评分

```
p = failures / attempts
U = 4p(1-p)                 # Gini 不稳定度：p=0.5 时最大
C = min(1, attempts / 10)   # 样本置信度
score = round(100 * U * C)
```

失败率 100% 的用例会被归为 `broken`，score 为 0——它需要人去看 bug，而不是治抖动；真正危险的是 50/50 翻转的用例。

### 2. 失败签名

对 message + 用户栈帧做归一化（去时间戳 / UUID / 端口 / 临时路径 / 地址 / 数字），取 SHA-1 前 12 位作为签名；栈帧过滤掉 `site-packages` 与标准库。同一签名即视为同一根因。

### 3. 定位

```
基线：单独跑目标用例（默认 2 次）      必须通过，否则不是顺序依赖
全量：按原顺序跑「前序用例 + 目标」    必须失败，否则 INCONCLUSIVE
二分：找最小的失败前缀长度              O(log n) 次 probe
最小化：逐个剔除不必要的前序用例        O(k) 次 probe
复核：重复执行最终集合（默认 2 次）     全部失败才判定 high confidence
```

**每个 probe 的通过/失败以目标用例本身的报告结果为准，而不是 pytest 的进程退出码**——子集里其他用例失败不应污染结论。

总预算默认 60 次 probe，耗尽时返回 `PARTIAL` 并保留已有证据。二分依赖「污染单调叠加」假设，结论标注为 best-effort，完整 probe 证据写入 JSON，可人工复核。

## 真实项目验证

对 **pytest 9.2.0** 源码包中 9 个时序 / 子进程 / 临时目录相关测试文件执行 10 轮分析：

| 指标 | 结果 |
|---|---|
| 用例 | 519 个实际执行（另有 20 个平台条件跳过） |
| 轮次 | 10/10 有效，总耗时 627.8s（单轮 50.8~81.9s） |
| 分类 | flaky 0 / broken 0 / stable 519 |
| 环境 | Windows 10.0.26200，Python 3.13.12，pytest 9.2.0 |

报告：[JSON](reports/pytest-9.2.0-flaky-report.json) / [Markdown](reports/pytest-9.2.0-flaky-report.md)

> 该报告由 v1.0 生成（schema 1.0）；当前工具 schema 为 1.1，新增 `tool_version` / `command` / `cwd` / `skipped_tests` 字段，新生成的报告会自动带上这些元数据。

该子集是 pytest 自测中确定性较强的用例，0 flaky 属于预期结果；本次运行验证了工具在 5190 次真实执行上的采集与统计能力，且没有产生假阳性。检测与污染源定位效果见 `fh demo`。

## 技术文章

- [如何定位测试用例的顺序依赖污染源](docs/顺序依赖污染源定位.md)：从基线实验、二分、贪心最小化到证据复核的完整推导。

## 配置

默认向上查找 `.flaky-hunter.toml`，也支持 `pyproject.toml` 的 `[tool.flaky-hunter]`。优先级：CLI > `FH_*` 环境变量 > 配置文件 > 默认值。

```toml
[run]
command = "pytest -q --junitxml={report}"
rounds = 10
adapter = "pytest"          # pytest | junit-xml

[analysis]
min_attempts = 5
ignore = ["tests/e2e/*"]

[locate]
top_n = 5
confirm_runs = 2
max_probe_total = 60

[ci]
fail_on_score = 0           # 0 表示关闭门禁
```

## CI 示例

```yaml
name: flaky-hunter
on:
  schedule: [{ cron: "0 18 * * *" }]
  workflow_dispatch:
jobs:
  hunt:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install flaky-hunter pytest
      - run: fh run -n 20 --fail-on-score 60 --format json --output flaky-report.json
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: flaky-report, path: flaky-report.json }
```

## 已知限制

- `locate` 目前只支持 pytest；`analyze` 通过 JUnit XML 支持任意语言产出的报告
- 分析已有 JUnit XML 时，用例标识为 `classname::name`（XML 不含 nodeid）；加 `--cwd` 可调用 pytest 收集把 nodeid 补全为可执行形式，但 `analyze` 本身仍不做定位
- 二分定位假定污染可叠加，若污染需要多步配合或会被后续用例清理，结论可能不是最小集
- 并行执行测试会放大资源竞争，flaky 评分不可与串行结果直接比较

## 开发

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows
.venv/bin/python -m pip install -e ".[dev]"       # macOS/Linux
python -m pytest
```

## 发布

本项目使用两个 GitHub Actions 工作流：

- `.github/workflows/ci.yml`：push / PR 时在 Ubuntu + Windows × Python 3.9~3.13 跑单测，另有一个 job 构建 sdist/wheel、`twine check`，并在干净 venv 里安装 wheel 跑 `fh demo`。
- `.github/workflows/release.yml`：推送 `v*` tag 时构建产物，通过 [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) 发布，并把产物附加到 GitHub Release。

首次发布前需要在 PyPI 项目设置里配置 trusted publisher（owner / repo / workflow `release.yml` / environment `pypi`），然后：

```bash
git tag v1.0.0
git push origin v1.0.0
```

本地预检：

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```

```
src/flaky_hunter/
├── cli.py              # run / analyze / locate / demo
├── runner.py           # 多轮执行与报告采集
├── adapters/           # pytest / junit-xml 适配器
├── parsers/            # JUnit XML / pytest-json-report
├── analyze/            # 评分、签名、聚类、根因
├── locate/             # 隔离实验、二分、最小化
├── report/             # terminal / json / markdown
└── demo/fixture/       # 内置示例仓库
```

## License

MIT
