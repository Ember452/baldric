# Baldric/Pi RPC 运行时可互换计划

## 目标

Electron 宿主应能用一个产品设置选择任一子进程：

```json
{"agent_runtime": "baldric"}
```

运行时专属的启动配置（二进制路径、provider/model、cwd、session 位置）
可以不同。启动之后，宿主必须使用单一的命令/事件契约，普通编码 agent 行为不再按运行时分支。

兼容目标是 Pi 记载于
`packages/coding-agent/docs/rpc.md` 的 JSONL RPC 协议，因为 Pi 已发布类型化的 TypeScript 客户端。Baldric
必须在共享面上匹配命令名、请求字段、响应信封、响应数据形状、事件名
与生命周期语义。持久化 session 文件不需要互相可读；可互换性在进程边界。

## 完成定义

1. 同一套黑盒契约套件能启动 Pi 或 Baldric，并演练 prompting、流式、
   取消、模型选择、thinking 控制、直接 shell 命令、compaction、session
   检视与命令发现。
2. 共享命令有相同的必填请求字段与成功响应形状。
3. 共享事件使用相同的驼峰 wire 词汇与生命周期含义。
4. 不支持的可选行为返回确定性的失败响应；绝不静默改变语义。
5. 运行时专属能力隔离在可选特性中，不进入普通聊天/工具
   操作。
6. Electron 消费生成/共享的协议类型或自己的归一化领域模型，绝不消费
   provider 特定分块或任一运行时的持久化 JSONL。

## 差距清单

### wire 形状

Baldric 第一版 RPC 在 Pi 返回完整模型对象的地方用了模型引用、省略了
state 字段、返回扁平树、暴露 Baldric 的 session 统计名，并且 compaction 返回显示字符串。即使底层行为存在，这些也是 wire 兼容问题。

### 缺失的命令

Pi 还支持模型/thinking 轮换、队列投递模式、自动 compaction/重试
控制、直接 bash 取消、HTML 导出、克隆、fork-message 发现、entry 游标、
last-assistant 查询与 session 命名。

### 输入与 extension UI

Pi 接受图片块并实现了 extension 对话框请求/响应子协议。Baldric 的
provider 中立消息支持图片，但 `CodingSession.prompt()` 目前接受文本，
Baldric 的 extension 桥是回调式。两者都需要专门的 session 接缝才能协议兼容。

### session 身份

Pi 暴露 session 文件路径；Baldric 主要暴露索引 ID。Baldric 在 RPC 边界应接受 ID
或已索引的 Baldric session 路径，同时保持 `SessionManager` 权威。两个运行时的持久化文件刻意不同。

## 交付阶段

### Phase A — frontend 关键对齐（本次变更）

- 把 state 与 model 响应归一化为 Pi 字段名。
- 增加模型/thinking 轮换。
- 增加直接 bash、HTML 导出、entry 游标、树投影、fork-message 发现、
  last-assistant 查询与 session 命名。
- 经公开 `CodingSession` 方法增加自动 compaction 控制。
- 在接受 Pi 的 `sessionPath` 字段的同时，session 恢复保持在 `SessionManager` 之后。
- 增加 fixture 式响应测试并更新已发布的兼容矩阵。

本阶段让一个 Electron 适配器覆盖文本聊天、流式工具、取消、模型与
thinking 选择、直接命令、transcript 恢复与 session 浏览。

### Phase B — 执行控制

- 增加由 `CodingSession` 拥有的可取消 direct-bash 任务；发出 Pi 兼容的
  `bash_execution_update` 记录并实现 `abort_bash`。
- 增加运行时自动重试的启用/禁用与重试延迟取消接缝。
- 把队列投递模式（`all` 与 `one-at-a-time`）加进可移植 harness，而不是在 RPC frontend 里伪装。
- 从 session API 返回结构化 compaction 数据（摘要、被替换边界、token 估算、用量），同时保留当前 TUI 消息。

### Phase C — 多模态与 extension UI

- 用 provider 中立的图片内容扩展 session prompt/queue API。
- 为 select、confirm、input、editor、notifications、status、
  widgets、titles、editor text 实现 RPC extension UI 桥。
- 关联对话框响应并处理取消/超时，不阻塞 stdin 派发。

### Phase D — 一致性与客户端验证

- 从 Pi 的公开文档（不是 Pi 运行时代码）引用协议 fixture。
- 在可选集成 job 中对两个已安装二进制运行相同的子进程场景。
- 用 Pi 的 RPC 客户端对 Baldric 建一个小的 TypeScript 冒烟 fixture；在文档中固定已测试的 Pi 协议版本。
- 在宣称更高兼容级别之前，把 Pi 未来的协议新增归类为 supported、有意不同或 pending。

## Electron 集成指引

两个运行时都用子进程 RPC，即使 Pi 也能在 Node 里直接导入。把
进程启动放在 Electron 主进程，向 renderer 暴露窄的 IPC API。运行时专属的启动配置与共享 session 状态分开存放。renderer
应以 `agent_settled` 而非 `agent_end` 判断运行状态。

生产宿主仍应为可选的 Phase B/C 行为维护能力表。
只选 `agent_runtime` 对 Phase A 公共面已足够；所选运行时未宣告/不支持的可选控件应隐藏或禁用。
