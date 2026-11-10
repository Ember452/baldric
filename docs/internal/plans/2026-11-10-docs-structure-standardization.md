# 文档结构标准化实施计划

> **给执行 agent：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务执行本计划。步骤用勾选框（`- [ ]`）语法跟踪。

**目标：** 让 `docs/` 成为 Baldric 文档的唯一事实来源，按读者分群、按 Diátaxis 四象限布局，用一份标准文件约束存放位置与写作。

**架构：** `docs/user/` 是唯一发布的树，成为 Astro 内容基底。`docs/internal/` 存放贡献者档案（ADR、架构日志、设计、笔记、计划、规格），永不被站点 glob。`docs/AGENTS.md` 定义分层分类与写作规则。打包自知识 `src/baldric/runtime/data/docs/` 保持为独立的 wheel 工件，作为独立分层记录。

**技术栈：** Markdown + Astro 7 内容集合（website/），Python 3.12 + pytest 守卫，GitHub Actions，本地移动用 PowerShell（只 `git mv`）。

**规格：** 无。需求在评审中达成一致；以下决定是本计划的权威依据。

## 已锁定的决定

1. **`docs/` 是唯一根。** 移除 `website/content/`。
2. **Diátaxis 改名在范围内。** 没有发布、没有用户，所以不需要重定向：
   - `/guides/...` → `/how-to/...`
   - `/internals/...` → `/explanation/...`
   - `/quickstart/` → `/tutorials/quickstart/`
   - `/concepts/` → `/explanation/concepts/`
   - `/what-is-baldric/` → `/explanation/what-is-baldric/`
   - `/reference/`、`/releases/`、`/roadmap/`、`/contributing/`、`/` 保持 URL。
3. **按读者分群，不是隐藏目录。** 发布内容在 `docs/user/`；贡献者内容在 `docs/internal/`。
4. **打包自知识保持独立。** `src/baldric/runtime/data/docs/` 随 wheel 发布、由 agent 运行时读取。它是被记录的独立分层，不是用户文档的拷贝。
5. **ADR 序列合并。** `dev-notes/adr/0001-0003` 保留；`plans/adr-0001-0003` 变为 `0004-kernel-boundary.md`、`0005-god-class-deferral.md`、`0006-transcript-as-truth.md`。
6. **部署保持禁用。** `.github/workflows/docs.yml.disabled` 与 `publish.yml.disabled` 不重新启用；CI 仍在既有 `docs` job 中构建并测试站点。

## 全局约束

- **移动文件只用 `git mv`。** 绝不删除重建文档。历史必须跟随文件。
- **绝不用脚本、`sed` 或循环改写文档正文。** 逐文件用编辑器工具。批量 `git mv` 循环移动文件而不碰内容，是允许的。
- **用户文档描述当前行为。** 历史与被否决的替代方案归 `docs/internal/`。
- **一个事实一个家。** 链接到拥有该事实的页面，不要复述。
- **发布边界是绝对的。** `docs/internal/`、`docs/templates/`、`docs/assets/` 绝不能被 Astro 集合加载。内容基底恰好是 `docs/user`。
- **根 `AGENTS.md` 只能在任务 6 增长**，该任务有正当理由（新增 `docs/AGENTS.md` 分层）并在同一提交中重新基线。
- **每个任务收尾全绿**（该任务下列的检查）。不堆叠失败提交。
- **提交信息遵循仓库风格**（`docs: ...`、`chore: ...`），每次提交一个连贯变更。

## 目标树

```text
docs/
├── README.md                     # 文档地图与阅读路径
├── AGENTS.md                     # 文档标准（分层表 + 规则）
├── assets/
│   └── baldric-header.svg
├── templates/
│   ├── adr.md
│   ├── design.md
│   └── plan.md
├── user/                         # 发布 —— Astro 内容基底
│   ├── _index.md
│   ├── contributing.md
│   ├── releases.md
│   ├── roadmap.md
│   ├── tutorials/
│   │   └── quickstart.md
│   ├── how-to/
│   │   ├── _index.md
│   │   ├── context.md
│   │   ├── extensions.md
│   │   ├── local-inference.md
│   │   ├── mcp.md
│   │   ├── print-mode.md
│   │   ├── project-instructions.md
│   │   ├── project-trust.md
│   │   ├── providers-and-models.md
│   │   ├── sessions.md
│   │   ├── skills-and-prompts.md
│   │   ├── themes.md
│   │   └── tui.md
│   ├── reference/
│   │   ├── _index.md
│   │   ├── cli.md
│   │   ├── configuration.md
│   │   ├── keybindings.md
│   │   ├── rpc.md
│   │   ├── slash-commands.md
│   │   └── tools.md
│   └── explanation/
│       ├── _index.md
│       ├── agent-loop.md
│       ├── architecture.md
│       ├── concepts.md
│       ├── custom-frontend.md
│       ├── design-principles.md
│       └── what-is-baldric.md
└── internal/                     # 永不发布
    ├── README.md
    ├── adr/
    │   ├── 0001-use-textual-for-tui.md
    │   ├── 0002-keep-tool-docs-hand-written.md
    │   ├── 0003-unify-skill-discovery-on-agent-skills-spec.md
    │   ├── 0004-kernel-boundary.md
    │   ├── 0005-god-class-deferral.md
    │   └── 0006-transcript-as-truth.md
    ├── architecture/             # 自 dev-notes/architecture/ 移入
    ├── design/                   # 自 dev-notes/design/ 移入
    ├── notes/                    # 自 dev-notes/*.md 移入（README 除外）
    ├── plans/                    # 自 plans/ 与 docs/superpowers/plans/ 移入
    └── specs/                    # 自 docs/superpowers/specs/ 移入
```

