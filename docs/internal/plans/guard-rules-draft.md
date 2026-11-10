# Guard 规则草案（供评审，未落地到 scripts/ 与 tests/）

> 本文件**不修改任何现有脚本/测试**，只是把 `kernel-refactor-plan.md` §4 + 阶段 6 的守卫规则，按现有
> `scripts/check_import_graph.py` 与 `tests/guards/test_import_boundaries.py` 的真实机制，写成**可评审的代码草案**。
> 评审通过后再逐条落进现场（受 AGENTS.md"禁止脚本批量改"约束，逐文件手工改）。

现有机制回顾（来自 `check_import_graph.py` 实读）：
- `RULES: tuple[(source_prefix, forbidden)]` — 前缀匹配，`source` 命中且 `imported` 以 `forbidden` 开头即违规。
- `AI_AGENT_SURFACE` + `scan_surface_violations()` — 白名单：`baldric_ai` 只许 import 这些 `baldric_agent.*` 模块，且 `from baldric_agent import X`（包根）也算违规（会拉起 session/storage/jsonl）。
- `main()` 汇总 `scan_violations + scan_surface_violations`，任一非空即 exit 1。
- guard 测试用"植入违规 → 断言被扫出"证明 gate 有牙（`test_scanner_detects_synthetic_violation`）。

---

## 一、`scripts/check_import_graph.py` 增补草案

### 1.1 新增前向/反向 layer 规则（对应 §4 双向守卫）

```python
RULES += (
    # ---- protocol 是最底层：不得依赖任何上层，也不得碰平台 I/O 模块 ----
    ("baldric_protocol", "baldric_agent"),
    ("baldric_protocol", "baldric_ai"),
    ("baldric_protocol", "baldric_coding"),
    ("baldric_protocol", "textual"),
    ("baldric_protocol", "rich"),
    ("baldric_protocol", "fcntl"),
    ("baldric_protocol", "msvcrt"),
    ("baldric_protocol", "tempfile"),
    # ---- 内核不得依赖 provider 实现（今天成立，钉死防反向）----
    ("baldric_agent", "baldric_ai"),
)
```

> 说明：`("baldric_ai", "baldric_agent")` **不加进 RULES**，因为 `baldric_ai` 今天就是靠 `AI_AGENT_SURFACE`
> 白名单机制约束（现状允许 5 个契约模块）。改造后 `AI_AGENT_SURFACE` 换名为 `AI_PROTOCOL_SURFACE` 指向
> `baldric_protocol.*`，届时 `from baldric_ai` import `baldric_agent.*` 会被 surface scanner 判违规（见 1.2）。
> **两套机制合起来 = 双向覆盖。**

### 1.2 `AI_AGENT_SURFACE` → `AI_PROTOCOL_SURFACE`（阶段 1 切换）

```python
# 改造后：provider 层只许依赖 protocol 契约，不得回流 agent / coding
AI_PROTOCOL_SURFACE: tuple[str, ...] = (
    "baldric_protocol.messages",
    "baldric_protocol.provider",
    "baldric_protocol.provider_events",
    "baldric_protocol.tools",
    "baldric_protocol.types",
)

def _is_on_surface(imported: str) -> bool:          # 改指向 protocol
    return any(imported == m or imported.startswith(m + ".") for m in AI_PROTOCOL_SURFACE)

def scan_surface_violations(root: Path = ROOT) -> list[ImportViolation]:
    ...
    for lineno, imported in _imports(tree):
        # 只关心 baldric_ai 是否 import 了「非 protocol 的 baldric_*」
        if not (imported.startswith("baldric_") and not _is_on_surface(imported)):
            continue
        violations.append(...)
```

> 注意：这条一旦收紧，`AI_PROTOCOL_SURFACE` **必须**覆盖 `baldric_ai` 真实用到的全部 protocol 模块
> （实读消息：messages/provider/provider_events/tools/types）。少列一个 → 误报；多列一个不存在的 → 用
> `test_ai_*_surface_is_declared_and_real` 那种"模块必须真存在"测试兜住。

