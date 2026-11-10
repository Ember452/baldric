---
title: 内置工具
description: agent 用来在你的项目里干活的 read、write、edit 与 bash 工具。
---

工具是 agent 能在你的工作目录里采取的动作。由模型决定何时调用；Baldric 执行它们并把结果流式返回。Baldric 内置四个编码工具：`read`、`write`、`edit` 与 `bash`。

所有路径都相对 session 的工作目录（`--cwd`，或你启动 Baldric 的目录）解析。

> [!NOTE]
> 本页记录工具的*行为*——模型能在你的机器上做什么。要构建 frontend 或注册自己的工具，见[构建自定义 frontend](/explanation/custom-frontend/)。

## `read`

从磁盘读取文件。

```json
{ "path": "README.md", "offset": 1, "limit": 40 }
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `path` | 是 | string | 要读的文件（相对 `cwd`）。 |
| `offset` | 否 | integer | 1 起始的起始行（`0` = 从文件开头）。 |
| `limit` | 否 | integer | 最多返回的行数。 |

对文本文件，`read` 返回 UTF-8 内容，应用 `offset`/`limit`，并截断到最多 2,000 行或 50 KB（以先到者为准），追加形如 `[42 more lines in file. Use offset=101 to continue.]` 的提示。受支持的图片（JPEG、静态 PNG、GIF、WebP、BMP）从文件内容识别，作为图片附件发给具备视觉能力的模型。BMP 会转换为 PNG。Baldric 校验图片，必要时在不放大、不改变宽高比的前提下缩放。处理后的附件限制为两边不超过 2,000 像素且不超过 5 MB。超过 50 MB 或 4000 万像素的源文件会被拒绝。动画 PNG 与 JPEG XL 输入会收到明确的不支持格式提示。如果解码、转换或缩放无法产出安全的附件，Baldric 返回明确的省略说明。

如果在图片工具结果之后 provider 仍立即拒绝请求，Baldric 会省略这些图片并附带 API 错误重试一次。模型随后可以换一张更小的图或另一个方案，而不必重跑原有工具。恢复在连续第三次 provider 失败时停止；成功响应会重置计数。provider 级的网络重试仍然独立。部分流式响应与取消不适用这种重试。原图与 API 错误保留在 session 历史里，但被拒附件不再进入后续的模型 context。

当活动模型不接受图片时，`read` 返回明确的纯文本提示，说明图片内容不可用并建议换用具备视觉能力的模型。它不会附加或处理图片。provider 序列化对来自旧 session 或其他工具的图片块应用同样的防御性降级。这避免无效请求，并减轻纯文本模型凭空描述图片的压力。

Textual TUI 会显示这条提示，但不内联渲染图片；原生的终端图片渲染仍在 `read` 工具的 provider 中立契约之外。

`path` 缺失/非法、文件不存在、路径是目录、`offset` 超过文件末尾，或文件既不是 UTF-8 文本也不是受支持图片时失败。

## `write`

创建或完整覆盖一个 UTF-8 文本文件。

```json
{ "path": "src/example.py", "content": "print('hello')\n" }
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `path` | 是 | string | 要写的文件（相对 `cwd`）。 |
| `content` | 是 | string | 完整的文件内容。 |

自动创建缺失的父目录并覆盖已存在的文件。对同一路径的写入在进程内串行化，所以并发的 `write`/`edit` 调用不会交错。

## `edit`

对一个文件应用精确的文本替换。

```json
{
  "path": "src/example.py",
  "edits": [
    { "oldText": "print('hello')", "newText": "print('hello, Baldric')" }
  ]
}
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `path` | 是 | string | 要编辑的文件（相对 `cwd`）。 |
| `edits` | 是 | array | 一或多条 `{oldText, newText}` 替换。 |

每条 `oldText` 必须非空、精确匹配（包括空白）、**恰好出现一次**，且与其他编辑不重叠。所有编辑先整体校验再写入——任何一条失败，文件保持不变。行尾在匹配时归一化，并还原为原本占主导的行尾风格。成功结果包含 diff、unified patch 与第一处变更的行号。

## `bash`

在工作目录里运行 shell 命令。

```json
{ "command": "pytest -q", "timeout": 30 }
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `command` | 是 | string | 要运行的 shell 命令。 |
| `description` | 否 | string | 命令用途的短摘要，显示为该调用的标签。 |
| `timeout` | 否 | number | 最长运行秒数（> 0）。无默认值。 |

合并 stdout 与 stderr，退出码 `0` 视为成功，大输出返回**尾部**（截断到 2,000 行 / 50 KB；完整输出写入一个临时 `.log` 文件，路径包含在结果里）。

shell 每个 session 解析一次，工具描述里会写明它：POSIX 上是 `bash`（没有 bash 时用 `sh`）；Windows 上是 PowerShell（`pwsh`，然后 Windows PowerShell，均以 `-NoProfile -NonInteractive` 运行），最终回退到 `cmd.exe`。用对应 shell 的语法写命令——在 Windows 上这个工具不会假装自己是 bash。超时或取消会终止整棵进程树（POSIX 上是进程组，Windows 上 `taskkill /T`），所以管道或复合命令启动的子进程不会继续运行。

## 如何选工具

- **`read`** — 查看文件（替代 `cat`/`sed`）。
- **`write`** — 新文件或完整重写。
- **`edit`** — 对现有文件的精确修改。
- **`bash`** — 测试、lint、搜索、项目检视。