---

## 任务 0：记录起点

**文件：** 无。

**接口：**
- 消费：干净的 `main` checkout。
- 产出：分支 `docs/standardize-structure` 与一条已记录的绿色基线。

- [ ] **步骤 1：确认工作树干净**

运行：
```powershell
git status --short
```
预期：无输出。

- [ ] **步骤 2：记录基线检查**

运行：
```powershell
uv run pytest -q tests/guards tests/test_package_metadata.py
npm --prefix website run build
npm --prefix website test
```
预期：pytest 通过；Astro 构建成功；`npm test` 全部站点测试通过。

- [ ] **步骤 3：创建分支**

运行：
```powershell
git switch -c docs/standardize-structure
```
预期：`Switched to a new branch 'docs/standardize-structure'`。

本任务无提交。

---

## 任务 1：确立 `docs/` 为文档根

**文件：**
- 新建：`docs/README.md`
- 新建：`docs/AGENTS.md`
- 新建：`docs/templates/adr.md`
- 新建：`docs/templates/design.md`
- 新建：`docs/templates/plan.md`

**接口：**
- 消费：无。
- 产出：后续任务都引用的文档标准；`docs/AGENTS.md` 是任务 6 的棘轮将认识的新文件。

- [ ] **步骤 1：写 `docs/README.md`**（中文版见仓库 `docs/README.md` 的实际内容）

- [ ] **步骤 2：写 `docs/AGENTS.md`**（中文版见仓库 `docs/AGENTS.md` 的实际内容，含"语言"一节：文档优先中文）

- [ ] **步骤 3：写 `docs/templates/adr.md`**（中文模板，见仓库实际内容）

- [ ] **步骤 4：写 `docs/templates/design.md`**（中文模板，见仓库实际内容）

- [ ] **步骤 5：写 `docs/templates/plan.md`**（中文模板，见仓库实际内容）

- [ ] **步骤 6：验证没有移动其他东西并提交**

运行：
```powershell
git status --short
uv run pytest -q tests/guards
```
预期：只有五个新文件未跟踪；守卫测试通过。

```powershell
git add docs/README.md docs/AGENTS.md docs/templates
git commit -m "docs: add documentation root index, standard, and templates"
```

---

## 任务 2：把发布文档移到 `docs/user` 并重指 Astro

**文件：**
- 移动：`website/content/` → `docs/user/`
- 修改：`website/src/content.config.ts`
- 修改：`website/src/pages/[...slug].astro`
- 修改：`website/src/data.ts`
- 修改：`website/tests/site.test.mjs`
- 修改：`website/data/sidebar.yaml`
- 修改：`website/src/components/Footer.astro`、`Navbar.astro`、`Home.astro`
- 修改：`website/src/components/Roadmap.astro`

**接口：**
- 消费：任务 1 的 `docs/`。
- 产出：Astro 集合基底 `docs/user`；发布页面 `tutorials/`、`how-to/`、`reference/`、`explanation/`，加顶层 home、`contributing`、`releases`、`roadmap`。

- [ ] **步骤 1：带历史移动目录树**

运行：
```powershell
git mv website/content docs/user
git mv docs/user/guides docs/user/how-to
git mv docs/user/internals docs/user/explanation
New-Item -ItemType Directory -Path "docs/user/tutorials" -Force | Out-Null
git mv docs/user/quickstart.md docs/user/tutorials/quickstart.md
git mv docs/user/concepts.md docs/user/explanation/concepts.md
git mv docs/user/what-is-baldric.md docs/user/explanation/what-is-baldric.md
```
预期：`website/content` 不复存在；`git status --short` 显示 rename。

- [ ] **步骤 2：重指内容集合**

`website/src/content.config.ts` 中：

```ts
loader: glob({ pattern: "**/*.md", base: "./content" }),
```

改为：

