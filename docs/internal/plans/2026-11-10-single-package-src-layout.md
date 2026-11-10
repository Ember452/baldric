# 单包 src 布局迁移计划

> **给执行 agent：** 本计划按所有者的直接指令（"开一个新分支，将该做的做完"）由 Lead 在单个
> session 内联执行。步骤用勾选框跟踪。批量改写遵循 AGENTS.md 的逃生通道：确有必要的批量改写 → 独立提交 → 先 dry-run 评审。

**目标：** 把五个顶层包 `src/baldric_{protocol,ai,agent,coding,mcp}`
合并为一个导入包 `src/baldric/{protocol,ai,agent,coding,mcp}`，与发行名 `baldric` 一致，行为零变化。

**架构：** 纯机械改名。目录移动用 `git mv`（历史
保留）；导入/字符串/注释改名用带强制 dry-run 评审的 token 级 Python 脚本；配置、门脚本逻辑与路径段修复手工进行；棘轮基线重新生成并逐项 diff 评审。层边界仍由 `check_import_graph.py` 以翻译后的前缀强制。

**技术栈：** Python 3.12、uv、hatchling、pytest、ruff、mypy、项目棘轮。

**规格：** 所有者在对话中的决定（2026-11-10）：单一 `baldric` 导入
根对单一发行版是更常规的布局；pre-1.0（0.3.0）是动手的便宜时机。`AGENTS.md` 硬规则适用。

## 全局约束

- 行为零变化：不重新格式化、不做包映射之外的改名、不
  弱化断言、不删/跳测试。
- 包映射（精确）：`baldric_protocol→baldric.protocol`、`baldric_ai→baldric.ai`、
  `baldric_agent→baldric.agent`、`baldric_coding→baldric.coding`、`baldric_mcp→baldric.mcp`。
- 发行名保持 `baldric`；版本保持 `0.3.0`；`uv.lock` 不得变化。
- 历史记录**不**改写：`dev-notes/**`、`plans/**`、
  `docs/superpowers/**`（本新计划除外）、`src/**/data/release-notes/**`、
  gitignore 的产物。它们刻意用旧名描述过去的状态。
- 指引文件编辑尽可能字节等长
  （`baldric_x` → `baldric.x` 与 `src/baldric_x/` → `src/baldric/x/`
  等长），guidance 棘轮不 `--init` 增长即保持绿。
- 已知 Windows 基线：`trust/policy.py` +
  `session/storage.py` 的 14 个 mypy 错误；约 121 个 POSIX 跳过。它们必须仍是仅有的 mypy 错误。
- 分支 `refactor/single-package-src-layout` 上一次原子提交。

## 盘点（2026-11-10 已核实）

- src：1432 行绝对导入；3 处字符串引用（`files("baldric_coding")` ×2——
  运行时关键资源锚；`source="baldric_coding.system_prompt"` 标签）。
  src 中无 `import_module`/`__import__`。extension 加载器用合成模块
  名（`spec_from_file_location`），不受影响。themes 里的 `files(__package__)` 自动适配。`version.py` 读发行元数据——不受影响。
- tests：导入 + 点分字符串（monkeypatch/logger/import_module）+ 13
  行路径段需要手工两段修复（清单在 Task 5）。
- scripts：`check_import_graph.py`（仅字符串前缀；`_module_name`
  与路径无关）、`check_structure.py`（扇出根集合 + 成员判断）、
  `check_agent_guidance.py`（发现深度 `src/*` → `src/baldric/*`）、
  `generate_models.py`（导入 + 一个斜杠路径）。`check_suppressions.py`、
  `check_move_only.py`、`verify_versions.py` 无需变更。
- config：`pyproject.toml` 4 处（entry point、coverage omit、hatch packages、
  mypy packages）。`.pre-commit-config.yaml` 用通用 `^src/`——不变。
  `.github/**`——无引用。
