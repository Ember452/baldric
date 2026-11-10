---
title: RPC 协议
description: 以子进程方式控制 Baldric——Pi 兼容的 JSONL 命令与事件。
---

以无头子进程运行 Baldric：

```bash
baldric --mode rpc [--provider NAME] [--model MODEL] [--cwd PATH] [--session ID]
```

RPC 模式从 stdin 逐行读取 JSON 对象（每行一个、以 LF 结尾），把响应和 session 事件以紧凑 JSON 行写到 stdout。诊断走 stderr。客户端可以带 `id`；对应响应会回显它。事件记录是异步的，通常不携带请求 ID。

```json
{"id":"1","type":"prompt","message":"Inspect this project"}
{"id":"1","type":"response","command":"prompt","success":true}
{"type":"agent_start"}
```

协议支持 Pi 兼容的 prompting（`prompt`、`steer`、`follow_up`、`abort`）、状态与消息检视、完整的 Pi 形状模型引用、模型与 thinking 轮换、自动 compaction 控制、直接 shell 命令、HTML 导出、新建/恢复 session、entry 游标、session 统计与树、fork、最后一条 assistant 查询、session 命名以及命令发现。未知命令与非法参数返回 `success: false`，进程不停止。

判断一次运行是否完全空闲要用 `agent_settled` 而不是 `agent_end`：重试、溢出 compaction 或排队续跑都可能跟在 `agent_end` 之后。

## 分帧

只在 LF（`\n`）上切分记录。CRLF 输入末尾的 CR 会被接受。U+2028、U+2029 这类 Unicode 行分隔符在 JSON 字符串里是普通字符。单条记录上限 16 MiB。

## 最小 Node/Electron 客户端

```js
import { spawn } from "node:child_process";

const baldric = spawn("baldric", ["--mode", "rpc"], { stdio: ["pipe", "pipe", "inherit"] });
baldric.stdout.setEncoding("utf8");
let buffer = "";
baldric.stdout.on("data", chunk => {
  buffer += chunk;
  for (;;) {
    const index = buffer.indexOf("\n");
    if (index < 0) break;
    const line = buffer.slice(0, index);
    buffer = buffer.slice(index + 1);
    console.log(JSON.parse(line));
  }
});
baldric.stdin.write(JSON.stringify({ id: "1", type: "prompt", message: "Hello" }) + "\n");
```

RPC 与 TUI 的 compaction 都保留最近的 entry，并返回或持久化第一条既有的保留 entry 作为 `firstKeptEntryId`，与 Pi 一致。session 检视以 Pi 的原生形状发出现代 compaction，不再使用 Baldric 早期的替换 id 桥接。较旧的 Baldric 记录可能缺少边界；检视会把它们如实暴露为 `customType: "baldric.compaction"` entry，而不是伪造 Pi 的 compaction 元数据。它们的旧 id 列表仍可用于本地回放，但不进入 RPC wire 格式。在可用时，投影出的 compaction 与 branch-summary entry 会携带生成摘要那次请求的 Pi 兼容 `usage` 数据；旧 entry 与启发式回退摘要省略该字段。

session 检视以 Pi wire 形状投影持久化的 `custom_message` entry：`parentId`、`customType`、`content`、`details` 与 `display`。Baldric 本地 session JSONL 使用 `parent_id`、`custom_type` 这类 snake_case 包装字段；客户端应依赖 RPC 形状，而不是存储层的拼写。

在公开 `CodingSession` 具备等价行为的范围内，Baldric 与 Pi 保持镜像。支持直接 `bash`，但 `abort_bash` 需要未来的可取消 session API。队列投递模式、重试控制、克隆、图片 prompt 与 extension UI 请求/响应子协议仍是分阶段的兼容性工作。契约、已完成的前端关键阶段与剩余的生产阶段见 `docs/internal/design/rpc-runtime-interchangeability-plan.md`。