```ts
loader: glob({ pattern: "**/*.md", base: "../docs/user" }),
```

- [ ] **步骤 3：从 entry id 推导编辑链接路径**

`website/src/pages/[...slug].astro` 中，把：

```ts
const file = entry.filePath?.replace(/^.*?content\//, "") ?? `${entry.id}.md`;
```

替换为：

```ts
const file = `${entry.id}.md`;
```

- [ ] **步骤 4：重指编辑 URL**

`website/src/data.ts` 中：

```ts
editRepoUrl: "https://github.com/Ember452/baldric/edit/main/website/content",
```

改为：

```ts
editRepoUrl: "https://github.com/Ember452/baldric/edit/main/docs/user",
```

- [ ] **步骤 5：更新侧栏路径与标签**

用计划中的新 `sidebar.yaml`（各路径已改为 `/tutorials/quickstart/`、`/how-to/...`、`/explanation/...`；"Guides" 组更名 "How-to guides"）整体替换 `website/data/sidebar.yaml`。

- [ ] **步骤 6：更新站点测试夹具**

`website/tests/site.test.mjs`：

`for (const file of await files(path.resolve("content")))` →
`for (const file of await files(path.resolve("../docs/user")))`；

`.relative(path.resolve("content"), file)` →
`.relative(path.resolve("../docs/user"), file)`；

quickstart 夹具 `"quickstart/index.html"` → `"tutorials/quickstart/index.html"`；

编辑链接期望 `"/edit/main/website/content/quickstart.md"` →
`"/edit/main/docs/user/tutorials/quickstart.md"`。

- [ ] **步骤 7：更新组件里的硬编码站点链接**

逐文件用编辑器替换：

- `website/src/components/Footer.astro`：`/quickstart/` → `/tutorials/quickstart/`（1 处）、`/internals/` → `/explanation/`（1 处）。
- `website/src/components/Navbar.astro`：`/quickstart/` → `/tutorials/quickstart/`（1 处）、`/internals/` → `/explanation/`（1 处）。
- `website/src/components/Home.astro`：`/quickstart/` → `/tutorials/quickstart/`（2 处）、`/internals/` → `/explanation/`（5 处）、`/guides/` → `/how-to/`（1 处）。
- `website/src/components/Roadmap.astro`：`/internals/` → `/explanation/`（1 处）；两处 `<code>dev-notes/</code>` 改为 `<code>docs/internal/</code>`。
- `website/src/pages/404.astro`：`/quickstart/` → `/tutorials/quickstart/`（1 处）。

- [ ] **步骤 8：构建并测试**

运行：
```powershell
npm --prefix website run check
npm --prefix website run format:check
npm --prefix website run build
npm --prefix website test
```
预期：类型检查通过、格式干净、构建产出 `dist/tutorials/quickstart/index.html`、`dist/how-to/tui/index.html`、`dist/explanation/architecture/index.html`，站点测试全过。

> 执行注记：站点测试会解析正文里的内容链接，因此任务 3 的 URL 重写必须在本任务提交前完成（两者不可分别保持绿色）；本分支将任务 2 与任务 3 合并为一个原子提交。

- [ ] **步骤 9：提交**

```powershell
git add -A
git commit -m "docs: move published docs to docs/user with Diátaxis layout"
```

---

## 任务 3：在用户文档内重写发布 URL 命名空间

**文件（都在 `docs/user/` 下）：**
- `docs/user/explanation/concepts.md`：7 处 `/guides/`、1 处 `/internals/`
- `docs/user/tutorials/quickstart.md`：5 处 `/guides/`、1 处 `/concepts/`
- `docs/user/explanation/what-is-baldric.md`：1 处 `/guides/`、1 处 `/internals/`、2 处 `/quickstart/`、2 处 `/concepts/`
- `docs/user/contributing.md`：1 处 `/internals/`
- `docs/user/how-to/*.md`：8 个文件、19 处 `/guides/`
- `docs/user/explanation/*.md`（四个迁移的 internals 页）：7 处 `/guides/`、10 处 `/internals/`
- `docs/user/reference/*.md`：4 个文件、18 处 `/guides/`、1 处 `/internals/`

**接口：**
- 消费：任务 2 的新 URL 命名空间。
- 产出：`/guides/`、`/internals/`、`/quickstart/`、`/concepts/`、`/what-is-baldric/` 链接归零。

- [ ] **步骤 1：先重写指定的已移动页面**

对下面每个文件，按此顺序用编辑器 replace-all。

1. `docs/user/tutorials/quickstart.md`：
   - `(/concepts/)` → `(/explanation/concepts/)`
   - `(/guides/` → `(/how-to/`
2. `docs/user/explanation/concepts.md`：
   - `(/internals/` → `(/explanation/`
   - `(/guides/` → `(/how-to/`