### 1.3 阶段 6：产品/扩展不得绕过 protocol 直连 coding 内部实现

> 这是决定"可扩展"能否兑现的最后一道锁。现有 RULES 是"前缀禁用"，但产品层在 `baldric_coding` 内部，
> 不能简单"禁 baldric_coding → baldric_coding.session"。需要一条**白名单式**扫描（类似 surface scanner），
> 只针对**产品/扩展目录**。

```python
# 产品 / 扩展新代码：允许的 baldric_* 依赖白名单
EXTENSION_ALLOWED_SURFACE: tuple[str, ...] = (
    "baldric_protocol",              # 契约（含 session.entries/tree/jsonl）
    "baldric_coding.extensions.api", # 扩展唯一入口
)

# 产品/扩展代码所在目录（相对 src/）
EXTENSION_ROOTS: tuple[str, ...] = (
    "baldric_coding/extensions/builtins",   # 内建扩展
    # 将来 personal agent / 产品包也加进来
)

# 明确禁止扩展依赖的 coding 内部实现（非 api）
EXTENSION_FORBIDDEN_INSIDE_CODING: tuple[str, ...] = (
    "baldric_coding.session",   # SessionState / runtime 等
    "baldric_coding.tui",
    "baldric_coding.rendering",
    "baldric_coding.backends",
)

def scan_extension_violations(root: Path = ROOT) -> list[ImportViolation]:
    """扩展/产品代码不得直接依赖 coding 内部实现，只走 api.py + protocol。"""
    violations: list[ImportViolation] = []
    for path in sorted((root / "src").rglob("*.py")):
        if "__pycache__" in path.parts or "data" in path.parts:
            continue
        module = _module_name(path, root)
        if not any(module.startswith(r.replace("/", ".")) for r in EXTENSION_ROOTS):
            continue
        for lineno, imported in _imports(ast.parse(path.read_text(encoding="utf-8"))):
            if any(imported == f or imported.startswith(f + ".") for f in EXTENSION_FORBIDDEN_INSIDE_CODING):
                violations.append(ImportViolation(module, lineno, imported))
    return violations
```

> 取舍说明（需评审拍板）：
> - **白名单 vs 黑名单**：上面用"黑名单内部实现"（`EXTENSION_FORBIDDEN_INSIDE_CODING`），因为扩展目录本身就在
>   `baldric_coding` 里，不能整体禁 `baldric_coding`。若要求更严，可改"只许 `EXTENSION_ALLOWED_SURFACE` 白名单"，
>   但那会把当前合法的内部工具引用一次性炸出来（面可能很大）。**建议先黑名单，跑一次看真实违规量再决定是否升白名单。**
> - 这条要不要现在就落，取决于阶段 6 是否有真实产品/扩展目录；`builtins/subagents` 现在就在，可直接拿它验证。

---

## 二、`tests/guards/test_import_boundaries.py` 增补草案（证明 gate 有牙）

### 2.1 protocol 底层守卫

```python
def test_protocol_cannot_import_upper_layers_or_platform(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "baldric_protocol"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "leaky.py").write_text(
        "from baldric_agent.loop import run_agent_loop  # noqa: F401\n"
        "import fcntl  # noqa: F401\n",
        encoding="utf-8",
    )
    violations = scan_violations(tmp_path)
    assert ImportViolation(module="baldric_protocol.leaky", lineno=1, imported="baldric_agent.loop") in violations
    assert ImportViolation(module="baldric_protocol.leaky", lineno=2, imported="fcntl") in violations


def test_protocol_rules_are_declared() -> None:
    pairs = set(RULES)
    assert ("baldric_protocol", "baldric_agent") in pairs
    assert ("baldric_protocol", "baldric_ai") in pairs
    assert ("baldric_protocol", "baldric_coding") in pairs
    assert ("baldric_protocol", "fcntl") in pairs
```

### 2.2 内核不得反向 import provider（今天成立，钉死）

