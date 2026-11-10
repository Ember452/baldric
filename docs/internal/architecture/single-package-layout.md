# 单包 `src/baldric/` 布局

状态：完成（2026-11-10，分支 `refactor/single-package-src-layout`）。

## 变更了什么

五个顶层导入包被合并到一个包根之下，使导入路径与发行名一致（`pip install baldric` →
`import baldric`）：

| 之前 | 之后 |
| --- | --- |
| `src/baldric_protocol` | `src/baldric/protocol` |
| `src/baldric_ai` | `src/baldric/ai` |
| `src/baldric_agent` | `src/baldric/agent` |
| `src/baldric_coding` | `src/baldric/coding` |
| `src/baldric_mcp` | `src/baldric/mcp` |

新的 `src/baldric/__init__.py`（仅 docstring，无再导出）是包
根。五个每包 `py.typed` 标记合并为 `src/baldric/py.typed` 一个（PEP 561 包根）。

这是**纯机械改名**：行为零变化、映射之外无改名、未触碰的代码不重新格式化。

## 为什么

对单一发行版，一个导入根（`baldric.*`）比五个并列顶层包更常规。pre-1.0 是动手的便宜时机。多包布局以物理方式表达的层边界仍由
`scripts/check_import_graph.py`（现为翻译后的前缀）与 `tests/guards/` 强制。

## 怎么做（批量改写纪律）

按 `AGENTS.md`，批量改写经评审过的、token 级脚本完成：

1. `git mv` 每个包目录到 `src/baldric/`（历史保留）。
2. 对 `src/`、`tests/`、`scripts/`、`examples/` 与受跟踪的项目 extension `.baldric/extensions/` 做 token 级改写：`NAME` token 与
   `STRING`/`COMMENT`/`FSTRING` token 文本改名；编辑范围之外的字节内容保留；每份改写的 `.py` 写前用 `ast` 重新解析并核对行数。
3. 现行文档的文本改写（根 `AGENTS.md`/`README.md`/`CONTRIBUTING.md`、
   scoped `AGENTS.md`、打包的 `data/docs`、`website/content`、`landing.html`、
   `website/src/data.ts`、`Home.astro`、`roadmap.yaml`）。
4. `--apply` 前逐行评审 dry-run 报告；第二遍 dry-run 零变化（幂等）。
5. 手工修复脚本无法切分的文件路径段
   （`"src" / "baldric.coding"` → `"src" / "baldric" / "coding"`）与门脚本的路径逻辑。

作为历史记录的目录被刻意**不**改写，按设计仍用旧名：`dev-notes/**`、`plans/**`、
`docs/superpowers/**`、`src/baldric/coding/data/release-notes/**`。

## 门脚本变更

- `check_import_graph.py`：RULES / surface 前缀翻译；`_module_name`
  与路径无关，无需变更。
- `check_structure.py`：模块扇出的项目根集合现在是
  `{baldric.agent, baldric.ai, baldric.coding}`；成员判断从首段匹配改为前缀匹配，嵌套点分名仍计入
  （protocol/mcp 照旧排除，指标语义相同）。
- `check_agent_guidance.py`：scoped 文件发现现在 glob `src/baldric/*`
  （比之前深一层）。
- `check_suppressions.py`、`check_move_only.py`、`verify_versions.py`：不变
  （与路径无关 / 基于发行名）。

## 基线

- `structure-baseline.json`、`suppressions-baseline.json`、
  `agent-guidance-baseline.json`：用 `--init` 重新生成。diff 经评审证明是纯键改名——structure/suppressions 值相同；
  guidance 值相等或更紧（`src/baldric_x/AGENTS.md` → `src/baldric/x/`
  短一个字节，棘轮因此收紧，允许）。
- `tests/guards/session_state_write_baseline.json`：键重映射
  `src/baldric_coding/...` → `src/baldric/coding/...`，值保留。
- `tests/guards/test_lint_config_fingerprint.py`：`EXPECTED_FINGERPRINT`
  更新，因为 mypy `packages` 清单有意从五条改为 `["baldric"]`。

## 对第三方的破坏性变更

这是 0.3.0 的公开导入破坏。更新导入：

```python
# before
from baldric_coding.extensions import ExtensionAPI
from baldric_protocol.tools import AgentTool, AgentToolResult
# after
from baldric.coding.extensions import ExtensionAPI
from baldric.protocol.tools import AgentTool, AgentToolResult
```

打包示例（`src/baldric/coding/data/examples`、`examples/` 与受跟踪的
`.baldric/extensions/ask_user_question.py`）在同一变更中更新。

## 验证

- `ruff check .` / `ruff format --check .`：绿。
- `mypy`：恰好 `trust/policy.py` +
  `session/storage.py`（新路径）的 14 个已知 Windows-only 错误，与基线一致；CI 在 Linux 上绿。
- `check_import_graph.py`、`check_structure.py`、`check_suppressions.py`、
  `check_agent_guidance.py`、`verify_versions.py`：OK。
- 资源冒烟：`files("baldric.coding").joinpath("data/catalog.toml")`
  可读；`import baldric.{protocol,ai,agent,coding,mcp}` 全部成功。
- `uv build`：wheel 只含 `baldric/...` 路径（无 `baldric_*`），
  含 `baldric/py.typed` 与 `data/` 资源。
- `baldric --version` → `baldric 0.3.0`；console entry point 解析为
  `baldric.coding.cli:app`。
- `uv.lock` 不变（`baldric==0.3.0`，同一来源）。
- 完整 `pytest`：行为与基线等价；唯一失败是 `test_tui_app.py` 已知的
  Windows TUI asyncio 偶发，重跑通过。