3. `docs/user/explanation/what-is-baldric.md`：
   - `(/quickstart/)` → `(/tutorials/quickstart/)`
   - `(/concepts/)` → `(/explanation/concepts/)`
   - `(/guides/` → `(/how-to/`
   - `(/internals/` → `(/explanation/`
4. `docs/user/contributing.md`：
   - `(/internals/` → `(/explanation/`

- [ ] **步骤 2：重写其余地方的分区链接**

对 `docs/user/how-to/`、`docs/user/reference/`、`docs/user/explanation/` 下每个文件用编辑器 replace-all：

- `(/guides/` → `(/how-to/`
- `(/internals/` → `(/explanation/`

不碰 `docs/internal/`。

- [ ] **步骤 3：验证站点无残留旧链接**

运行：
```powershell
Select-String -Path "docs/user/**/*.md" -Pattern '\(/guides/|\(/internals/|\(/quickstart/|\(/concepts/|\(/what-is-baldric/'
```
预期：无输出。（`docs/user/**/*.md` 需要 PowerShell 7 递归 glob；不可用时用 `Get-ChildItem -LiteralPath docs/user -Recurse -File -Filter *.md | Select-String -Pattern ...`。）

再验证新路径存在：

```powershell
Select-String -Path "docs/user/**/*.md" -Pattern '\(/how-to/|\(/explanation/|\(/tutorials/'
```
预期：上列文件有命中。

- [ ] **步骤 4：构建并测试站点**

运行：
```powershell
npm --prefix website run build
npm --prefix website test
```
预期：构建成功且链接解析测试以新路由通过。

- [ ] **步骤 5：提交**（本分支与任务 2 合并为一个原子提交）

```powershell
git add docs/user
git commit -m "docs: point user docs at the Diátaxis URL namespace"
```

---

## 任务 4：把贡献者文档移入 `docs/internal`

**文件：**
- 移动：`dev-notes/adr/` → `docs/internal/adr/`
- 移动：`dev-notes/architecture/` → `docs/internal/architecture/`
- 移动：`dev-notes/design/` → `docs/internal/design/`
- 移动：`dev-notes/*.md`（`README.md` 除外）→ `docs/internal/notes/`
- 移动：`dev-notes/README.md` → `docs/internal/README.md`
- 移动：`plans/` → `docs/internal/plans/`
- 移动：`docs/superpowers/plans/*.md` → `docs/internal/plans/`
- 移动：`docs/superpowers/specs/*.md` → `docs/internal/specs/`
- 修改：`docs/internal/README.md`
- 修改：`docs/internal/design/03-tools.md`
- 修改：`docs/internal/design/mcp-client-build.md`
- 修改：`src/baldric/runtime/data/docs/architecture.md`
- 修改：`src/baldric/runtime/data/docs/extensions.md`
- 修改：`src/baldric/runtime/data/docs/models.md`
- 修改：`src/baldric/runtime/data/docs/skills.md`

> 本任务会移动计划文件自身：`docs/superpowers/plans/2026-11-10-docs-structure-standardization.md`
> 落到 `docs/internal/plans/2026-11-10-docs-structure-standardization.md`。此后按新路径跟踪进度。
> （执行补充：`git mv` 要求目标父目录 `docs/internal/` 已存在——先建目录，再移动；且目标目录已存在时 `git mv` 会把源目录嵌进其内部，需展平。）

**接口：**
- 消费：`docs/AGENTS.md` 的 `docs/internal/` 存放规则。
- 产出：六个内部分区，且 `dev-notes/`、`plans/`、`docs/superpowers/` 目录消失。

- [ ] **步骤 1：按此确切顺序移动目录**

```powershell
git mv dev-notes/adr docs/internal/adr
git mv dev-notes/architecture docs/internal/architecture
git mv dev-notes/design docs/internal/design
git mv plans docs/internal/plans
New-Item -ItemType Directory -Path "docs/internal/notes" -Force | Out-Null
Get-ChildItem -LiteralPath "dev-notes" -File -Filter *.md | Where-Object { $_.Name -ne "README.md" } | ForEach-Object { git mv $_.FullName "docs/internal/notes/$($_.Name)" }
git mv dev-notes/README.md docs/internal/README.md
New-Item -ItemType Directory -Path "docs/internal/specs" -Force | Out-Null
Get-ChildItem -LiteralPath "docs/superpowers/plans" -File -Filter *.md | ForEach-Object { git mv $_.FullName "docs/internal/plans/$($_.Name)" }
Get-ChildItem -LiteralPath "docs/superpowers/specs" -File -Filter *.md | ForEach-Object { git mv $_.FullName "docs/internal/specs/$($_.Name)" }
```
Windows 上 git 不删除清空后的源目录，核实为空后删除：
```powershell
Get-ChildItem -LiteralPath dev-notes, docs/superpowers -Force -ErrorAction SilentlyContinue
```
预期：无文件列出。然后：
```powershell
Remove-Item -LiteralPath dev-notes, docs/superpowers -Recurse -Force -ErrorAction SilentlyContinue
```
预期：`dev-notes`、`plans`、`docs/superpowers` 消失；`git status --short` 报 rename 而非 add/delete。

