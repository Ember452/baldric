---
title: "Phase 28：Pi 兼容 RPC mode"
---

Phase 28 在 `baldric_coding.rpc` 增加无头 frontend。它消费与 print mode 和 Textual 相同的 `CodingSession`
事件，保持 `baldric_coding → baldric_agent → baldric_ai`。

进程在 stdin/stdout 上使用严格 JSONL。串行化的写入器防止响应与事件
字节交错；prompt 工作运行在 AnyIO 任务组里，事件流式输出的同时取消与排队输入保持可用。EOF 取消活动工作、等待自有任务并关闭 session。

## Pi 兼容性

| 区域 | 状态 |
| --- | --- |
| prompt、steer、follow-up、abort | 支持 |
| state/messages | 支持 |
| 模型与 thinking | Pi 形状模型加 set/cycle/list 支持 |
| 手动 compaction | 支持；详细用量仍是近似 |
| 新建/切换 session、统计、树、fork | Pi 形状 wire 响应；接受 Baldric ID 或已索引路径 |
| 命令发现 | 支持，带合成的 Baldric 来源元数据 |
| 直接 bash | 支持 |
| abort_bash | 推迟；需要可取消的公开 session API |
| HTML 导出、session 命名、entry 游标 | 支持 |
| 自动 compaction 开关 | 支持 |
| extension UI RPC | 推迟；Baldric 目前用 frontend 桥回调 |
| 队列/重试控制、克隆、图片 prompt | 推迟 |

协议有意只映射公开的 `CodingSession` 行为。它不读原始 session
JSONL、不依赖 Textual、不复刻 agent loop。

## 验证

`tests/test_rpc.py` 以 `FakeProvider` 驱动真实 `CodingSession`，走内存 JSONL
流。覆盖关联式确认、事件流、畸形记录、CRLF 与 Unicode
行分隔符。CLI 测试单独覆盖 `--mode rpc` 路由。
