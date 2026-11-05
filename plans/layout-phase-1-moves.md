# 蓝图对齐第一阶段实施计划：只移动，不拆分

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现本计划。步骤用 `- [ ]` 复选框跟踪。

**Goal:** 把 `baldric_coding` 中所有可证明"零行为变化"的文件移动（O/A/B 类）搬到蓝图位置，且完全不触碰任何内部逻辑拆分。

**Architecture:** 两阶段策略的第一阶段。本阶段只允许"换目录 + 换文件名 + 改 import"三种改动；7 个需要 1:N 拆分的文件明确留在原地不动。风险控制的支点不是"更小心"，而是**每个提交只含一种性质的变化**，以及用 git 的 `R100` 重命名检测把"零行为变化"变成可机器验证的事实。

**Tech Stack:** Python 3.12+、uv、pytest、mypy（`strict = true`）、ruff（line-length 110）、git。

**Spec:** `dev-notes/architecture/target-project-layout.md`（蓝图）。执行前先读它，特别是「阅读规则：这是一张蓝图」「两条承重的规则」「蓝图尚未成为现实的阻碍」三节。

**本阶段明确不做：** 任何文件内部的逻辑拆分。7 个 C 类文件（`tools.py`、`commands.py`、`session.py`、`session_export.py`、`rpc.py`、`tui/app.py`、`tui/widgets.py`）中，除 `rpc.py` 外均按规则 1.1 “停车”进目标包（单文件 1:1 移动+改名，零逻辑改动）；包内切分属于第二阶段。`tui/themes/` 虽在机械分类里被判为 1:N，但它是一个**包目录的整体移动**（内含的 3 个 `.json` 随 `__init__.py` 一起走），不需拆内容，所以归 Task 3 执行。

## 已确认的范围决定与环境约束

执行者不要反复评估这几条，它们已由项目负责人确认：

1. **范围只含 `baldric_coding`。** `baldric_ai`（根上 20 个 `.py`）与 `baldric_agent`（11 个）本阶段**不动**，尽管蓝图给了它们目标子包。
2. **测试文件不搬位置。** `tests/` 的 91 个文件在本阶段保持平铺，只改 import 路径。测试树镜像 src 是后续独立任务。
3. **不做旧路径兼容 shim。** 不在旧路径留转发模块。漏改的引用应当以 ImportError 直接暴露，由 `mypy --strict` 与测试里的深层 import 兜住（**具体数量不写在本计划里**，由 Task 2 现场扫描得出并记台账；上一版写的 241 已证实因递归不完全而偏低）。
4. **交付形态：单分支多提交，一个 PR。** 分支 `refactor/layout-phase-1` 从 `main` 起；每个簇一个 commit；全部任务完成后开一个 PR。CI 只在 PR 上跑，因此**每个 commit 的本地三件套全绿是唯一的实时反馈来源——这条不能省**。

### 蓝图里有、但本阶段故意不着落的条目

下列五项在蓝图中占位，但**不属于本阶段**。遇到它们请绕过，不要现场扩范围：

| 条目 | 原因 |
|---|---|
| `baldric_ai/net/`、`baldric_ai/catalog/` | 属于 `baldric_ai`，范围决定 1 已排除 |
| `mcp/` | 蓝图自标“when it lands”，功能本身还不存在 |
| `security/` | 蓝图自标“when needed”，沙箱能力尚未开做 |
| `extensions/` 下的 `package_manager.py` | 蓝图自标“预期新增，今天不存在” |
| `examples/` 双拷贝去重（蓝图阻碍表的一项） | 它是仓库根问题，不是 `baldric_coding` 内部的移动；**单独开一个小型 PR 做**，混进本分支只会把 PR 的评审边界弄浑 |

5. **命令环境：Windows PowerShell。** 本计划所有命令以 PowerShell 形式书写（**PowerShell 5.1 不支持 `&&`，多语句用 `;`**）。若环境里有 Git Bash，可用其等价形式，但两者语义必须逐字对应。遇到命令报错时**不要现场自创扫描方式**，而是把失败原文记台账并停下报告——这正是第 0 节要防的事。

---

## 0. 本计划的使用方式（先读这一节）

**本计划里的文件清单是"参考起点"，不是权威来源。** 它由 `9c1285d` 之后的 main 分支一次扫描得出，随代码演化会过期。执行者必须遵守两条：

1. **先重跑扫描，以扫描结果为准。你在没有全面考虑清楚前，绝对不允许动手，严禁自己去写什么计划外的功能。每次动手前，问自己，我考虑清楚了吗，是否为了偷工减料只看了部分文件** Task 2 定义了扫描程序与判定判据。Task 2 产出的映射表是本阶段的权威清单；若它与本计划某任务的列表冲突，**按扫描结果执行，并在该任务下注明差异**。
2. **判据是稳定的，清单不是。** 本计划的分类判据（O/A/B/C 四档）、许可/禁止清单、移动配方 M 是决策依据；具体哪些文件属于哪一档属于事实，必须现扫。

不需要详细到"每一行怎么改"的部分：import 改写本身、以及扫描新发现的文件——由你按判据自行决定并执行，然后在 commit message 与台账里留下你做了什么判断。

---

## Global Constraints