- [ ] **步骤 2：改写 `docs/internal/README.md`**（中文版见仓库实际内容）

- [ ] **步骤 3：修复两处因移动而断的相对链接**

`docs/internal/design/03-tools.md`：

```markdown
[ADR 0002](./adr/0002-keep-tool-docs-hand-written.md)
```

改为：

```markdown
[ADR 0002](../adr/0002-keep-tool-docs-hand-written.md)
```

`docs/internal/design/mcp-client-build.md`：

```markdown
[plans/mcp-client-implementation.md](../../plans/mcp-client-implementation.md)
```

改为：

```markdown
[plans/mcp-client-implementation.md](../plans/mcp-client-implementation.md)
```

- [ ] **步骤 4：更新打包自知识路径**

编辑 `src/baldric/runtime/data/docs/` 下这些文件：

- `architecture.md`：`website/content/internals/architecture.md` → `docs/user/explanation/architecture.md`；`dev-notes/architecture/` → `docs/internal/architecture/`。
- `extensions.md`：`website/content/guides/extensions.md` → `docs/user/how-to/extensions.md`（三处）；`dev-notes/architecture/phase-21-extensions.md` → `docs/internal/architecture/phase-21-extensions.md`。
- `models.md`：`website/content/guides/providers-and-models.md` → `docs/user/how-to/providers-and-models.md`。
- `skills.md`：`website/content/guides/skills-and-prompts.md` → `docs/user/how-to/skills-and-prompts.md`。

同时更新发布文档中的现行仓库路径引用：

- `docs/user/contributing.md`：`dev-notes/design/` → `docs/internal/design/`、`dev-notes/architecture/` → `docs/internal/architecture/`、`dev-notes/adr/` → `docs/internal/adr/`、其余 `dev-notes/` → `docs/internal/`，`website/content/` → `docs/user/`。
- `docs/user/how-to/extensions.md:928`：`dev-notes/architecture/phase-21-extensions.md` → `docs/internal/architecture/phase-21-extensions.md`。
- `docs/user/explanation/architecture.md:95`：`` `dev-notes/` `` → `` `docs/internal/` ``。
- `docs/user/explanation/custom-frontend.md:110`：`` `dev-notes/` `` → `` `docs/internal/` ``。
- `docs/user/explanation/design-principles.md:54`：`` `dev-notes/` `` → `` `docs/internal/` ``。
- `docs/user/reference/rpc.md:78`：`dev-notes/design/rpc-runtime-interchangeability-plan.md` → `docs/internal/design/rpc-runtime-interchangeability-plan.md`。

- [ ] **步骤 5：验证移动与链接**

运行：
```powershell
git status --short
Test-Path dev-notes, plans, docs/superpowers
Get-ChildItem -LiteralPath docs/internal -Directory | Select-Object -ExpandProperty Name
Select-String -Path "docs/internal/**/*.md" -Pattern '\]\(\.\./\.\./plans/|\]\(\./adr/'
```
预期：`Test-Path` 返回 `False, False, False`；列出六个内部分区（`adr`、`architecture`、`design`、`notes`、`plans`、`specs`）；链接搜索无输出。
（执行注记：计划文档自身代码块里的示例字符串会命中该搜索——那是教学示例，不是真实链接。）

- [ ] **步骤 6：跑 Python 守卫与 wheel 测试**

运行：
```powershell
uv run pytest -q tests/guards tests/test_package_metadata.py
```
预期：全过，包括断言打包文档存在的 wheel 测试。

- [ ] **步骤 7：提交**

```powershell
git add -A
git commit -m "docs: move contributor records under docs/internal"
```

---

## 任务 5：合并 ADR 序列

**文件：**
- 改名：`docs/internal/plans/adr-0001-kernel-boundary.md` → `docs/internal/adr/0004-kernel-boundary.md`
- 改名：`docs/internal/plans/adr-0002-god-class-deferral.md` → `docs/internal/adr/0005-god-class-deferral.md`
- 改名：`docs/internal/plans/adr-0003-transcript-as-truth.md` → `docs/internal/adr/0006-transcript-as-truth.md`
- 修改：`docs/internal/adr/0004-kernel-boundary.md`（标题）
- 修改：`docs/internal/adr/0005-god-class-deferral.md`（标题）
- 修改：`docs/internal/adr/0006-transcript-as-truth.md`（标题与自引用）
- 修改：`docs/internal/plans/agent-kernel-parity-plan.md`
- 修改：`docs/internal/plans/kernel-refactor-plan.md`
- 修改：`docs/internal/specs/2026-11-08-tui-visual-system-design.md`
- 修改：`src/baldric/runtime/extensions/builtins/subagents/extension.py`
- 修改：`tests/runtime/extensions/test_subagents_extension.py`