```python
def test_agent_cannot_import_provider_impl(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "baldric_agent"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "leaky.py").write_text("import baldric_ai  # noqa: F401\n", encoding="utf-8")
    assert ImportViolation(module="baldric_agent.leaky", lineno=1, imported="baldric_ai") in scan_violations(tmp_path)
```

### 2.3 运行时双向守卫（防 shim 残留的间接耦合，见 §4 补充）

> 静态 AST 看不见"通过 re-export shim 间接 import"。用**独立子进程** import 后查 `sys.modules`。

```python
import subprocess
import sys

def _imported_modules_after(import_expr: str) -> set[str]:
    code = f"import {import_expr}\nimport sys\nprint('\\n'.join(sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO_ROOT)
    assert out.returncode == 0, out.stderr
    return set(out.stdout.split())

def test_agent_runtime_does_not_load_provider() -> None:
    mods = _imported_modules_after("baldric_agent")
    assert not any(m == "baldric_ai" or m.startswith("baldric_ai.") for m in mods), \
        "importing baldric_agent pulled in baldric_ai (indirect coupling)"

def test_provider_runtime_does_not_load_agent() -> None:
    mods = _imported_modules_after("baldric_ai")
    assert not any(m == "baldric_agent" or m.startswith("baldric_agent.") for m in mods), \
        "importing baldric_ai pulled in baldric_agent (shim leak / reverse dependency)"
```

> 注意：需要 `PYTHONPATH=src`（或已 `uv pip install -e`）。测试里用 `sys.executable -c` + `cwd=REPO_ROOT` + 设
> `env["PYTHONPATH"]="src"` 更稳。**这条在 shim 期会真实炸**（因为 shim 让 agent 的模块 re-export protocol，
> 而 protocol 不 import ai，应该不炸；但若有人反过来 import 就会炸）——正是要的。

### 2.4 阶段 6：扩展不得绕过 protocol

```python
def test_extension_cannot_import_coding_internals(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "baldric_coding" / "extensions" / "builtins" / "demo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "leaky.py").write_text(
        "from baldric_coding.session import SessionState  # noqa: F401\n", encoding="utf-8"
    )
    violations = scan_extension_violations(tmp_path)
    assert ImportViolation(
        module="baldric_coding.extensions.builtins.demo.leaky", lineno=1,
        imported="baldric_coding.session",
    ) in violations
```

---

## 三、评审要点（这版草案需要你确认的 4 件事）

1. **`AI_PROTOCOL_SURFACE` 的模块清单**是否恰好等于 `baldric_ai` 真实用到的 5 个 protocol 模块
   （实读：messages/provider/provider_events/tools/types）。多列/少列都需在落地时用"模块必须存在"测试兜。
2. **阶段 6 用黑名单还是白名单**：建议先黑名单（`EXTENSION_FORBIDDEN_INSIDE_CODING`），跑一次看
   `builtins/subagents` 的真实违规量，再决定是否升白名单。
3. **运行时守卫的子进程成本**：每加一条守护测试要 spawn 一个 python 子进程；可以先只加两条（agent/protocol、
   ai/agent），TUI 层面不纳入以免拖慢。
4. **`baldric_protocol` 是否算"包根 import 也违规"**：像 `from baldric_agent import X` 一样，是否需要禁止
   `from baldric_coding import X`（包根会拉起 session/tui）。建议对 protocol 自身不设这条（它没有重 init），
   但对"扩展 → baldric_coding 包根"要设。

---

## 四、落地顺序（评审通过后）

1. 先改 `scripts/check_import_graph.py`（加 RULES 条目 + surface 改名 + `scan_extension_violations`），
   **逐条手改**，每改跑一次 `uv run python scripts/check_import_graph.py` 看是否误杀现状。
2. 再改 `tests/guards/test_import_boundaries.py` 加对应"植入违规"测试，证明每条新规则有牙。
3. 故意各植入一次违规（protocol import agent、agent import ai、扩展 import session）验证 CI 真的炸，
   然后撤掉植入。
