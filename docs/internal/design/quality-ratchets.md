# 质量棘轮

Baldric 用 CI 门与只能单向移动的已提交基线的组合维持质量线。本文记录每个棘轮守护什么、在哪里运行、如何收紧。

这些机制取材于成熟的 agent 项目的实践：
Codex 把约束编进工具链（clippy `deny`、一条必需检查、干净工作树），DeepSeek Harness 保有 341 个窄守卫加计数基线，Kimi CLI 注入仓库地图并审计不变量，DeerFlow 把架构边界作为普通 pytest 测试强制，并让指令文件受字节预算约束。

## 已在 CI 门控

| 门 | 锁定什么 |
| --- | --- |
| `pytest` 矩阵（3.12/3.13/3.14） | 行为必须在每个受支持解释器上通过 |
| `ruff check .` | 零 lint 发现；任何新违规都失败（fail-on-error 本身就是棘轮） |
| `ruff format --check .` | 格式不能漂移 |
| `mypy` | Linux（CI 运行平台）上无类型错误 |
| docs 构建 + 网站测试 | 已发布文档不能坏 |
| `collection-gate` | 每个测试都能在干净安装中被收集 |
| `all-checks-passed` | 一条必需检查；`always()` 保证失败的依赖不会看起来是绿的 |
| `Assert a clean worktree` | CI 不得留下未提交变更 |


## 本笔记引入的棘轮

### 覆盖率下限

`pyproject.toml` 设 `[tool.coverage.report] fail_under = 80`，CI 运行
`uv run pytest --cov`。下限刻意保守：Windows
开发套件在跳过 POSIX-only 测试时约 85.7%，Linux CI 套件还会跑那些测试，所以真实 CI 覆盖率更高。覆盖率增长时收紧
`fail_under`；它永不放松。

### 架构层方向

`scripts/check_import_graph.py` 强制 AGENTS.md 的分层规则
（`baldric_agent` 不碰 `baldric_coding`/`textual`/`rich`，
`baldric_ai` 不碰 `baldric_coding`，frontend 模块不进
session/tools/trust/providers/context）。脚本早已有之但靠手动；CI 现在每次 push 与 PR 都运行它。

注意：`scripts/check_move_only.py` 有意不进 CI。它是 phase-1 只移动重构的窄审计，按设计拒绝普通代码变更。

### 结构棘轮

`scripts/check_structure.py` 在 `src/` 上测量：

- 每文件行数与最长函数体（直接语句数）；
- 全局最深的项目内继承链；
- 全局最宽的模块扇出（导入的不同项目内模块数）。

已提交的 `structure-baseline.json` 记录当前值。任何指标退过基线，或没有基线条目的文件超过硬限（1200 行 / 150 语句）时检查失败。改善的指标会被报告并提示运行
`uv run python scripts/check_structure.py --init`，把基线重写得更紧。基线已提交；棘轮只收紧。

本笔记时点的基线亮点：`tui/app.py` 5781 行、
`session/session.py` 2220 行、最大扇出 51 模块、继承深度 1。
这些是后续工作必须打败的数字，不是追平的数字。

### 豁免棘轮

`scripts/check_suppressions.py` 按文件与类别统计 `# type: ignore` / `# noqa` 注释（`suppressions-baseline.json`）。它补上 `mypy --strict` 最大的洞：一次绿色的 mypy 运行说不出有多少豁免注释在撑着。当前基线：41 个文件 141 条注释，主要是 94 条 `noqa: BLE001`（宽异常处理）与 17
条 `noqa: F401`（再导出）。

注释扫描用 `tokenize` 而不是正则，字符串或 docstring 里的 "noqa" 一词绝不会被计为豁免。每个棘轮脚本还断言最小语料规模，错误路径无法让门空转地变绿。

### agent 指引棘轮

`scripts/check_agent_guidance.py` 记录每个 `AGENTS.md`
与 `CLAUDE.md`（根与每包）的字节大小，加上最深的根到包链
（`agent-guidance-baseline.json`）。指令文件只能缩小；增长需要重跑 `--init`——那是"说明为什么"的时刻。`CLAUDE.md` 必须保持薄的 `@AGENTS.md` 垫片，规则只有一个家。

### lint 配置指纹

`tests/guards/test_lint_config_fingerprint.py` 对归一化的 ruff 与 mypy 配置做哈希。删一条 ruff 规则或关掉 `mypy.strict` 都会改变哈希，因此必须编辑测试——这是披露步骤，不是静默放松。

### 黄金文件

`tests/helpers/golden.py` 把 wire 格式输出对照 `tests/expected/` 里的已提交文件（assistant 消息 JSON 与 tool 结果 JSON）。测试只读这些文件；更新需要 `UPDATE_EXPECTED=1`，它会打印所接受的 diff。

渲染的终端输出被刻意排除。`--help` 黄金文件试过又回退：rich 在不同平台上的 Unicode 换行与测量不同，Windows 上生成的文件在 Linux 上有 162 行 diff 而行为毫无变化。黄金文件只对处处逐字节一致的输出有意义。

### 代码不变量

`tests/invariants/test_code_invariants.py` 用 `ast` 遍历 `src/` 并强制：
`subprocess` 调用必须传 timeout、不允许裸 `except:`、无显式 encoding 的文件 IO 保持 ≤ 18 处（棘轮，这些调用早于规则）。

### 门的自我测试

`tests/guards/` 证明每个门仍会触发：植入的层违规、变大的文件、新增的豁免、变大的指令文件都必须被拒绝。一个不再抓任何东西的绿门比没有门更糟，所以门本身要被测试。

## 本地工作流 hook

`.pre-commit-config.yaml` 只跑快速检查（ruff fix/format、三个
棘轮、版本一致性），刻意不跑测试；CI 拥有完整矩阵。`.github/pull_request_template.md` 要求写出实际运行的命令、行为证明清单与 AI 协助披露。

`scripts/verify_versions.py` 保持 `pyproject.toml`、`uv.lock` 与（发布期的）git tag 一致。

## 刻意缺席

性能基线（没有可守护的热路径基准）、API 表面快照（尚无外部消费者）、跳过数门（Linux CI 按设计只跳过少量测试）、PR 大小限制（单人开发的噪音）、pytest 标记与分片测试（套件在 Linux 约 3 分钟；分片徒增 CI 机械）、Blockbuster 式阻塞 IO 门（当前代码只有一处 `time.sleep`，事件循环路径上没有阻塞调用——它守护的风险还不存在）。
