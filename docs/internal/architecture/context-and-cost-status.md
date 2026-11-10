# context 与成本：现状

**状态：** 验证笔记 —— 2026-11-06（分支 `reliability/p3-and-followups`）

路线图的 "context and cost" 阶段按四项调研。读代码发现四项均已实现——主要因为 harness 从一开始就按 Pi 对齐构建。本笔记记录每项的位置，避免重做，并为未来变更留参照。

| 项 | 位置 | 作用 |
| --- | --- | --- |
| 单一 context 投影 | `src/baldric_agent/context_projection.py`（`provider_context`） | 循环回放 `provider_context(messages)`——对持久历史的纯推导：丢弃空的失败/中止轮，把被拒图片结果改写为文本错误。历史从不被改动。 |
| compaction 切点 | `src/baldric_coding/session/runtime.py`（`_recent_preserving_compaction_plan`、`_auto_compaction_plan`）、`compaction/context_window.py` | 切点按 token 预算（`DEFAULT_COMPACTION_KEEP_RECENT_TOKENS`），保留近期尾部并把被替换前缀总结为一条 `CompactionEntry`；溢出与阈值触发共用该计划。 |
| 增量 context 状态 | `src/baldric_coding/session/session.py`（`_context_usage_cache`、`_invalidate_context_usage_cache`） | `context_usage` 只算一次，仅在消息/工具/compaction/模型变更落地时失效，而不是每次渲染重算。provider 上报用量存在时胜过估算。 |
| 缓存亲和 | `src/baldric_ai/openai_cache.py`、`openai_compatible.py`（`prompt_cache_key`、`_apply_session_affinity_headers`）、`anthropic.py`（`cache_control` 断点）、`openai_codex.py`（`session-id`） | OpenAI 兼容发送 prompt cache key 与该 provider 的 session-affinity header；Anthropic 在 system/messages/tools 上标 `cache_control`；Codex 发送 `session-id`。 |

## 真正剩余的差距

- Google 与 Mistral 不暴露缓存亲和机制，适配器因此已不发任何东西；无可添加。
- 估算值是启发式；它是参考性的（UI 在 provider 上报用量前显示 `?`）。改进启发式不是正确性所需。

本阶段不需要改代码；四项俱在，并由既有 session/compaction/usage 套件测试。
