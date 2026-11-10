---
title: "02 — Agent Loop"
---

agent loop 是那个小而可复用的引擎：把消息、工具与 provider 流变成进展事件。

## 职责

1. 接收当前 system prompt、transcript、tools 与模型选择。
2. 请 provider 流式返回回复。
3. 在文本与 tool 调用到达时发出事件。
4. 收集 assistant 消息。
5. 执行被请求的工具。
6. 追加工具结果。
7. 继续，直到 assistant 不再发出 tool 调用。

## 非职责

循环对 CLI 参数、Textual 组件、session 文件位置、项目资源发现一无所知。
它们属于 `baldric_coding`。

## 事件优先的设计

每个有意义的步骤都应可通过事件观察，print mode、Rich 渲染与 Textual 因此共享同一内核。
