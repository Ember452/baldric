# `baldric.coding` 改名 `baldric.runtime`

状态：完成（2026-11-10，分支 `refactor/coding-to-runtime`）。

## 变更了什么

应用/宿主包被改名以去掉 "coding" 的狭义，同时保持发行名（`baldric`）不变：

| 之前 | 之后 |
| --- | --- |
| `src/baldric/coding/` | `src/baldric/runtime/` |
| `import baldric.coding` | `import baldric.runtime` |
| `files("baldric.coding")` | `files("baldric.runtime")` |
| console entry `baldric.coding.cli:app` | `baldric.runtime.cli:app` |
| `tests/coding/` | `tests/runtime/` |

`baldric` 仍是包根；分层现在是
`baldric.{protocol, ai, agent, runtime, mcp}`。

## 刻意不变的部分

- **标识符**：`CodingSession`、`CodingSessionEvent`、`CodingSessionRecord`、
  `CodingSessionConfig`、`create_coding_tools`、`CodingReloadSummary`、
  `FakeCodingSession` 等保持原名。它们命名的是*编码 session*——一个正当概念——且位于冻结公开 API（139 个导出）中。包是这类 session 的宿主；宿主包改名不使 session 类型不再是 coding session。pi/tau 同样在别名的包里保留 `coding` 味道的类。
- **只含 "coding" 一词的无关字符串**：
  `"https://api.kimi.com/coding/v1"`（真实 provider URL）与测试模块文件名 `test_coding_session.py` / `test_coding_tools.py`。
- **历史记录**：`dev-notes/**`、`plans/**`、`docs/superpowers/**`、
  `data/release-notes/**` 按设计继续用旧路径。

## 怎么做（边界安全的批量改写）

- 目录经 `git mv` 移动（src 与 tests）。
- 一次性脚本只替换有界的包路径：
  `baldric.coding` → `baldric.runtime`、`baldric/coding` → `baldric/runtime`、
  `tests/coding` → `tests/runtime`。其 16 例自测证明正则
  绝不触碰 `CodingSession`、`create_coding_tools`、`api.kimi.com/coding` 或
  `baldric_coding`。改写 273 个文件；第二遍运行零变化。
- 注记：早先的 token 级变体没能改写真实的 `from baldric.coding
  import` 语句（那是三个 token——`baldric . coding`——不是单个 STRING token），整文本、边界安全的正则修复了它。提交前由 dry-run + 残留扫描抓住。
- 正则正确放过的路径段字面量
  （少量测试里的 `Path / "baldric" / "coding"`）由手工修复。
- 门脚本：`check_import_graph.py` 的 RULES 与 `check_structure.py` 扇出根集合由脚本翻译；`check_agent_guidance.py` glob
  `src/baldric/*`，无需变更。

## 配置 / 基线

- `pyproject.toml`：entry point 与 coverage `omit` → `runtime`。
- `structure-baseline.json`、`suppressions-baseline.json`、
  `agent-guidance-baseline.json`：用 `--init` 重新生成（纯键改名）。
- `tests/guards/session_state_write_baseline.json`：键重映射
  `src/baldric/coding/...` → `src/baldric/runtime/...`，值保留（61
  对 (field, count) 不变）。
- `.github/workflows/ci.yml`：一个路径清单更新为 `tests/runtime/...`。

## 验证

- `ruff check .` / `ruff format --check .`：绿（`coding`→`runtime` 改名
  需要导入重排（I001）与两处长行折行；无行为变更）。
- `mypy`：恰好 14 个已知 Windows-only 错误（`trust/policy.py`、
  `session/storage.py`，现位于 `src/baldric/runtime/`）。
- `check_import_graph.py`、`check_structure.py`、`check_suppressions.py`、
  `check_agent_guidance.py`、`verify_versions.py`：OK。
- 导入：`import baldric.{runtime,ai,agent,protocol,mcp}` 全部成功；
  `files("baldric.runtime").joinpath("data/catalog.toml")` 可读。
- `uv build`：wheel 只含 `baldric/runtime/...`（无 `coding` 路径），
  含 `baldric/py.typed` 与 `data/` 资源。
- `baldric --version` → `0.3.0`；entry point `baldric.runtime.cli:app`。
- `uv.lock` 不变。

## 对第三方的破坏性变更

更新导入路径（标识符不变）：

```python
# before
from baldric.coding.extensions import ExtensionAPI
from baldric.coding.session.session import CodingSession
# after
from baldric.runtime.extensions import ExtensionAPI
from baldric.runtime.session.session import CodingSession
```