- 目标包名：`baldric_ai`、`baldric_agent`、`baldric_coding`（三层划分不变）
- Python 下限：`requires-python = ">=3.12"`
- 行宽：110（ruff `line-length`）
- 类型：`mypy` `strict = true`，`packages = ["baldric_ai", "baldric_agent", "baldric_coding"]`
- 入口点：`baldric = "baldric_coding.cli:app"` —— **本阶段绝不改动**，`cli.py` 留在根
- `py.typed`：三个包根各一份，**必须留在包根**，不可进任何子目录
- 包资源：`data/` 随所属模块一起走；主题 `.json` 随 `themes/` 一起走
- 提交信息：英文 Conventional Commits
- 测试：全程走 `uv run pytest`；**断言一字不动**，只允许改 import 行
- 每个任务结束时 `uv run pytest`、`uv run mypy`、`uv run ruff check .` 三项全绿才允许进入下一任务
- 禁止 `git add -A` / `git add .`；只显式 `git add <path>`

---

## 1. 分类判据（决定一个文件属于哪种操作）

对每个源文件依次回答三个问题，第一个命中的结论生效：

| 判据 | 类别 | 本阶段处理 |
|---|---|---|
| 蓝图目标位置 = **多个**文件/目录（1:N 映射） | **C 拆分** | **不拆分**。若与新包无同名冲突则留在原地（如 `rpc.py`）；若有冲突则按【规则 1.1】整文件停车进包（属 A/B 操作）。两者都算本阶段完成。 |
| 蓝图目标目录 = 当前目录 且 文件名相同 | **O 无操作** | 不动 |
| 文件名相同，只是目录变了 | **A 纯搬移** | 执行，零行为变化 |
| 目录变 **且** 文件名变 | **B 搬移+改名** | 执行，零行为变化（改名只影响 import 路径） |

补充规则：

- **判据不用行数。** 参考项目在 1,500–4,400 行区间很常见，行数不是标准偏差。`provider_config.py` 2,545 行但目标 `providers/config.py` 只有一个文件 → B 类。
- **判据不用"感觉太大"。** 唯一标准是映射基数。
- 若某文件你判定为 C 但本计划列为 A/B，**以你的判定为准并把差异记进台账**——这说明蓝图或本计划有一处错了。

**规则 1.1 — 同名冲突用“停车”解决，不用拆分解决。**

新建包 `X/` 时，若根上存在同名模块 `X.py`，Python 不允许 `baldric_coding.X`（模块）与 `baldric_coding/X/`（包）共存。此时把该文件**整文件移动进包里**：

```text
session.py         → session/session.py        （蓝图目标位置，1:1）
session_export.py  → session/export.py         （本阶段不建 session/export/ 目录）
tools.py           → tools/registry.py         （蓝图目标位置，1:1）
commands.py        → commands/registry.py      （蓝图目标位置，1:1）
context.py         → context/project.py        （蓝图目标位置，1:1）
```

这仍然是 A/B 类（一个源文件 → 一个目标文件，内容零改动），不违反“只移动”的约定。第二阶段的拆分发生在包内部，那时周围结构已经稳定。**遇到同名冲突不要停下等指示，直接按本规则停车并记台账。**

---

## 2. 许可 / 禁止清单（"移动导致的必要改动"的边界）

**允许出现的变化：**

- 源码里的 `from baldric_coding.X import Y` 路径改写
- 测试文件里同类 import 路径改写
- `baldric_coding/__init__.py` 门面里的 re-export 路径更新（只改路径，不改导出集）
- 新建包目录及其 `__init__.py`（**必须是空的**，见规则 2.1）
- 包资源目录 / `data/` 的相对位置随模块调整
- `.gitignore` 之类的基础设施微调（仅 Task 1 授权的两条）

**禁止出现的变化（一律推迟到第二阶段）：**

- 拆分文件、移动符号、重排函数或类顺序
- 修改函数签名、默认值、返回值形状、类型注解内容
- 重命名任何符号（只有模块/包路径可改）
- 修 bug、清理死代码、"顺手"改注释或格式
- 修改任何测试断言
- **对模块名做全局文本替换（blanket replace）。** 同名模块在仓库里指向不同东西：已核实根上 `local_backends.py` 与 `tui/local_backends.py` 各一份（`project_trust.py` 同样两份），对 `project_trust` 做全文替换会把 `baldric_coding.tui.project_trust` 错改成 `baldric_coding.tui.trust.policy`。**硬规则：只按“完整 dotted 路径”逐条改写，且作域限于本簇目标；每改一处前对照 4.2 扫描出的引用清单。**
- 增删 `baldric_coding/__init__.py` 的公开导出集

**规则 2.1 — 新建包的 `__init__.py` 只写 docstring。**

现有 8 个 `__init__.py` 全部是急加载（`baldric_coding/__init__.py` 含 23 个顶层 import）。平级模块之间潜在的循环今天靠 import 顺序侥幸存活；一旦新建的子包 `__init__.py` 也去 eager import 其子模块，父包初始化会先于子模块执行，把潜在环变成 `partially initialized module` 硬错误，且依赖启动入口、本地不易复现。

所以：新目录 `auth/`、`config/`、`session/` 等的 `__init__.py` 内容 = 一行 docstring，结束。对外便利入口继续只留在 `baldric_coding/__init__.py` 这一处。

---

## 3. 移动配方 M（每个移动任务的标准操作序列）

对每个簇执行以下 7 步。**步骤顺序不可调换**，第 3 步的"先失败"是本计划最重要的单一措施。