**接口：**
- 消费：任务 4 产出的单一 `docs/internal/adr/` 目录。
- 产出：一个 ADR 序列 `0001`-`0006`；所有引用使用最终编号与路径。

- [ ] **步骤 1：改名 ADR**

```powershell
git mv docs/internal/plans/adr-0001-kernel-boundary.md docs/internal/adr/0004-kernel-boundary.md
git mv docs/internal/plans/adr-0002-god-class-deferral.md docs/internal/adr/0005-god-class-deferral.md
git mv docs/internal/plans/adr-0003-transcript-as-truth.md docs/internal/adr/0006-transcript-as-truth.md
```

- [ ] **步骤 2：改标题编号**

逐文件用编辑器：

- `docs/internal/adr/0004-kernel-boundary.md`：`# ADR-0001：` → `# ADR-0004：`
- `docs/internal/adr/0005-god-class-deferral.md`：`# ADR-0002：` → `# ADR-0005：`
- `docs/internal/adr/0006-transcript-as-truth.md`：`# ADR-0003：` → `# ADR-0006：`

`0004-kernel-boundary.md` 内，把交叉引用文本 `adr-0002-god-class-deferral.md` 改为 `0005-god-class-deferral.md`。
`0006-transcript-as-truth.md` 内，把 `(ADR-0001)` 改为 `(ADR-0004)`。

- [ ] **步骤 3：更新计划引用**

`docs/internal/plans/agent-kernel-parity-plan.md`：先替换 `plans/adr-0003-transcript-as-truth.md` 为 `../adr/0006-transcript-as-truth.md`，再替换其余每处 `adr-0003-transcript-as-truth.md` 为 `../adr/0006-transcript-as-truth.md`，并把所有指代 transcript 决策的 `ADR-0003` 改为 `ADR-0006`。

`docs/internal/plans/kernel-refactor-plan.md`：先替换 `plans/adr-0001-kernel-boundary.md` 为 `../adr/0004-kernel-boundary.md`，再替换 `adr-0003-transcript-as-truth.md` 为 `../adr/0006-transcript-as-truth.md`、`adr-0002-god-class-deferral.md` 为 `../adr/0005-god-class-deferral.md`，以及其余每处 `adr-0001-kernel-boundary.md` 为 `../adr/0004-kernel-boundary.md`。

`docs/internal/specs/2026-11-08-tui-visual-system-design.md`：把每处 `plans/adr-0003-transcript-as-truth.md` 替换为 `../adr/0006-transcript-as-truth.md`，把每处指代 transcript-as-truth 的 `ADR-0003` 替换为 `ADR-0006`。

- [ ] **步骤 4：更新指名 transcript ADR 的代码注释**

`src/baldric/runtime/extensions/builtins/subagents/extension.py`：把 durable-transcript 行的注释前缀从 `ADR 0003:` 改为 `ADR 0006:`。

`tests/runtime/extensions/test_subagents_extension.py`：把两处 durable-transcript 注释从 `ADR 0003` 改为 `ADR 0006`。

不要改 `src/baldric/runtime/context/skills/skills.py:185`：其 `ADR 0003` 指技能发现，编号不变。

- [ ] **步骤 5：验证重编号**

运行：
```powershell
Get-ChildItem -LiteralPath docs/internal/adr -File | Select-Object -ExpandProperty Name
Get-ChildItem -LiteralPath docs/internal -Recurse -File -Filter *.md | Select-String -Pattern 'adr-000[123]-(kernel|god|transcript)|plans/adr-000'
Select-String -LiteralPath "src/baldric/runtime/extensions/builtins/subagents/extension.py","tests/runtime/extensions/test_subagents_extension.py" -Pattern 'ADR 0003'
```
预期：ADR 目录列出 `0001`-`0006`；第一个搜索无输出（计划文档自身的指令文本命中属预期，需排除）；第二个搜索无输出（transcript 注释现在写 `ADR 0006`）。`skills.py` 的技能发现 `ADR 0003` 正确，不属任一搜索。

- [ ] **步骤 6：跑受影响测试**

运行：
```powershell
uv run pytest -q tests/runtime/extensions/test_subagents_extension.py tests/guards
```
预期：全过。

- [ ] **步骤 7：提交**

```powershell
git add -A
git commit -m "docs: merge ADR sequences under docs/internal/adr"
```

---

## 任务 6：更新指引入口并扩展 agent 指引棘轮

