---
title: "Phase 10：system prompt 组装"
---

Phase 10 加了 Baldric 的规范 system prompt 构建器。

实现位于：

```text
src/baldric_coding/system_prompt.py
```

## 加了什么

Baldric 现在能从以下输入构建确定性的 Pi 风格 system prompt：

- Baldric 默认的编码 agent 身份
- 启用的工具
- 工具 prompt snippet
- 工具 prompt guideline
- 额外 guideline
- 可选自定义 prompt 文本
- 可选追加 prompt 文本
- 项目 context 文件
- 已加载 skill
- 当前日期
- 当前工作目录

## 为什么存在

更早的阶段加了工具、skill、prompt template 与 coding session。本阶段之前，CLI 用一个只列工具的小型本地 prompt 构建器。Baldric 现在有一条共享的 prompt 组装层，print mode、coding session 与后续 UI/session frontend 都能用。

## 默认 prompt 形状

默认 prompt 以 Baldric 身份开头：

```text
You are an expert coding assistant operating inside Baldric, a coding agent harness.
```

随后是使用每个工具 `prompt_snippet` 的可用工具区块：

```text
Available tools:
- read: Read file contents
- write: Create or overwrite files
- edit: Make precise file edits ...
- bash: Execute bash commands ...
```

然后是从启用工具收集的 guideline：

```text
Guidelines:
- Use bash for file operations like ls, rg, find
- Use read to examine files instead of cat or sed.
- Use write only for new files or complete rewrites.
- Be concise in your responses
- Show file paths clearly when working with files
```

guideline 按确定性顺序去重。

默认 prompt 还镜像 Pi 的渐进披露文档块（已为 Baldric 改写）。它指向打包的 Baldric 文档与示例（extension、
skill、provider/模型、命令、TUI 行为与架构），并告诉模型只在 Baldric 专属问题时阅读它们。自定义 prompt 仍会替换这个默认文档块。

## 自定义 prompt

提供 `custom_prompt` 时，它替换默认的 Baldric 身份、工具与 guideline 区块。

自定义 prompt 之后 Baldric 仍追加这些，匹配 Pi 行为：

1. 追加的 system prompt 文本
2. 项目 context
3. skill 区块（`read` 工具启用时）
4. 当前日期
5. 当前工作目录

## 项目 context

项目指令以 `ProjectContextFile` 值表示并按 Pi 的类 XML 风格格式化：

```xml
<project_context>

Project-specific instructions and guidelines:

<project_instructions path="/repo/AGENTS.md">
...content...
</project_instructions>

</project_context>
```

Phase 10 格式化提供的 context 文件。`AGENTS.md` 与 `CLAUDE.md` 之类文件的完整发现可以日后扩展。

## skill

skill 按 Pi 的 XML 风格 skill 索引格式化：

```xml
<available_skills>
  <skill>
    <name>python-testing</name>
    <description>Write and run Python tests.</description>
    <location>/home/user/.baldric/skills/python-testing/SKILL.md</location>
  </skill>
</available_skills>
```

Baldric 只在 `read` 工具启用时包含 skill 区块。这镜像 Pi：任务匹配某个 skill 描述时，模型应使用 `read` 加载完整 skill 文件。

prompt template 不插入 system prompt。它们是用户 prompt 展开资源。

## 集成

print mode 现在用 `build_system_prompt()` 而不是本地最小 prompt 构建器。

`CodingSessionConfig.system` 现在可选。省略时 `CodingSession.load()` 从以下输入构建 system prompt：

- cwd
- 配置的工具或默认编码工具
- 已加载 skill
- 自定义/追加 prompt 选项
- 提供的 context 文件

既有调用者仍可传显式 `system` 字符串。

## 测试

本阶段覆盖于：

```text
tests/test_system_prompt.py
tests/test_cli.py
tests/test_coding_session.py
```

测试验证：

- 默认 prompt 区块
- 可用工具格式化
- 无 snippet 的隐藏工具
- guideline 去重
- 自定义 prompt 行为
- 项目 context 格式化
- skill XML 转义
- 仅 `read` 启用时包含 skill
- print-mode 集成
- coding-session 集成

## 下一阶段

路线图下一阶段是 Rich 控制台渲染。这里引入的 system prompt 构建器给未来 frontend 一条共享 prompt 组装层，而不必复刻 prompt 逻辑。
