---
title: "03 — 工具"
---

工具让 assistant 通过结构化调用检视并修改用户的环境。

本页是内置工具行为的面向用户的事实来源。Python
工厂函数也有面向贡献者的 docstring，但生成的 API 参考文档被有意推迟；见
[ADR 0002](../adr/0002-keep-tool-docs-hand-written.md)。

Baldric 把"工具"这个概念与任何具体 frontend 分开：

- `baldric_agent` 定义 provider 中立的工具类型并执行被请求的 tool 调用。
- `baldric_coding` 提供针对文件与 shell 命令的具体本地编码工具。
- CLI、TUI 与其他 frontend 决定向 session 暴露哪些工具。

## 内核模型

`AgentTool` 有：

- 一个 `name`，如 `read` 或 `bash`
- 人类可读的 `description`
- 描述可接受 JSON 参数的 `input_schema`
- 异步 `executor`
- 组装工具指引的客户端使用的可选 prompt 元数据

工具返回 `AgentToolResult`，含：

- `ok`：工具是否成功完成
- `content`：可回传给模型的文本
- 可选 `data`：供 UI、日志或未来集成的结构化元数据
- 可选 `error`：机器可读或人类可读的错误消息

agent loop 执行 tool call 并把结果转换为 transcript 中的 `ToolResultMessage` entry。

## 内置编码工具

`baldric_coding` 提供四个内置本地编码工具：

- `read`
- `write`
- `edit`
- `bash`

用 `create_coding_tools()` 一次注册全部：

```python
from baldric_coding import create_coding_tools

tools = create_coding_tools(cwd="/path/to/project")
```

或单独创建：

```python
from baldric_coding import (
    create_bash_tool,
    create_edit_tool,
    create_read_tool,
    create_write_tool,
)
```

传给工具的相对路径对照 `cwd` 解析。省略 `cwd` 时，Baldric 使用工厂被调用那一刻的进程当前工作目录。

## `read`

从磁盘读取文件。

工厂函数：

- `create_read_tool_definition()`
- `create_read_tool()`

### 参数

```json
{
  "path": "README.md",
  "offset": 1,
  "limit": 40
}
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `path` | 是 | string | 要读的文件路径。相对路径对照 `cwd` 解析。 |
| `offset` | 否 | integer | 1 起始的起始行号。`0` 作为文件开头的别名被接受。 |
| `limit` | 否 | integer | 最多返回的行数。 |

`offset` 提供时必须是非负整数。`limit` 必须是正整数。

### 文本行为

对文本文件，`read`：

1. 以 UTF-8 文本打开文件
2. 应用提供的 `offset` 与 `limit`
3. 把大输出截断到最多 2,000 行或 50 KB，以先到者为准
4. 还有更多行时追加续读提示

续读提示示例：

```text
[42 more lines in file. Use offset=101 to continue.]
```

### 图片行为

受支持的图片文件按 MIME 类型识别：

- JPEG
- PNG
- GIF
- WebP

对受支持的图片，`read` 返回一条短文本消息，并把图片元数据存进 `data`，包括：

- 解析后的路径
- MIME 类型
- 字节大小
- base64 编码的图片字节

### 错误

`read` 在以下情况失败：

- `path` 缺失或不是字符串
- `offset` 为负，或 `limit` 不是正整数
- 文件不存在
- 路径是目录
- `offset` 超出文件末尾
- 文件无法按 UTF-8 解码且不是受支持图片

## `write`

创建或完整覆盖一个 UTF-8 文本文件。

工厂函数：

- `create_write_tool_definition()`
- `create_write_tool()`

### 参数

```json
{
  "path": "src/example.py",
  "content": "print('hello')\n"
}
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `path` | 是 | string | 要写的文件路径。相对路径对照 `cwd` 解析。 |
| `content` | 是 | string | 要写入的完整文件内容。 |

### 行为

`write`：

1. 解析目标路径
2. 创建缺失的父目录
3. 以 UTF-8 编码写入 `content`
4. 覆盖该路径上任何既有文件