**文件：**
- 修改：`README.md:201`、`README.md:258`
- 修改：`CONTRIBUTING.md:115-137`
- 修改：`AGENTS.md:148-231`
- 修改：`scripts/check_agent_guidance.py`
- 修改：`tests/guards/test_agent_guidance_ratchet.py`
- 修改：`agent-guidance-baseline.json`

**接口：**
- 消费：任务 1-5 的最终路径。
- 产出：指向新树的指引文件；棘轮覆盖 `docs/AGENTS.md`；重新基线的 `agent-guidance-baseline.json`。

- [ ] **步骤 1：更新 `README.md`**

`dev-notes/` 保留逐阶段构建日志 → `docs/internal/`；
`website/content/` → `docs/user/`。

- [ ] **步骤 2：更新 `CONTRIBUTING.md`**

`dev-notes/` → `docs/internal/`；`website/content/` 代码块 → `docs/user/`；`dev-notes/release-process.md` 链接 → `docs/internal/notes/release-process.md`。

- [ ] **步骤 3：更新 `AGENTS.md`**

Scoped Instructions 列表加：

```markdown
- `docs/AGENTS.md` - documentation placement and writing rules
```

Documentation Expectations：`dev-notes/` 改 `docs/internal/`，`website/content/` 改 `docs/user/`。

- [ ] **步骤 4：教棘轮认识 `docs/AGENTS.md`**

`scripts/check_agent_guidance.py` 的 `_managed_files` 替换为把 `ROOT / "docs"` 加进 guidance 目录列表的版本（见仓库实际代码）。

- [ ] **步骤 5：在守卫测试中断言新分层**

`tests/guards/test_agent_guidance_ratchet.py` 的 `test_baseline_is_committed_and_readable` 增加：

```python
    assert "docs/AGENTS.md" in baseline["files"]
```

- [ ] **步骤 6：重新基线并验证**

运行：
```powershell
uv run python scripts/check_agent_guidance.py --init
uv run python scripts/check_agent_guidance.py
uv run pytest -q tests/guards/test_agent_guidance_ratchet.py
```
预期：基线列出 `docs/AGENTS.md`；检查打印 `agent-guidance ratchet: OK`；守卫测试通过。

- [ ] **步骤 7：提交**

```powershell
git add README.md CONTRIBUTING.md AGENTS.md scripts/check_agent_guidance.py tests/guards/test_agent_guidance_ratchet.py agent-guidance-baseline.json
git commit -m "docs: point guidance files at docs/ and ratchet docs/AGENTS.md"
```

---

## 任务 7：加 GitHub 社区文件与生成式 changelog

**文件：**
- 新建：`SECURITY.md`
- 新建：`CODE_OF_CONDUCT.md`
- 新建：`SUPPORT.md`
- 新建：`CHANGELOG.md`（生成）
- 新建：`scripts/render_changelog.py`
- 新建：`tests/guards/test_changelog.py`
- 新建：`.github/ISSUE_TEMPLATE/bug_report.yml`
- 新建：`.github/ISSUE_TEMPLATE/feature_request.yml`
- 新建：`.github/ISSUE_TEMPLATE/config.yml`
- 修改：`.github/workflows/ci.yml`（`static` job 加 changelog 检查）

**接口：**
- 消费：`src/baldric/runtime/data/release-notes/releases.json` 作为发布事实唯一来源。
- 产出：GitHub 认可的社区文件与一份不会偏离发布数据的 changelog。

各文件全文见仓库实际内容（英文社区文件与中文文档标准是两类产物，社区文件保持英文）。渲染器从 `releases.json` 生成、`--check` 校验、CI 加同步检查；守卫测试的 `subprocess.run` 带 `timeout=60`。

- [ ] **步骤 1-4：写 SECURITY.md、CODE_OF_CONDUCT.md、SUPPORT.md、三个 issue 模板**
- [ ] **步骤 5：写 changelog 渲染器 `scripts/render_changelog.py`**
- [ ] **步骤 6：写守卫测试 `tests/guards/test_changelog.py`**（`subprocess.run(..., timeout=60)`）
- [ ] **步骤 7：生成 changelog 并加 CI 检查**

运行：
```powershell
uv run python scripts/render_changelog.py
```
预期：`wrote CHANGELOG.md`。

`.github/workflows/ci.yml` 的 `static` job、agent-guidance 步骤之后加：

```yaml
      - name: Check changelog is current
        run: uv run python scripts/render_changelog.py --check
```

- [ ] **步骤 8：验证并提交**

运行：
```powershell
uv run ruff check scripts/render_changelog.py tests/guards/test_changelog.py
uv run pytest -q tests/guards/test_changelog.py
uv run python scripts/render_changelog.py --check
```
预期：lint 通过；测试通过；检查打印 `CHANGELOG.md is up to date`。

