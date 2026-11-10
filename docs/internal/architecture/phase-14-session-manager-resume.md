---
title: "Phase 14：session 管理器与恢复"
---

Phase 14 让 Baldric session 成为存放在 Baldric home 之下的第一等记录。

实现位于：

```text
src/baldric_coding/session_manager.py
```

## 加了什么

Baldric 现在有一个 `SessionManager`，可以：

- 创建新 session
- 把 session 索引进用户 home 元数据
- 按最新优先列出 session
- 按 id 查找 session
- 新消息持久化后 touch session
- 为既有 TUI 行为返回默认项目 session

session 元数据由：

```python
CodingSessionRecord
```

表示，含：

- `id`
- `path`
- `cwd`
- `model`
- `title`
- `created_at`
- `updated_at`

## 存储布局

session transcript 保持 append-only JSONL 文件。

session 元数据最初存于全局兼容索引：

```text
~/.baldric/sessions/index.jsonl
```

当前 session 元数据与 transcript 文件位于项目专属目录：

```text
~/.baldric/sessions/<cleaned-path-suffix>-<short-hash>/
```

默认项目 session 仍是：

```text
~/.baldric/sessions/<cleaned-path-suffix>-<short-hash>/default.jsonl
```

但现在以稳定 id 索引：

```text
default-<cleaned-path-suffix>-<short-hash>
```

新 session 存为：

```text
~/.baldric/sessions/<cleaned-path-suffix>-<short-hash>/<session-id>.jsonl
```

## CodingSession 集成

`CodingSessionConfig` 现在接受：

```python
session_id: str | None
session_manager: SessionManager | None
```

session 持久化新消息时会 touch session 管理器记录，`updated_at` 保持最新。

这让 session transcript 与 session 索引松耦合：`baldric_agent` 仍只知道 append-only session 存储，而 `baldric_coding` 拥有面向用户的 session 元数据。

## TUI 集成

TUI 现在经 `SessionManager` 创建 session。

默认行为：

```bash
baldric
```

创建新 session。

为明确起见也接受显式新 session 旗标：

```bash
baldric --new-session
```

恢复一个已索引 session：

```bash
baldric --resume <session-id>
```

session id 未知时，Baldric 以清晰错误退出。

后续 TUI 打磨经以下方式增加了进程内 session 切换：

```text
/resume <session-id>
```

纯 `/resume` 打开项目范围的 session picker。`/resume <session-id>`
重载所选已索引 session 并重建可见 transcript，不重启 Baldric。

## CLI session 列表

Baldric 可以列出已索引 session：

```bash
baldric sessions
```

第一版实现打印制表符分隔的行：

```text
<id>    <title>    <model>    <cwd>
```

更丰富的弹窗 session picker 现在使用与 `/resume` 相同的项目范围 session 记录。

## resume 时的中断 tool call 修复

Baldric 通过添加合成工具结果修复被取消的 tool call：

```text
Tool call interrupted by user
```

这让 OpenAI 兼容 transcript 保持有效——那些 provider 拒绝任何 assistant tool call 没有匹配工具输出的历史。旧版本存在一个微妙的
resume bug：修复可以加进内存 `AgentHarness` 让活动 session 继续，但不写回
append-only JSONL 文件。`/resume` 后 Baldric 从磁盘重建分支时没有那条合成工具结果，下一次 provider 请求报错如：

```text
No tool output found for function call call_...
```

`CodingSession.load()` 现在在返回被恢复 session 之前检查活动分支上未匹配的 assistant tool
call。发现时追加持久修复 entry 并把叶推进到修复后的分支。这也覆盖用户消息已经追加在悬空 tool call 之后的
历史损坏 session。

## 测试

本阶段覆盖于：

```text
tests/test_session_manager.py
tests/test_coding_session.py
tests/test_cli.py
```

测试验证：

- session 创建与索引
- 默认 session 记录
- 最新优先列表
- prompt 持久化后的元数据更新
- TUI resume/new-session 的 CLI 接线
- session 列表 CLI 输出

## 下一阶段

下一阶段应把硬编码的 slash 命令处理替换为命令注册表。注册表随后可以驱动 TUI 补全与 `/sessions`、`/resume`、`/new` 等 session 命令。
