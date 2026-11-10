# 项目信任运行时

Issue #535 给环境性项目资源加了一道 `baldric_coding` 输入加载守卫。已接受策略与 Pi 兼容性研究保留在
`dev-notes/design/project-trust.md`（现 `docs/internal/design/project-trust.md`）。

## 运行时形状

- `project_trust.py` 拥有类型化的请求/解析、严格的 cwd
  规范化、仅元数据的检测、优先级、每 cwd 缓存，以及加锁的版本 1 原子存储。
- `BaldricResourcePaths.project_resources_enabled` 创建一份连贯的资源计划。既有的 skill、prompt、context、system prompt、主题与 extension 加载器消费该计划，而不各自实现策略。
- `CodingSession.load` 先只导入用户/显式 extension，解析信任，然后加载受保护的 Markdown/JSON 与选择加入的项目 extension。
- CLI 入口提供用户全局默认与调用级覆盖。
  结构化/无头模式不提示。TUI 把 frontend 中立的请求适配为无障碍的 Textual 弹窗。
- reload 与目标替换在采纳之前 stage 全新的 cwd 绑定 extension runtime、
  资源、工具、命令、prompt 与信任缓存条目。
  资源计划无条件重绑到规范目标；源项目注册绝不跨 cwd 边界。取消或任何准备失败保留当前快照与先前协调器缓存。

`baldric_agent` 没有信任、路径、Typer 或 Textual 依赖。Textual 留在
`baldric_coding.tui`。

## 持久化与失败行为

`~/.baldric/trust.json` 有 `version` 与排序的 `decisions`。读取拒绝未知
字段/版本、重复或相对/未归一化路径与未知值。更新先锁存储、持久装好 mode-0600 的撤销日志，
再写/fsync 同目录临时文件、替换 `trust.json` 并 fsync 目录。读取者拒绝任何有待处理日志的存储。日志只在目标提交点之后移除；失败尝试恢复，
恢复失败则日志原地保留——即使提交与恢复双双失败，新授予的字节也不可能暴露。日志清理的 fsync
失败在两种持久结果下都安全：已提交存储保持可见，或日志重现、读取 fail closed。错误诊断并 fail closed；
仅本次的显式批准不依赖存储。

## 迁移

没有 legacy 存储。既有项目不被自动信任。存在受保护候选时交互式用户决定；未解析的无头 `ask` 跳过
项目输入。用户/全局与 CLI 显式资源继续加载。
`--project-extensions` 仍是额外的可执行代码选择加入。

## 验证

使用临时 home/项目与 fake extension/provider。运行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

项目信任不是文件系统/进程/网络/工具/模型沙箱。