写入在当前进程内按解析后的路径串行化。这意味着并发指向同一文件的 `write` 或 `edit` 操作不会交错。

### 结果元数据

成功结果包括：

- 解析后的路径
- 写入的字符数

### 错误

`write` 在以下情况失败：

- `path` 缺失或不是字符串
- `content` 缺失或不是字符串
- 文件系统拒绝写操作

## `edit`

对一个 UTF-8 文件应用精确的文本替换。

工厂函数：

- `create_edit_tool_definition()`
- `create_edit_tool()`

### 参数

```json
{
  "path": "src/example.py",
  "edits": [
    {
      "oldText": "print('hello')",
      "newText": "print('hello, Baldric')"
    }
  ]
}
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `path` | 是 | string | 要编辑的文件路径。相对路径对照 `cwd` 解析。 |
| `edits` | 是 | array | 一或多条替换对象。 |
| `edits[].oldText` | 是 | string | 要替换的确切文本。必须非空且在原文件中唯一。 |
| `edits[].newText` | 是 | string | 替换文本。 |

### 匹配规则

每条 `oldText` 必须：

- 非空
- 精确匹配，包括空白与换行
- 在原文件中恰好出现一次
- 不与另一条编辑的匹配范围重叠

所有 `oldText` 都对照原文件内容匹配，而不是对照先前编辑的结果。

### 回滚行为

`edit` 在写入前校验每条替换。任何一条编辑校验失败，文件保持不变。

### 行尾与 BOM

匹配时，Baldric 把文件内容与编辑文本归一化为 LF 行尾。应用编辑后，Baldric 还原文件原本占主导的行尾。UTF-8 字节序标记保留。

### 结果元数据

成功结果包括：

- 解析后的路径
- 应用的编辑数
- `ndiff` 风格的 diff
- unified patch
- 首个变更行号

### 错误

`edit` 在以下情况失败：

- `path` 缺失或不是字符串
- 文件不存在
- 路径是目录
- `edits` 缺失、为空或畸形
- 任一 `oldText` 为空
- 任一 `oldText` 未找到
- 任一 `oldText` 出现多次
- 编辑范围重叠
- 所有替换加起来文件毫无变化

## `bash`

在配置的工作目录里执行 shell 命令。

工厂函数：

- `create_bash_tool_definition()`
- `create_bash_tool()`

### 参数

```json
{
  "command": "pytest -q",
  "timeout": 30
}
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `command` | 是 | string | 要执行的 shell 命令。 |
| `timeout` | 否 | number | 最长运行秒数。提供时必须大于零。 |

没有默认超时。需要有界执行的调用者应自行提供。

### 行为

`bash`：

1. 以 `cwd` 作为子进程工作目录运行命令
2. 把 stdout 与 stderr 合并为单一输出流
3. 把输出按 UTF-8 解码，替换无效字节
4. 命令以退出码 `0` 结束时返回成功
5. 命令非零退出或超时时返回失败

POSIX 系统上，命令在新会话中启动。发生超时时，Baldric 杀掉整个进程组，管道或复合命令的子进程一并停止。非 POSIX 系统上，Baldric 杀掉直接子进程。

### 输出截断

`bash` 返回大输出的尾部。输出截断到最多 2,000 行或 50 KB，以先到者为准。

发生截断时，Baldric 把完整命令输出写入临时 `.log` 文件，并把该路径放进结果元数据。

### 结果元数据

结果包括：

- 命令字符串
- 退出码
- 命令是否超时
- 以秒计的时长
- 截断元数据
- 输出被截断时的完整输出临时文件路径

### 错误

`bash` 在以下情况失败：

- `command` 缺失或不是字符串
- `timeout` 不是大于零的数字
- 命令以非零状态退出
- 命令超时
- 子进程无法启动

## 如何选工具

- 用 `read` 检视文件内容，而不是 shell 出去跑 `cat` 或 `sed`。
- 新文件或完整重写用 `write`。
- 对既有文件的精确修改用 `edit`。
- 测试、lint、搜索、项目检视之类的命令用 `bash`。
