# docs/ - 文档标准

本文件约束 `docs/` 下的全部内容。根目录 `AGENTS.md` 依然适用；本文件只追加
文档的存放位置与写作规则。

## 语言

- **文档优先用中文写作。** `docs/` 下新建或改写的文档，正文一律用中文，
  `docs/internal/` 同样适用。
- 代码块、命令、frontmatter 键名、文件路径、链接目标保持原样，不翻译。
- 专有技术名词保留英文原文（agent loop、provider、tool、skill、prompt
  template、extension、session、TUI、compaction、frontend 等），行文用中文。
- 不新建英文文档；英文原文由 git 历史保存。

## 两类读者

| 路径 | 读者 | 是否发布 |
| --- | --- | --- |
| `docs/user/` | 使用 Baldric 的人 | 是，由 `website/` 发布 |
| `docs/internal/` | 维护 Baldric 的贡献者 | 否 |
| `docs/assets/` | 仓库 README 与文档 | 否 |
| `docs/templates/` | 新文档的起点 | 否 |

`src/baldric/runtime/data/docs/` 是独立的层：打包进 wheel、由 agent 在运行时
读取的自知识。不要把用户文档移进去，也不要把它当作文档源。

## 存放位置（一个事实只有一个家）

| 目录 | 职责 | 不属于这里的内容 |
| --- | --- | --- |
| `docs/user/tutorials/` | 有序的首次上手路径；只介绍下一步需要的东西 | 参考表、设计理由 |
| `docs/user/how-to/` | 任务配方：目标、步骤、验证 | 教学序列、架构随笔 |
| `docs/user/reference/` | 查询：命令、旗标、环境变量、文件格式 | 叙事、教程 |
| `docs/user/explanation/` | 系统为何长成这样；架构与概念 | 分步操作 |
| `docs/internal/adr/` | 已接受或已否决的决策，一文件一决策，统一编号 | 进行中的工作计划 |
| `docs/internal/architecture/` | 既成事实的阶段日志与子系统笔记 | 前瞻性提案 |
| `docs/internal/design/` | 实现前写下的设计 | 事故纪实 |
| `docs/internal/notes/` | 功能构建日志与调查 | 现行的面向用户的解释 |
| `docs/internal/plans/` | 可执行的工作计划 | 已被接受的决策（应写 ADR） |
| `docs/internal/specs/` | 计划所实现的详细规格 | 流水账式任务清单 |

事实属于别处时，链接到拥有它的文档，不要复述。

## 写作规则

- `docs/user/` 描述当前行为。历史、被否决的替代方案、实现日志归
  `docs/internal/`。
- **正文用中文**；代码、命令、路径、专有名词按「语言」一节的规则保留。
- 用户文档中的站内链接用根相对路径：`/how-to/...`、`/reference/...`、
  `/explanation/...`。Astro 构建会为发布的基础路径改写它们。
- 指向仓库文件的链接用仓库相对路径。永远不要在文档里硬编码
  `github.com/.../blob/main/...` 这样的文件 URL。
- 每个 `docs/user/` 页面以 `title` frontmatter 开头；多页站点分区
  （`how-to/`、`reference/`、`explanation/`）各有恰好一个 `_index.md`；
  单页分区 `tutorials/` 没有。
- 参考页用表格或定义列表，不写叙事段落。
- 命令必须可直接复制执行；Python 命令用 `uv run`。
- 用户文档里不写状态注记（"已实现"、"即将推出"）；状态归 roadmap 与
  release notes。
- 新决策用 `docs/templates/adr.md` 起 ADR；新的多步工作用
  `docs/templates/plan.md` 起计划。

## 验证

- 用户文档：`npm --prefix website run build && npm --prefix website test`。
- 贡献者文档：被改动文件里的链接必须相对其所在位置可解析。
- 发布站点绝不能包含 `docs/internal/`、`docs/templates/`、`docs/assets/`：
  Astro 内容基底是且仅是 `docs/user`。