- [ ] **M-1 记录起点。** `git rev-parse HEAD` 记入台账；确认 `uv run pytest -q` 全绿。若已红，停下报告，不要带着红灯搬。
- [ ] **M-2 生成该簇的 import 改写清单。** 用第 4 节的扫描命令得到"谁引用了本簇的模块"，输出用 `Set-Content` 写入 `$env:TEMP` 下的临时文件，**不要写进仓库**。
- [ ] **M-2.5 把引用闭包算全（本阶段最重要的批次规则）。** 一个提交的单位**不是目标包，而是引用闭包**：

```text
提交内容 = 本簇被搬的文件
         ∪ 所有引用这些文件的文件（即使它们属于别的簇、别的包）
         ∪ tests/ 里对应的 import
         ∪ baldric_coding/__init__.py 的门面行
```

实测跳簇引用是常态不是例外：`paths.py` 有 **30 个**外部引用者，`credentials.py` 与 `resources.py` 各 13 个，`commands.py` 8 个，`session.py` 7 个。**跳簇的引用者只改 import 行，不碰它们的其他内容。**

不允许把引用者推迟到“它所属的那个任务”里再改。理由：一旦允许中间提交是红的，`mypy --strict` 与 M-3 的故意红灯同时失效，此后每个失败都无法区分“本次搬坏了”和“上个任务欠的账”——那正是 agent 开始乱改代码的起点。
- [ ] **M-3 先改测试的 import，不改任何源码。** 只改 `tests/**` 里的路径到新位置。跑测试。
      **预期结果：`ModuleNotFoundError` / `ImportError` 大面积失败。** 这是正确状态，不是事故。它证明安全网仍然连着。
      若此时仍全绿：先查该簇的真实测试覆盖再下结论。两种分岔：
      - 该簇**有直接测试文件**（按 4.2 扫描能列出）却仍全绿 → 说明路径没真正改到或测试未收集该模块，**停下查清**；
      - 该簇只经门面被间接使用（如 `observability`、`utils` 这类低覆盖簇）→ 全绿是**正常状态**，记台账后继续，不要停下等人。
- [ ] **M-4 执行 `git mv` + 源码 import 改写。** 一次完成本簇全部文件的移动与路径修正，同时更新 `baldric_coding/__init__.py` 的 re-export 路径与新包的空 `__init__.py`。
- [ ] **M-5 证明零行为变化。** 见第 5 节三条校验，逐条跑。
- [ ] **M-6 三件套全绿。** `uv run pytest`、`uv run mypy`、`uv run ruff check .`，外加 `uv run ruff format --check .`。
- [ ] **M-7 提交。** 一个簇一个 commit。Windows 改名（`local_backends.py → backends.py` 这类）走两步：`git mv a.py tmp_rename.py; git mv tmp_rename.py b.py`，避免 NTFS 大小写不敏感导致静默半成功。

---

## 4. 扫描程序（Task 2 用它生成权威映射表）

```powershell
# 4.1 枚举 coding 包内全部源文件（排除构建产物与打包数据）
Get-ChildItem src\baldric_coding -Recurse -Filter *.py |
  Where-Object { $_.FullName -notmatch '\\__pycache__\\|\\data\\' } |
  ForEach-Object { $_.FullName.Replace("$PWD\", '') } | Sort-Object

# 4.2 谁引用了某个模块（改名/搬移前必查，含字符串形式与文档引用）
$targets = Get-ChildItem src, tests, scripts, website, dev-notes -Recurse -Include *.py, *.toml, *.md -File -ErrorAction SilentlyContinue
Select-String -Path $targets.FullName -Pattern 'baldric_coding\.MODULE_NAME' |
  ForEach-Object { "$($_.Path):$($_.LineNumber)  $($_.Line.Trim())" }

# 4.3 动态 import 与资源路径（搬移的隐形雷，每簇必查）
Select-String -Path (Get-ChildItem src -Recurse -Filter *.py).FullName `
  -Pattern 'importlib|spec_from_file_location|files\(' |
  ForEach-Object { "$($_.Filename):$($_.LineNumber)  $($_.Line.Trim())" }