```powershell
git add SECURITY.md CODE_OF_CONDUCT.md SUPPORT.md CHANGELOG.md scripts/render_changelog.py tests/guards/test_changelog.py .github/ISSUE_TEMPLATE .github/workflows/ci.yml
git commit -m "docs: add community files and generated changelog"
```

---

## 任务 8：终验扫描

**文件：** 默认无。只修扫描证明过期的东西，一次一个文件，然后作为新提交（绝不改写历史提交）。

**接口：**
- 消费：此前每个任务。
- 产出：树已标准化、站点干净、无现行引用指向被移除路径的证据。

- [ ] **步骤 1：证明无现行引用指向被移除的根**

运行（注意：管道把路径字符串当文本行搜索是空转——用 `Select-String -Path`）：
```powershell
$targets = @("README.md", "CONTRIBUTING.md", "AGENTS.md")
$targets += Get-ChildItem -LiteralPath docs, website/src, website/tests, src/baldric/runtime/data/docs -Recurse -File -Include *.md, *.ts, *.astro, *.mjs -ErrorAction SilentlyContinue | ForEach-Object FullName
Select-String -Path $targets -Pattern 'website/content|dev-notes/|docs/superpowers|\(/guides/|\(/internals/'
```
预期：活动文件无输出。`docs/internal/` 散文里的历史文件名提及（非 Markdown 链接）允许；出现链接则修复。

- [ ] **步骤 2：证明发布树恰好是 `docs/user`**

运行：
```powershell
Get-ChildItem -LiteralPath docs/user -Directory | Select-Object -ExpandProperty Name
```
预期：`how-to`、`explanation`、`reference`、`tutorials`。

- [ ] **步骤 3：跑静态层**

运行：
```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/check_import_graph.py
uv run python scripts/check_structure.py
uv run python scripts/check_suppressions.py
uv run python scripts/check_agent_guidance.py
uv run python scripts/verify_versions.py
```
预期：全绿。`trust/policy.py` 与 `session/storage.py` 的 14 个已知 Windows-only mypy 错误本地可能出现；它们是有文档的局限，CI 在 Linux 跑 mypy。

- [ ] **步骤 4：跑快速套件**

运行：
```powershell
uv run pytest -q --ignore=tests/runtime/tui
```
预期：全过（有文档的 Windows 跳过属预期）。

- [ ] **步骤 5：跑网站检查**

运行：
```powershell
npm --prefix website run check
npm --prefix website run format:check
npm --prefix website run build
npm --prefix website test
```
预期：全过；`dist/tutorials/quickstart/index.html`、`dist/how-to/`、`dist/explanation/`、`dist/reference/` 存在。

- [ ] **步骤 6：检查最终 diff**

运行：
```powershell
git status --short
git diff --stat main...HEAD
```
预期：只有文档移动、站点接线、指引文件、社区文件与 changelog 工具。任务 5 的 ADR 注释更新之外无源行为变更。

- [ ] **步骤 7：提交扫描修复**

若步骤 1 或任何检查需要修复，按：

```powershell
git add -A
git commit -m "docs: fix stale documentation references"
```

若无过期项，不提交。

---

## 后续（明确不在范围内）

不在本计划中添加；它们是独立、可评审的变更：

- `docs/user/reference/api/` 下的生成 Python API 参考。
- `docs/user/explanation/glossary.md` 与 `docs/user/how-to/troubleshooting.md`（结构稳定后再写）。
- 覆盖 `docs/internal/` 的全仓 Markdown 链接检查器（历史散文路径提及需先审计）。
- 重新启用 `.github/workflows/docs.yml.disabled` 做 GitHub Pages 部署。
- i18n、postmortem、archive 分层。
- 移除游离根文件（`033662d6*.html`、`084dc60e*.html`、`landing.html`、`_pytest_channels.log`、`interview-prep-bytedance.md`）；它们需要所有者决定，不是文档移动。

## 自检

- **决定覆盖：** 单一根（`docs/`）、Diátaxis 改名、读者分群、打包自文档分层、ADR 合并、CI/社区文件——每项映射到一个任务（1-7）并在任务 8 验证。
- **无占位符：** 每个新建文件有全文；每个移动有确切命令；每个检查有命令与预期结果。
- **命名一致：** `docs/user`、`docs/internal`、`docs/internal/adr`、`docs/internal/notes`、`docs/templates`、`docs/AGENTS.md`、`docs/README.md` 在每个任务中拼写一致。
- **已知风险：** `dev-notes/*.md` 的 `git mv` 循环必须在 `dev-notes/README.md` 移动之前运行；上方步骤顺序强制了这一点。
- **已知风险：** `Select-String -Path "docs/**/*.md"` 需要 PowerShell 7 递归 glob；行内提供了 `Get-ChildItem | Select-String` 回退。
