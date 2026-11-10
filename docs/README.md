# Baldric 文档

本目录是 Baldric 文档的唯一事实来源。

## 从这里开始

- 初识 Baldric：[tutorials/quickstart.md](user/tutorials/quickstart.md)
- Baldric 是什么、为什么：[explanation/what-is-baldric.md](user/explanation/what-is-baldric.md)
- 任务配方：[user/how-to/](user/how-to/_index.md)
- 查询：[user/reference/](user/reference/_index.md)
- Baldric 如何工作：[user/explanation/](user/explanation/_index.md)

## 地图

| 目录 | 读者 | 内容 |
| --- | --- | --- |
| `user/` | 使用 Baldric 的人 | 已发布的指南、参考与解释 |
| `internal/` | 贡献者 | ADR、架构日志、设计、笔记、计划、规格 |
| `assets/` | 仓库 README 与文档 | 图片与图示 |
| `templates/` | 贡献者 | ADR、设计、计划的起点模板 |

## 给贡献者

- 文档标准：[AGENTS.md](AGENTS.md)
- 决策：[internal/adr/](internal/adr/)
- 架构日志：[internal/architecture/](internal/architecture/)
- 设计：[internal/design/](internal/design/)
- 功能笔记：[internal/notes/](internal/notes/)
- 计划与规格：[internal/plans/](internal/plans/)、[internal/specs/](internal/specs/)

## 发布站点

`docs/user/` 是 `website/src/content.config.ts` 配置的 Astro 内容基底。
`docs/internal/`、`docs/templates/`、`docs/assets/` 永不发布。

`src/baldric/runtime/data/docs/` 的打包自知识随 wheel 发布、由 agent 在运行时
读取；它与本目录刻意分开。