# 4.4 门面导出集快照（用于 M-5 证明导出集没变）
# 注意：必须用 __all__，绝对不能用 dir(m)。dir() 会把子模块/子包名也算进去
# （实测 186 个名字里 46 个是模块/包），新建任何子包都会让它必然变化。
$facadeBefore = Join-Path $env:TEMP 'facade_before.txt'
uv run python -c "import baldric_coding as m; print('\n'.join(sorted(m.__all__)))" | Set-Content $facadeBefore
```

Task 2 的产出格式（写成 `dev-notes/architecture/layout-mapping.md`，供后续每个任务与收尾复核引用）：

```text
| 现路径 | 目标路径 | 类别 | 判定依据 | 备注（资源随动/字符串引用/待决） |
```

扫描时必须一并记录三类"隐形引用"，它们是 mypy 抓不到的漏改源：

1. `extensions/loader.py` 用 `spec_from_file_location` 按文件路径加载用户扩展 —— 影响扩展的**发现路径**约定，不影响内部模块名
2. `importlib.resources.files` 出现处（`catalog_loader.py`、`models_dev.py`）—— 依赖 `data/` 相对包路径
3. `dev-notes/`（24 处）与 `website/content/`（9 处）里硬编码的模块路径 —— 属于文档失真，不阻断执行，但 Task 12 必须收口

---

## 5. 零行为变化的三条校验

- [ ] **重命名检测。** `git diff --find-renames --stat HEAD~1` 中被搬文件应显示 `R100`（内容完全未变）；带 import 修正的会是 `R9x`。
- [ ] **变化范围。** 跑 `uv run python scripts/check_move_only.py HEAD`（其规格见 Task 1 Step 3）。出现任何一个非 import 块的增删行即为配方违例，回退重做。手工核对时用 `git diff --find-renames -U0 HEAD~1`。
- [ ] **导出集不变。** 重跑 4.4 得 `facade_after.txt`，再跑
      `Compare-Object (Get-Content $facadeBefore) (Get-Content $facadeAfter)`，**输出必须为空**。
      这条守住"门面 `__all__` 冻结"。**不得用 `dir(m)` 做此检查**（理由见 4.4 注释）。

## 5.1 失败分诊（M-4 之后出现任何失败时）

前提：**M-1 已确认基线全绿，所以 M-4 之后的任何新失败必然是本次搬移造成的。** 不存在“是因为别的文件还没搬”这种原因——那只能说明闭包没算全。把每个失败归入三类之一：

| 类型 | 特征 | 允许的处置 |
|---|---|---|
| **A 路径没改完** | `ModuleNotFoundError` / `ImportError`，报的是旧模块名或旧路径 | 补改那个引用者的 import 行。**这是闭包漏了，不是“该等后续任务”** |
| **B 新包成了急加载** | `cannot import name` / `partially initialized module` / 指向包属性的 `AttributeError` | 把新包 `__init__.py` 改回**只有 docstring**（规则 2.1）。不改逻辑，不加 `sys.modules` hack |
| **C 其他任何失败** | 断言值不符、行为差异、超时、平台差异…… | **停下。不改产品代码，不改测试，不 skip/xfail。** 原样记入台账（失败名 + 报错原文 + 出现于哪次提交）并报告等人 |

判不准属于哪一类，一律按 C 处理。**目标不是“让测试变绿”，而是“能解释每个失败为什么绿”。**

## 5.2 永久禁止的动作（为了绿而做这些就是违规）

- 新增转发模块 / shim / `sys.modules` 注册 / `sys.path` 修补
- 修改任何测试断言、参数化取值，或加 `@pytest.mark.skip` / `xfail`
- 改动 `baldric_coding/__init__.py` 的导出集内容或名字（只允许改路径）
- 为绕开环而把顶层 import 改成函数内延迟 import（**唯一例外**：`commands.py` 里已有的那一处保持原样，不新增此类）
- 用 `# type: ignore` 压住 mypy 报错
- 重命名符号、拆函数、顺手修 bug

## 5.3 只有结构检查允许“预期非空”

**测试永远应当全绿。唯一允许非空/非绿信号的是 grep 与结构检查项**，例如 Task 9 的 `backends/ → tui` 方向检查：若移动前就已有引用，那是既有违反，记台账归入第二阶段，不由本阶段修。Task 3 的第 2 条反向 grep 非空也属于这一类。

---

## 6. 台账

在 `dev-notes/architecture/layout-migration-log.md`（Task 1 创建）里为每个簇记一行：起点 commit、扫描差异、执行了配方 M 的哪几步、三条校验结果、commit hash。**这张表是本阶段唯一的过程产物**，第二阶段的入口条件由它判定。

---

## Task 1: 装安全网与基线

**Files:**
- Create: `dev-notes/architecture/layout-mapping.md`（空表头即可，Task 2 填）
- Create: `dev-notes/architecture/layout-migration-log.md`
- Create: `scripts/check_move_only.py`（第 5 节"变化范围"校验的自动化）
- Modify: `.gitignore`（加 `.venv*/`；本计划唯一授权的基础设施改动）
- 提交：`dev-notes/architecture/target-project-layout.md` 与 `dev-notes/architecture/index.md`（蓝图已写好但未提交）

**Produces:** `scripts/check_move_only.py <commit-ish>` —— 退出码 0 表示该提交的增删行全部位于 import 语句内；非 0 时打印违例行。后续所有任务的 M-5 调用它。

- [ ] **Step 1: 确认基线**

```powershell
git checkout main; git pull --ff-only
uv sync --dev
uv run pytest -q
```
Expected: 全绿。若红，停止并报告，不要开始任何移动。

- [ ] **Step 2: 提交蓝图文档与本计划**

**已执行（2026-11-05）：** 蓝图与 `index.md` 指针已在 `7b2d30c` 提交，本计划在 `c94c7c1` 提交，`AGENTS.md` 在 `749611a` 单独提交；v0.2.1 发布提交为 `444befe`。**执行到这一步时先跑 `git status`，若这些文件已不在未提交列表里，直接跳过本步并在台账记一句“已前置提交”。**

当时用的命令（仅当文件仍未提交时才跑）：

```powershell
git add dev-notes/architecture/target-project-layout.md dev-notes/architecture/index.md plans/layout-phase-1-moves.md
git commit -m "docs(architecture): add target project layout blueprint and phase 1 move plan"
```

（本计划文件 `plans/layout-phase-1-moves.md` 也在这里提交。它住在 `plans/` 是故意的——仓库现有惯例如此，`602-built-in-local-inference.md` 就在那里。）

- [ ] **Step 3: 写 `check_move_only.py`**

要求：解析 `git diff --find-renames -U0 <commit>`，逐 hunk 判断增删行是否全部属于 **import 块**（不是“import 行”）。不引入新依赖（只用 stdlib）。

必须处理四个已预见的误报源（这些都是真实会踩的坑，不是保险起见）：