- docs/site：根 `AGENTS.md`/`README.md`/`CONTRIBUTING.md`、3 个 scoped `AGENTS.md`、
  `landing.html`、`website/content/**`（8 个文件）、`website/src/data.ts`（release
  notes 路径——功能相关）、`website/src/components/Home.astro`、
  `website/data/roadmap.yaml`（1 行）、打包的 `src/baldric_coding/data/docs/**`
  与 `data/examples/extensions/*.py`。
- 受跟踪的项目 extension `.baldric/extensions/ask_user_question.py`——导入
  必须改名，否则本地 extension 失效。
- `py.typed`：每个旧包一个标记（5 个）。新布局：在
  `src/baldric/py.typed` 放一个标记（PEP 561 包根）；删除五个子包副本。

---

### Task 1：基线证据（DONE）

- [x] `main` @ 9f77fa3 干净工作树；已建分支 `refactor/single-package-src-layout`。
- [x] 静态门全绿：ruff check、ruff format（466 文件）、import-graph、
      structure、suppressions、guidance、versions（0.3.0）。
- [x] mypy：恰好 2 个文件的 14 个已知 Windows 错误。
- [ ] 快速套件 `uv run pytest -q --ignore=tests/coding/tui`——记录结果。

### Task 2：目录移动 + 包根

**文件：**
- 移动：`src/baldric_protocol` → `src/baldric/protocol`（ai/agent/coding/mcp 同理）
- 新建：`src/baldric/__init__.py`（仅 docstring，无再导出）
- 移动：`src/baldric/protocol/py.typed` → `src/baldric/py.typed`
- 删除：`src/baldric/{ai,agent,coding,mcp}/py.typed`（单一根下冗余）

- [ ] `New-Item -ItemType Directory src/baldric` 然后五条 `git mv`。
- [ ] `git mv` 一个 py.typed 到根；`git rm` 其余四个。
- [ ] 写带一行 docstring 的 `src/baldric/__init__.py`。
- [ ] 验证：`git status` 显示 rename；`Get-ChildItem src/baldric` 显示 5 个目录
      + `__init__.py` + `py.typed`。

### Task 3：迁移脚本 + dry-run 评审

**文件：**
- 新建：`D:\DEVELOP\Solis\_migrate_baldric_single_package.py`（仓库外，
  一次性草稿约定；不提交）
- 输出：`D:\DEVELOP\Solis\_migration_report.txt`

脚本契约：
- `.py` 遍（src、tests、scripts、examples、.baldric/extensions）：tokenize；
  经映射替换确切的 NAME token；按有序规则改写 STRING/FSTRING_MIDDLE/COMMENT
  token 文本：
  1. `src[/\]baldric_x` → `src/baldric/x`
  2. `baldric_x/` → `baldric/x/`
  3. `baldric_x.` → `baldric.x.`
  4. 裸 `baldric_x` → `baldric.x`（标 REVIEW：可能是路径段）
- 文本遍（根 AGENTS/README/CONTRIBUTING/landing.html、src/**/*.md、
  website/content/**/*.md、website/src/data.ts、Home.astro、roadmap.yaml）：
  原文应用同样四条规则。
- 编辑范围之外保字节；保行尾与行数；每份改写的 .py 写盘前必须 `ast.parse` 成功。
- dry-run（默认）写完整报告；`--apply` 写文件。

- [ ] 跑 dry-run；通读完整报告；评审每条 REVIEW 标记的裸字符串与
      遗留清单（预期遗留：函数名含 `baldric_` 子串，如
      `test_baldric_coding_public_surface_is_frozen`）。
- [ ] 核对数量：约 250 个 src 文件，tests/scripts/examples 被触及；报告中
      没有 release-notes/dev-notes/plans/docs-superpowers 文件。

### Task 4：应用 + 配置编辑

