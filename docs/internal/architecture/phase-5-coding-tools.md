---
title: "Phase 5：内置编码工具"
---

Phase 5 在 `baldric_coding` 加了 Baldric 最早的内置编码工具。

工具住在：

```text
src/baldric_coding/tools.py
```

## 加了什么

Baldric 现在为这些初始工具提供工厂函数：

- `create_read_tool()`
- `create_write_tool()`
- `create_edit_tool()`
- `create_bash_tool()`
- 默认工具集的 `create_coding_tools()`

每个工厂有一个 Pi 风格的 `ToolDefinition` 对应物：描述、prompt snippet、prompt guideline、JSON schema 与执行器。公开工厂返回来自 `baldric_agent.tools` 的 provider 中立 `AgentTool`。

## 工具为什么住在 `baldric_coding`

`baldric_agent` 拥有可移植的 agent 大脑：消息、事件、作为抽象的工具、循环与 harness。

文件系统与 shell 访问是编码 agent 环境特性，所以具体实现住在 `baldric_coding`。

```text
baldric_agent:
  knows how to execute an AgentTool

baldric_coding:
  provides read/write/edit/bash tools for local coding work
```

这保持内核循环可复用、独立于本机行为。

## 工具行为

### `read`

读取 UTF-8 文本文件。

参数：

- `path`：文件路径
- `offset`：可选的 1 起始起始行；`0` 作为文件开头的别名被接受
- `limit`：可选的返回行数

大输出按 Pi 风格截断元数据与续读提示截断。受支持的图片文件（`jpg`、`png`、`gif`、`webp`）被识别并以 base64 元数据返回，供后续 UI/provider 集成使用。

### `write`

写入完整的 UTF-8 文本文件，需要时创建父目录。写入按路径经文件变更队列串行化，同一文件的并发变更不会交错。

参数：

- `path`：文件路径
- `content`：完整文件内容

### `edit`

对 UTF-8 文件应用精确的文本替换。

参数：

- `path`：文件路径
- `edits`：`{ oldText, newText }` 对象数组

重要的 Pi 式行为：

- 每条 `oldText` 必须恰好匹配一次
- 编辑不得重叠
- 校验发生在写入之前
- 任一编辑失败，文件保持不变
- UTF-8 BOM 保留
- 既有行尾保留
- 结果包含 diff、unified patch 与首个变更行元数据
- legacy `oldText`/`newText` 参数与 JSON 字符串 `edits` 被归一化

### `bash`

在配置的工作目录里执行 shell 命令。

参数：

- `command`：命令字符串
- `timeout`：可选的秒数超时，无默认超时

结果包括合并的 stdout/stderr 输出、退出码、超时状态、时长、截断元数据，以及输出被截断时的完整输出临时文件路径。

## 怎么使用这些工具

```python
from baldric_coding import create_coding_tools

tools = create_coding_tools(cwd="/path/to/project")
```

把这些工具传给 `AgentHarnessConfig` 或直接传给 `run_agent_loop()`。

## 测试

本阶段覆盖于：

```text
tests/test_coding_tools.py
```

测试验证：

- 默认工具注册
- 带行切片的文件读取
- 写入时的父目录创建
- 多编辑精确替换
- 编辑失败回滚
- 唯一匹配校验
- bash stdout 捕获
- bash 超时报告

## 下一阶段

下一阶段可以把这些工具接进非交互 print-mode CLI，让用户从终端对真实项目运行 Baldric。