1. **区分 diff 元数据与 hunk 内容行。** `diff --git a/x b/y`、`index abc..def 100644`、`similarity index 92%`、`rename from/to`、`--- / +++` 这些不是内容变化，不能计入违例。
2. **多行 import 的整块。** `from baldric_coding.x import (` 后面的 `    CommandRegistry,` 这类续行，以及闭括号 `)` ——**全部算 import 块内合法**。只按行首是否为 `import`/`from` 判定会把重新折行的门面 import 误报。
3. **删除侧也要宽恕。** 删掉的是一个旧 import 块时，它的续行同样合法；不要只宽容新增侧。
4. **`from __future__ import annotations` 是合法行，但它会作为新建文件的**内容行**出现在 diff 里**——对于新建的空 `__init__.py`，允许的行只有 docstring 行与空行（规则 2.1），脚本要把新建包 `__init__.py` 单独归类。

例外范围：**`baldric_coding/__init__.py` 这个门面文件只允许 import 行变化**（第 2 节禁止清单）；其余文件若因移动而必须修正 `importlib.resources` / `__file__` 路径表达式（仅 Task 3 预告的主题 `.json` 加载情形），属于移动导致的必要改动，**允许，但必须在台账里逐行声明理由**，否则一律判违例。

自检（Task 1 Step 4）：造一个含函数体改动的临时提交，验证脚本能正确拒绝。

- [ ] **Step 4: 用一次真实提交自检该脚本**

拿 Step 2 的 commit 跑：`uv run python scripts/check_move_only.py HEAD`。文档提交没有 import 变化，脚本应报"无违例"。再故意本地造一个含函数体改动的测试提交验证它会正确拒绝（验证后 `git reset` 掉）。

- [ ] **Step 5: 建两个台账文件 + 记录起点**

`layout-mapping.md` 写入第 4 节的表头；`layout-migration-log.md` 记录 `git rev-parse HEAD` 作为 Phase-1 起点。

- [ ] **Step 6: Commit**

```powershell
git add scripts/check_move_only.py .gitignore dev-notes/architecture/layout-mapping.md dev-notes/architecture/layout-migration-log.md
git commit -m "chore(layout): add move-only guard script and migration ledger"
```

---

## Task 2: 全量扫描，产出权威映射表

**Files:**
- Modify: `dev-notes/architecture/layout-mapping.md`

**Produces:** 本阶段唯一的权威清单。后续每个任务执行前与它比对，差异以扫描为准。

- [ ] **Step 1: 跑 4.1 枚举全部文件**
- [ ] **Step 2: 逐文件套第 1 节判据**，填四列表格。对每个 C 类文件写出"目标有多个位置"的具体理由（例如"`tools.py` 的 read/write/edit/bash 在蓝图里各成一文件"）。
- [ ] **Step 3: 跑 4.2/4.3 扫描三类隐形引用**，写入"备注"列。任何"字符串里出现的模块路径"必须在被搬的那个任务里同步改。
- [ ] **Step 4: 与本计划 Task 3-11 的列表做差异比对。** 差异写进台账，说明是扫描更新还是本计划过时。**若发现某文件你无法归类（蓝图没给位置），停下问人**，不要自行发明位置。
- [ ] **Step 5: 交叉验证三个"待决"映射**（我上轮标注为含判断的三条）：`context_window.py` 整包进 `session/compaction/` 还是拆、`skills.py` 的包深度、`cli.py` 是否拆分。**本阶段一律按"不拆"处理**（即 `context_window.py` = A/B、`cli.py` = O），并把它们登记为第二阶段候选。
- [ ] **Step 6: Commit** `docs(layout): add authoritative module-to-target mapping for phase 1`

---

## Task 3: `themes` 提出为顶层包（消环，最先做）

**Files:**
- Move: `src/baldric_coding/tui/themes/__init__.py` → `src/baldric_coding/themes/__init__.py`
- Move: `src/baldric_coding/tui/themes/*.json`（3 个主题文件随 `__init__.py` 一起走）
- Modify: 所有 `baldric_coding.tui.themes` 引用点（至少含 `session_export.py`、`session_usage.py`、`commands.py`、`tui/` 内部引用；**以 4.2 扫描结果为准，不要只改这几处**）
- Test: 以 `tests/test_tui_themes.py` 为主，其余按扫描

**为什么它必须排第一：** `session_export.py` 与 `session_usage.py` 在模块顶层从 `tui.themes` 取主题名，而 `tui/` 又在顶层 import session —— 这是一组靠 import 顺序存活的环。把 `themes` 移出 `tui` 只需一次目录移动（它是包目录，不是单文件），零逻辑改动，却直接把这组包级环拆干净。**若先动 `session/` 再做这一步，`session/` 会拖进整个终端前端。**

**Interfaces:**
- Produces: `baldric_coding.themes`（路径变化，符号名不变：`BALDRIC_DARK_THEME`、`BALDRIC_LIGHT_THEME`、`TuiTheme`、`available_tui_theme_names` 等）

- [ ] 执行配方 M 的 Step 1-7。本簇特殊注意：
  - `themes/__init__.py` 若用 `importlib.resources` 或 `__file__` 定位同目录的 `.json`，**移动后这两类定位方式都会失效** → 属于第 2 节禁止清单之外（这是移动导致的必要改动，允许改），但改动范围只能到"路径表达式修正"为止，不得重构加载逻辑
  - 改完必须跑一次真实加载验证三个 json 都能读到，不要只靠单测通过
  - **消环验收（本任务的核心产出，必须逐条跑并记输出）：**

