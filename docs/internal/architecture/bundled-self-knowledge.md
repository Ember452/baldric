# 打包的 Baldric 自知识

Baldric 遵循 Pi 的渐进披露方式管理产品知识。默认 system prompt 指明已安装的文档与示例，然后把 Baldric 专属请求路由到那些文件，而不把它们加载进每段对话。

## 打包资源

自知识位于 `src/baldric_coding/data/`：

```text
docs/       concise routing references and contributor workflows
examples/   readable extension examples
```

prompt 直接指向 extension 创建、skill、自定义与内置 provider/model、CLI 命令、TUI 行为与架构。它告诉 agent 先完整阅读相关文档与示例、跟随其交叉引用，再动手实现。

Baldric 不把自己的维护流程暴露为 Agent Skills。skill 是用户与项目资源，因此 Baldric 的产品文档不出现在 skill 侧栏、不与用户 skill 名冲突、也不在禁用 skill 加载时消失。

## 为什么

仓库的 `AGENTS.md` 只在 Baldric 运行于其源码 checkout 内时有用。打包文档让已安装的 Baldric 保有产品知识而不撑大基础 prompt。把文档与 skill 分开也保住了干净的用户自有 skill 命名空间，与 Pi 的设计一致。

extension 与 model/provider 文档收纳了原打包 `create-baldric-extension` 与 `baldric-model-catalog` skill 承载的详细流程。打包的 extension 示例仍作为具体起点可用。

## 架构

自文档属于 `baldric_coding`，不属于可移植的 `baldric_agent` harness。`self_docs.py` 解析已安装文档与示例路径，`system_prompt.py` 发出路由提示。`BaldricResourcePaths` 只发现用户与项目 skill。Hatch 把文档与示例作为 `baldric_coding` 的一部分打包。

## 验证

```bash
uv run pytest tests/test_system_prompt.py tests/test_skills.py tests/test_resources.py tests/test_package_metadata.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```
