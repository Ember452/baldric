---
title: "ADR 0001 — 交互式 TUI 使用 Textual"
---

## 状态

已接受，用于后续阶段。

## 背景

Baldric 需要一个交互式终端 UI，但可复用的 agent harness 必须保持对 frontend 框架独立。

## 决策

在内核循环、工具、session 与 print-mode CLI 稳定之后，完整交互式 TUI 使用 Textual。
Textual 藏在一个消费 agent 事件的适配器边界之后。

```text
AgentHarness emits events
        ↓
UI adapter consumes events
        ↓
Textual app renders chat, tool, and status components
```

## 后果

- `baldric_agent` 不得依赖 Textual。
- 早期阶段先用简单的 print mode 与 Rich 渲染器。
- Textual 组件可以独立演化，不改内核 agent loop。
