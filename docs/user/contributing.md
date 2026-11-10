---
title: 贡献
description: Baldric 如何开发、构建日志在哪里，以及如何在本地跑起来。
---

Baldric 以小而文档化的阶段构建——一部分是为了交付可用的 agent，一部分是为了让代码库成为"编码 agent 如何组装"的教学样本。

## 构建日志

详细的逐阶段实施笔记、设计文档与架构决策记录放在**仓库内**的 `docs/internal/` 下：

- `docs/internal/design/` — 高层设计文档（`00-roadmap`、`01-architecture`……）。
- `docs/internal/architecture/` — 逐阶段构建笔记（`phase-1` … `phase-24`），每篇回答：加了什么、为什么存在、后续阶段如何使用。
- `docs/internal/adr/` — 架构决策记录。

它们有意**不**发布在本站上——那是贡献者材料。已发布文档蒸馏结果；见 [Baldric 如何工作](/explanation/architecture/)。

## 路线图

已发布的逐阶段路线图与状态在[路线图页](/roadmap/)。底层清单记录在
[GitHub issue #2](https://github.com/Ember452/baldric/issues/2)。

## 在本地运行项目

```bash
git clone https://github.com/Ember452/baldric.git
cd baldric
uv sync --dev
uv run baldric --version
```

检查：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## 文档站点

本站是一个位于 `website/` 的 [Astro](https://astro.build/) 项目。使用 Node 22.12 或更新版本：

```bash
cd website
npm ci
npm run dev          # http://localhost:4321/
npm run check        # Astro 与 TypeScript 诊断
npm run format:check
npm run build        # 静态输出与 Pagefind 索引输出到 website/dist/
npm test             # 已构建站点与剪贴板回归测试
npm run preview      # 预览已构建站点，包括搜索
```

搜索需要构建出的 Pagefind 索引：验证搜索时用 `build` 加 `preview`，不要用开发服务器。

面向用户的文档在 `docs/user/`；落地页是
`docs/user/_index.md`，由 `website/src/components/` 里的 Astro 组件渲染。内容集合校验页面
元数据并保持既有的尾斜杠 URL。内部链接使用普通 Markdown 路径；callout 使用以 `[!NOTE]`、`[!TIP]` 或
`[!CAUTION]` 开头的引用块，后面可跟标题。GitHub Pages 仍以同一域名托管本站。文档页的代码块带一个
可用键盘聚焦的**复制**按钮。复制成功或剪贴板失败也会播报给辅助技术。

## 文档期望

每个实质性阶段都应在 `docs/internal/`
里留下面向初学者的笔记，说明加了什么、为什么存在、如何对应 [Pi](https://pi.dev) 的
设计，以及如何测试或使用。功能面向用户时，同时更新或在 `docs/user/` 下新增相关页面。