```powershell
# 1) session 侧不得再在顶层 import tui。预期：输出为空
Select-String -Path (Get-ChildItem src\baldric_coding -Recurse -Filter *.py).FullName `
  -Pattern '^from baldric_coding\.tui\.' |
  Where-Object { $_.Path -match '\\(session|export|usage|stats|branch_summary)' }

# 2) tui → session 这个方向仍然存在，它不是环（预期：非空，属正常）
Select-String -Path src\baldric_coding\tui\*.py -Pattern '^from baldric_coding\.(session|session_)' |
  ForEach-Object { "  $($_.Filename):$($_.LineNumber)" }
```

  第 1 条为空、第 2 条非空，就是“环已消、单向依赖保留”的正确终态。**不要把第 2 条的非空当成失败去修**（那是拆 `app.py` 的事，第二阶段）。

---

## Task 4: `auth/` 簇（7 文件，全 B 类）

**Files:**
- Move: `oauth_types.py` → `auth/types.py`
- Move: `oauth.py` → `auth/oauth.py`
- Move: `oauth_registry.py` → `auth/registry.py`
- Move: `oauth_anthropic.py` → `auth/flows/anthropic.py`
- Move: `oauth_github_copilot.py` → `auth/flows/github_copilot.py`
- Move: `oauth_device.py` → `auth/flows/device.py`
- Move: `credentials.py` → `auth/credentials.py`
- Create: `auth/__init__.py`、`auth/flows/__init__.py`（**空，只写 docstring**）
- Test: `tests/test_oauth.py`、`tests/test_oauth_providers.py`、`tests/test_oauth_tui.py`、`tests/test_credentials.py`

**备注：** `oauth.py` 与 `oauth_types.py` 是否进一步合并成 `auth/protocol.py` + `auth/types.py` 属第二阶段。本任务只做搬移改名。

---

## Task 5: 叶子簇（`config/` `update/` `observability/` `utils/`）

**Files:**
- Move: `paths.py` → `config/paths.py`；`shell_config.py` → `config/shell_config.py`
- Move: `update_check.py` → `update/check.py`；`updater.py` → `update/updater.py`；`reload.py` → `update/reload.py`
- Move: `diagnostics.py` → `observability/diagnostics.py`
- Move: `self_docs.py` → `utils/self_docs.py`
- Create: 四个包的**空** `__init__.py`
- Test: `tests/test_paths.py`、`tests/test_shell_config.py`、`tests/test_update_check.py`、`tests/test_updater.py`、`tests/test_diagnostics.py`（若存在，按扫描）

**备注：** `paths.py` 被测试深层引用最多（23 处，按 2026-11-05 扫描），M-3 的失败面会在这里最大 —— 属预期，不要为了让它变绿而改断言。`updater.py` 用 `importlib.metadata`，与包路径无关，可放心搬。

---

## Task 6: `context/` 簇

**Files:**
- Move: `context.py` → `context/project.py`
- Move: `gitignore.py` → `context/gitignore.py`
- Move: `resources.py` → `context/resources.py`
- Move: `system_prompt.py` → `context/system_prompt.py`
- Move: `thinking.py` → `context/thinking.py`
- Move: `prompt_templates.py` → `context/prompts.py`
- Move: `skills.py` → `context/skills/skills.py`（含空 `context/skills/__init__.py`）
- Create: `context/__init__.py`（空）
- Test: `tests/test_context.py`、`tests/test_gitignore.py`、`tests/test_resources.py`、`tests/test_system_prompt.py`、`tests/test_thinking.py`、`tests/test_prompt_templates.py`、`tests/test_skills.py`

**注意冲突：** 现有模块叫 `context.py`，新包叫 `context/`。**必须先完成 `context.py → context/project.py` 的移动，再建 `context/` 目录**，否则同名。Windows 上尤其注意：先 `git mv context.py context_tmp.py`，再 `mkdir context`，再 `git mv context_tmp.py context/project.py`。

**待决：** `skills.py` 的包深度（`context/skills.py` 还是 `context/skills/`）我在上轮标为判断项。**按蓝图取 `context/skills/`**；若执行时认为多余，可自行降级为单文件并在台账记录理由 —— 这是允许你自行判断的那类细节。

---

## Task 7: `providers/` 簇

**Files:**
- Move: `provider_config.py` → `providers/config.py`
- Move: `provider_catalog.py` → `providers/catalog.py`
- Move: `provider_runtime.py` → `providers/runtime.py`
- Move: `catalog_loader.py` → `providers/loader.py`
- Move: `models_dev.py` → `providers/stores/models_dev.py`
- Move: `models_dev_store.py` → `providers/stores/models_dev_store.py`
- Move: `codex_model_store.py` → `providers/stores/codex_model_store.py`
- Move: `codex_version.py` → `providers/stores/codex_version.py`
- Create: `providers/__init__.py`、`providers/stores/__init__.py`（空）
- Test: `tests/test_provider_config.py`、`test_provider_catalog.py`、`test_provider_runtime.py`、`test_catalog_loader.py`、`test_models_dev.py`、`test_models_dev_store.py`、`test_codex_model_store.py`、`test_codex_version.py`

**硬要求：** `catalog_loader.py` 与 `models_dev.py` 用 `importlib.resources.files` 读 `data/`（`catalog.toml`、`models-dev-catalog.json`）。**这一步必须现场跑一次真实读取**（不只在单测里）：

```powershell
uv run python -c "from baldric_coding.providers.loader import *; print('resources ok')"
uv run baldric --version
```

理由是 `importlib.resources` 的路径错误在打包成 wheel 后才致命，本地 import 成功不代表打包没问题。若 `tests/test_package_metadata.py` 钉住了资源路径，它会在 M-3 就失败 —— 那是正确行为。

---

## Task 8: `session/` 簇（只搬可搬的）

**Files:**
- Move: `session_manager.py` → `session/manager.py`
- Move: `session_preparation.py` → `session/prepare.py`
- Move: `session_stats.py` → `session/stats.py`
- Move: `session_usage.py` → `session/usage.py`
- Move: `branch_summary.py` → `session/branch_summary.py`
- Move: `context_window.py` → `session/compaction/context_window.py`（含空 `session/compaction/__init__.py`）
- Create: `session/__init__.py`（空）
- Move: `session.py` → `session/session.py`（**C 类停车，规则 1.1**：整文件移动+改路径，不拆）
- Move: `session_export.py` → `session/export.py`（**C 类停车**；本阶段不建 `session/export/` 目录）
- Test: `tests/test_session.py`、`test_session_manager.py`、`test_session_export.py`、`test_session_stats.py`、`test_session_usage.py`、`test_context_window.py`

**本任务的环变化（重要）：** 停车后 `session/session.py` 与 `session/manager.py` 同在一个包内，原先“模块 ↔ 包”的跳目录环降级为**包内模块间的环**——仍然存在，但不再依赖跳包初始化。搬完必须验证四种入口都能启动（见下方附加检查）。

执行要求：搬完后专门验证**四种**入口都能启动（这属于本簇的 **M-5 附加检查**，在 M-4 完成之后才有意义；M-3 阶段它们必然报 ImportError），因为环的表现依赖加载顺序 ——

```powershell
uv run python -c "import baldric_coding.session.manager"
uv run python -c "import baldric_coding.session"
uv run python -c "import baldric_coding.cli"
uv run baldric --version
```

四条必须全部成功。任何一条出 `partially initialized module` 或 `AttributeError`，说明你把新包 `__init__.py` 写成了急加载（违反规则 2.1）→ 改回空 init 再验。

---

## Task 9: `tools/` `backends/` `trust/` 簇

**Files:**
- Move: `image_processing.py` → `tools/image_processing.py`
- Move: `local_backends.py` → `backends/contracts.py`（**改名，两步 mv**）
- Move: `tui/local_backends.py` → `tui/backends.py`（**改名，两步 mv**）
- Move: `project_trust.py` → `trust/policy.py`（**改名，两步 mv**）
- Move: `tui/project_trust.py` → `tui/trust.py`（**改名，两步 mv**）
- Create: `tools/__init__.py`、`backends/__init__.py`、`trust/__init__.py`（空）
- Move: `tools.py` → `tools/registry.py`（**C 类停车，规则 1.1**：不拆成一工具一文件，那是第二阶段）
- Test: `tests/test_coding_tools.py`、`test_tool_arguments.py`、`test_tool_history.py`、`test_local_backends.py`、`test_tui_local_backends.py`、`test_project_trust.py`、`test_image_processing.py`

**本簇的完整引用面（已扫描核实，照单处理，禁止全文替换）：**

根版 `baldric_coding.local_backends` / `baldric_coding.project_trust` 共 **9 处 / 7 个文件**：
`cli.py:35`、`session.py:91`、`shell_config.py:11`、`extensions/api.py:23,25`、`extensions/runtime.py:77,79`、`__init__.py:90`、`tui/app.py:111`
tui 版（`baldric_coding.tui.local_backends` / `.project_trust`）共 **2 处**：`tui/app.py:171,178`

注意 `tui/app.py` **同时**引用两个版本（L111 根版、L171/178 tui 版）。这两个路径在本簇里目标不同（`trust/policy.py` vs `tui/trust.py`），**绝对不能对 `project_trust` 做全文替换**；另外 `extensions/api.py` 与 `extensions/runtime.py` 不在本任务的移动文件列表里，但它们是调用方，**必须同步改 import**（否则 M-4 会红）。以 4.2 的现场扫描为准。

**方向检查：** `tui/backends.py` 与 `backends/contracts.py` 是一对（契约 / Textual 宿主屏），蓝图要求依赖方向单向 `tui/ → backends/`。移动后跑一次：

```powershell
Select-String -Path (Get-ChildItem src\baldric_coding\backends -Filter *.py).FullName -Pattern 'baldric_coding\.tui'
```

必须为空 —— 若有输出，说明方向违反在移动前就存在于契约侧，**记录到台账并停下报告**，不要在阶段一里顺手修（那是逻辑改动）。

---

## Task 10: `extensions/` 与 `modes/` 簇

**Files:**
- Move: `built_in_extensions.py` → `extensions/builtin_registry.py`（**改名**；不能用蓝图写的 `extensions/builtins.py`，见下方硬冲突说明）
- Move: `extension_installer.py` → `extensions/installer.py`（**改名**）
- Move: `commands.py` → `commands/registry.py`（**C 类停车，规则 1.1**；含空 `commands/__init__.py`）
- **不动：** `rpc.py`（C 类，且本阶段不建 `modes/` 目录——没有可搬进去的东西）
- Test: `tests/test_extensions.py`、`test_extension_installer.py`、`test_example_extensions.py`、`test_commands.py`（按扫描）

**硬冲突（已核实，必须避开）：** 蓝图把 `built_in_extensions.py` 的目标写成 `extensions/builtins.py`，但 `extensions/builtins/` **已经是一个真实目录**（内含 `subagents/`、`llama_cpp/`）。同名模块与包不能共存，所以**该蓝图条目是错的** → 本计划改用 `extensions/builtin_registry.py`，并在 Task 12 按蓝图规则 4 修正文档。

**空目录不建（YAGNI）：** `modes/`、`session/export/`、`tui/app/`、`tui/widgets/` 在本阶段都没有可搬入的内容，一律**不建**。若某任务看起来要你为蓝图“补齐”一个空目录，跳过它并记台账——这是我明确授权的不执行项。

---

## Task 11: 门面与剩余 O 类复核

**Files:**
- Modify: `src/baldric_coding/__init__.py`（**只改路径，不改导出集**）
- Verify: `rendering/` 5 个文件、`tui/` 未列改动的 8 个文件、`extensions/` 原有 5 个文件 —— 应为 O 类，不搬

- [ ] **Step 1:** 重跑 4.4 的 `__all__` 快照，与 Phase-1 起点的 `facade_before.txt` 比对（`Compare-Object`）。**必须为空 diff**；若非空，说明某次移动改动了导出集，回退那次提交的导出行修正。
- [ ] **Step 2:** `uv run python -c "import baldric_coding as m; print(len(m.__all__))"` 与起点一致。**不要拿 `len(dir(m))` 对比**——它必然因新建子包而变大。
- [ ] **Step 3:** 若 `dev-notes/architecture/target-project-layout.md` 的编码树与本阶段实际结果出现新的偏差（比如你按扫描把某文件判成了不同类别），**按蓝图规则 4 改文档，不改代码**。

---

## Task 12: 收尾与第二阶段入口判定

**Files:**
- Modify: `dev-notes/architecture/layout-migration-log.md`（补每簇终态）
- Modify: `dev-notes/architecture/target-project-layout.md`（把已完成部分标注为现状，仍属蓝图的部分保留；两处文档失真收口）
- Modify: `website/content/**`（9 处硬编码模块路径）
- Modify: `dev-notes/**`（24 处硬编码模块路径，只改指向本次移动的那 24 处；历史阶段记录属**当时的事实**，不要追溯改写）
- Test: `tests/test_package_metadata.py`

- [ ] **Step 1: 打包验证，不能只跑单测**

```powershell
uv build --wheel
uv run python -c "import baldric_coding, baldric_coding.themes, baldric_coding.providers.loader as l; print('ok')"
```

理由：资源文件（3 个主题 `.json`、`data/catalog.toml`、`data/models-dev-catalog.json`）在 sdist/wheel 里的包含规则与本地目录不同，`hatch` 的 `packages` 配置只列了三个顶层包，新增子目录必须验证被打进产物。

- [ ] **Step 2: 根目录文件数复核。** 不要拿固定数字当验收标准（它会和 Task 2 的扫描权威性互相矛盾）。做法：从 `layout-mapping.md` 导出“目标仍在 `baldric_coding/` 根”的文件集合，与 `Get-ChildItem src\baldric_coding -Filter *.py` 的实际结果对差。**两边必须相等。** 若有出入，逐个写清原因（某簇被跳过 / 它被重判为 C 且无同名冲突 / 映射表本身需要修正），**不要现场改方案，也不要为了让两边对上而挪文件**。
- [ ] **Step 3: 写第二阶段入口条件。** 在台账末尾列出：7 个 C 类文件各自的拆分依据、以及 `context_window.py` / `cli.py` 两个"本阶段按不拆处理"的候选。**不要在本计划里给它们的拆分方案。**

- [ ] **Step 4: Commit**

```powershell
git add dev-notes website/content
git commit -m "docs(layout): record phase 1 move results and phase 2 entry conditions"
```

---

## 附：与蓝图文档的对应关系

本计划实现的是蓝图「全局目标结构」一节里的 A/B/O 部分，以及「两条承重的规则」的第 1 条（包根保持接近空）。蓝图「蓝图尚未成为现实的阻碍」表中的 4 项，本阶段的处置是：

| 阻碍 | 本阶段 |
|---|---|
| `session ↔ tui` 环 | **Task 3 消除**（themes 是纯移动） |
| `commands ↔ tui` 环 | 已有人工延迟 import，本阶段不动 |
| `rendering → tui.state` 方向违反 | **推迟**（提取 221 行属拆分，第二阶段） |
| 两个大文件多职责 | **推迟**（第二阶段主体） |

## 附二：本阶段必须反向修正蓝图的四处

按蓝图自己的规则 4（“更好的实现高于本文件”），Task 12 须修正 `dev-notes/architecture/target-project-layout.md`：

1. `extensions/builtins.py` → 改为 `extensions/builtin_registry.py`（与已存在的 `builtins/` 目录硬冲突）
2. `cli.py` 在根门面清单与阻碍表自相矛盾（阻碍表说它承担两件事，树却不动它）→ 阻碍表标注“本阶段按不动处理，拆分归第二阶段”
3. `modes/` 子树 → 标注为预期新增（本阶段不建空目录）
4. `session/export/`、`tui/app/`、`tui/widgets/` → 同上

这四处不是实施偏差，是蓝图的错。**修正文档，不修正代码。**