- [ ] 跑 `--apply`；重跑 dry-run → 报告必须显示零变化。
- [ ] `pyproject.toml`（4 处手工编辑）：
  - `baldric = "baldric.coding.cli:app"`
  - `omit = ["src/baldric/coding/data/*"]`
  - `[tool.hatch.build.targets.wheel] packages = ["src/baldric"]`
  - `[tool.mypy] packages = ["baldric"]`
- [ ] `scripts/check_structure.py`：扇出成员判断
      `target.split(".")[0] in project_roots` → 前缀匹配
      （`target == root or target.startswith(root + ".")`），根集合已被脚本
      翻译为 `{"baldric.agent","baldric.ai","baldric.coding"}`。
      保持指标语义一致（protocol/mcp 照旧排除）。
- [ ] `scripts/check_agent_guidance.py`：发现 `(ROOT/"src").glob("*")` →
      `(ROOT/"src"/"baldric").glob("*")`（scoped 文件深了一层）。

### Task 5：路径段修复（手工，13 行）

脚本之后这些读作 `"src" / "baldric.x"`（错一段）；逐个改为
`"src" / "baldric" / "x"`：

- [ ] `tests/test_package_metadata.py:8`
- [ ] `tests/helpers/subagents_shared.py:21`
- [ ] `tests/guards/test_session_state_write_ratchet.py:25`
- [ ] `tests/guards/test_provider_helpers_single_source.py:15`
- [ ] `tests/guards/event_union.py:20,21`
- [ ] `tests/guards/test_import_boundaries.py:67,83,95,137,152,166`
- [ ] `tests/coding/rendering/test_theme_schema.py:30`
- [ ] 验证：grep tests 找 `/ "baldric\.` → 零命中。

### Task 6：环境 + 基线

- [ ] `uv sync`（对新布局重建 editable 安装）；`uv.lock` diff 必须为空。
- [ ] 重新生成：`uv run python scripts/check_structure.py --init`、
      `check_suppressions.py --init`、`check_agent_guidance.py --init`。
- [ ] 逐个评审基线 diff：structure/suppressions = 纯键改名、值相同；guidance = 键改名、字节大小相同。
- [ ] 冒烟：`uv run python -c "import baldric, baldric.coding, baldric.ai,
      baldric.agent, baldric.protocol, baldric.mcp"`；`uv run baldric --version`。

### Task 7：全量验证（跨包重构 → 全量层）

- [ ] `uv run ruff check .` 与 `uv run ruff format --check .` → 绿。
- [ ] `uv run mypy` → 恰好 14 个已知 Windows 错误，新路径。
- [ ] `uv run python scripts/check_import_graph.py` → OK。
- [ ] 三个棘轮 + `verify_versions.py` → OK。
- [ ] `uv run pytest`（全量，约 4 分钟）→ 与基线相同的通过/跳过曲线。
- [ ] `uv build` → wheel 含 `baldric/coding/data/...`、`baldric/py.typed`、
      entry point `baldric.coding.cli:app`；无 `baldric_*` 路径。
- [ ] 资源冒烟：`uv run python -c "from importlib.resources import files;
      print(files('baldric.coding').joinpath('data/catalog.toml').read_text()[:80])"`。

### Task 8：日志 + 原子提交

- [ ] 加 `dev-notes/architecture/single-package-layout.md`：what/why/how、
      旧→新映射、刻意保留旧名的对象（历史记录）、
      验证证据、面向第三方 extension 的 extension-API 破坏注记
      （`from baldric_coding.extensions import ...` → `from baldric.coding.extensions import ...`）。
- [ ] `git add -A`（仅仓库）；检查 `git status` + `git diff --stat` 尾部；
      确认无草稿文件、无 uv.lock 变化、无历史文档搅动。
- [ ] 提交：`refactor: consolidate five baldric_* packages into src/baldric/`，
      正文描述机械改名、门证据与 0.3.0 的公开导入破坏。
- [ ] 带证据向所有者汇报；分支留待评审（未经询问不合并）。
