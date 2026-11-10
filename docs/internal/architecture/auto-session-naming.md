# 自动 session 命名

Baldric 依据第一条用户消息自动给新的受管 session 起一个短标题。

## 加了什么

- 新的受管 session 在第一条用户消息持久化之后自动命名。
- Baldric 请当前选定的 provider/model 起一个至多四个词的简洁标题。
- 标题在存入 session 元数据前经过净化。
- provider 调用失败或返回不可用文本时，Baldric 回退到从第一条消息派生的本地标题。
- `/name` 仍是手动覆盖，Baldric 不替换既有的 session 标题。

## 为什么存在

session id 对精确引用有用，但在 `/resume`、`baldric sessions` 与 id 补全里难以扫读。自动名字让已存 session 更容易辨认，用户不必停下来逐个手动命名。

## 与 Pi 的差异

这是 Baldric 相对 Pi 极简基线的少数有意产品分歧之一。Pi 式的 session 持久化聚焦持久 transcript 与显式用户动作。Baldric 增加自动 session 元数据以改进恢复/发现流程。

分歧保留在 `baldric_coding`，因为它是应用元数据行为，不是可复用 agent-harness 行为。`baldric_agent` 仍只拥有可移植的 agent loop、消息、工具与事件。

## 模型选择

Baldric 用 session 当前选定的 provider/model 发起命名请求。目前没有独立的标题模型设置。这让实现简单并跟随活动 session 配置，但意味着第一轮可能在主 assistant 回复之前有一次简短的额外模型调用。

## 持久化行为

命名只在第一条用户消息持久化之后发生。这保住了新准备 session 的延迟索引：在第一条持久消息之前被取消的 session，不应只因命名已开始就出现在 resume 索引里。

## 怎么测试

```bash
uv run pytest tests/test_coding_session.py -q
uv run ruff check src/baldric_coding/session.py tests/test_coding_session.py docs/user/how-to/sessions.md
```
