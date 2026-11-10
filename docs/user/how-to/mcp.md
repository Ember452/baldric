---
title: MCP 服务器
description: 连接 MCP 服务器，让它们的工具出现在 Baldric 内置工具旁边。
---

**MCP**（Model Context Protocol）是向 AI agent 暴露工具的开放标准。Baldric 是 MCP **客户端**：你配置的服务器贡献工具，它们出现在内置工具旁边，无需特殊提示。

## 配置服务器

Baldric 从两个位置读取 `mcp.json`：

- **用户级**：`~/.baldric/mcp.json` —— 你的服务器，处处可用。
- **项目级**：`<project>/.baldric/mcp.json` —— 仅在项目[受信任](/how-to/project-trust/)时加载。同名项目条目替换用户条目；只带 `"enabled"` 的条目只覆盖那一个开关（把全局服务器在某个仓库里关掉时很顺手）。

两者使用与 Claude Desktop 及其他 MCP 客户端相同的形状，既有配置可以直接拷过来：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
      "cwd": "~"
    },
    "docs": {
      "url": "https://docs.example.com/mcp",
      "headers": { "Authorization": "Bearer ${DOCS_TOKEN}" }
    }
  }
}
```

| 字段 | 适用于 | 含义 |
| --- | --- | --- |
| `command`、`args`、`env`、`cwd` | stdio 服务器 | 启动一个经 stdin/stdout 说 MCP 的本地程序 |
| `url`、`headers` | Streamable HTTP 服务器 | 连接远程端点 |
| `type` | 两者 | 可选（`"stdio"` 或 `"http"`）；缺失时从 `command`/`url` 推断，不一致时校验报错 |
| `timeout` | 两者 | 单次调用超时秒数（默认 60）；进度通知会重置它 |
| `description` | 两者 | 描述服务器的一行话，显示在 system prompt 里 |
| `enabled` | 两者 | `false` 保留条目但不连接 |

`env`、`headers`、`command`、`cwd` 里的值可以引用环境变量（`${NAME}`）——按 Baldric 运行所在的环境展开。无法解析的变量产生警告且条目以禁用状态启动。`command` 与 `cwd` 里 `~` 展开为你的用户目录。

## 管理服务器：`/mcp`

```text
/mcp                    # 列出服务器：名字、状态、transport、工具数
/mcp restart <name>     # 重读配置并重连一个服务器
/mcp off <name>         # 为该项目/用户禁用一个服务器
/mcp on <name>          # 重新启用
```

`on` 与 `off` 把决定写回定义该服务器的 `mcp.json`（你的选择跨 session 记住），然后立即连接或关闭。

## 工具命名

MCP 工具以普通工具出现，名为 `mcp__<server>__<tool>`——例如 `mcp__filesystem__read_file`。名字净化为字母、数字与下划线；若会超出 64 字符上限或与其他工具冲突，加一个短哈希后缀保持唯一。与其他 MCP 客户端相同的命名规则，工具的排序与分组因此一致。

## 状态与重连

每个服务器在 `connecting`、`connected`、`disconnected`、`needs-auth`、`failed`、`closed` 之间流转：

- 你的第一条消息最多等 10 秒给 connecting 中的服务器，让它们的工具真正可调用；启动本身绝不因此延迟。
- 掉线（例如服务器进程退出）标记为 `disconnected`；下一次工具调用自动重连。
- 启动失败的服务器标记 `failed`，其工具被撤回直到再次连接——session 其余部分继续工作。
- 应答 401 的 HTTP 服务器标记 `needs-auth`。Baldric 的 MVP 不含 MCP OAuth；改用带凭据的 header。

## 已知限制

- 无 MCP OAuth、resources、prompts、sampling——只有工具。
- 工具结果只呈现文本与图片：图片变成 `[image: mime, N bytes]` 占位符，其他内容块（内嵌资源、音频）变成 `[unsupported content block: …]`。
- 支持 `${NAME}` 展开；pi 的 `!command` shell 替换有意不支持（解析配置时跑 shell 超出范围）。
- 连接后才添加工具的服务器保持连接时的工具集，直到你运行 `/mcp restart <name>`。
- Subagent 子 session 不获得 MCP：每个 child 各起一套服务器进程太浪费。父 session 通过委托与子代理共享 MCP 工具。
