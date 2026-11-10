---
title: "ADR 0002 — 内置工具文档暂时保持手写"
---

## 状态

已接受。

## 背景

`src/baldric_coding/tools.py` 里的内置编码工具有详细的 Python docstring，Baldric 同时在 `docs/03-tools.md` 里维护面向初学者的工具文档。

这带来一些重复。生成的 API 参考（例如经 `mkdocstrings`）可以直接把 `create_read_tool_definition()`、`create_bash_tool_definition()` 这类工厂 docstring 渲染进文档站点，减少代码与文档的漂移。

Baldric 的文档当前服务两类读者：

- 需要理解工具行为、参数、结果、错误与示例的用户与 frontend 作者
- 需要工厂函数与实现边界 API 级细节的 Python 贡献者

## 决策

暂时保持 `docs/03-tools.md` 作为面向用户的内置工具行为的事实来源。Python docstring 继续作为贡献者侧的 API 文档，但暂不向 MkDocs 构建添加生成的 API 页面。

如果 Baldric 日后需要正式的 API 参考，可以再添加生成的 API 文档。届时它应当补充概念文档，而不是替换它们。

## 理由

手写工具文档仍是解释那些对 agent 用户重要行为的最佳方式：

- 常见编码任务该选哪个工具
- JSON 参数形状与校验规则
- 截断行为与续读提示
- TUI 与日志层可能消费的结果元数据
- 示例与实际错误场景

工厂 docstring 有用，但读起来像 API 参考材料。它们替代不了示例、行为注记，以及架构仍在演化时 Baldric 需要的面向初学者的解释。

现在引入 `mkdocstrings` 还会扩大文档构建面：新依赖、插件配置、严格构建期的 import 副作用，以及 CI 的新失败模式。在公开 API 还小、手写文档足够明确时，这个代价不划算。

## 未来 API 参考的要求

若 Baldric 日后采用生成的 docstring 文档，生成页应：

- 放在独立的 API Reference 分区下
- 包含 `ToolDefinition`、`create_coding_tools()` 与 `create_read_tool_definition()` 等单个工厂函数
- 不替换 `docs/03-tools.md`
- 示例与行为注记保留在手写的概念页里
- 在 `mkdocs build --strict` 下运行，不导入 provider 配置、不读用户文件、不需要可选的运行时设置

## 后果

- 用户可见契约变化时，工具行为变更必须同时更新相关 docstring 与
  `docs/03-tools.md`。
- 文档构建保持纯 Markdown，CI 保持简单。
- 未来的生成 API 参考可以作为独立文档特性引入，不改当前用户文档结构。
