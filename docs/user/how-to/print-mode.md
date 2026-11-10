---
title: Print mode 与脚本
description: 非交互运行 Baldric 处理单条 prompt——适合脚本、管道与 CI。
---

print mode 运行单条 prompt，不启动交互式 UI，把结果写到终端。它是脚本、管道与一次性提问的正确选择。

## 基本用法

```bash
baldric -p "summarize the changes in the last commit"
```

`-p` / `--print` 旗标把 Baldric 切到 print mode；prompt 本身是普通位置参数，与 TUI 的初始 prompt 相同。print mode 仍使用完整的 coding-session 环境——与 TUI 相同的工具、项目 context 与 session 存储——所以它的轮次也保存在
`~/.baldric/sessions/` 下。

旗标放在 prompt **之前**。Baldric 接受不加引号的多词 prompt，最后一个可识别旗标之后的一切——包括看起来像其他旗标的 token——都当作 prompt 文本：

```bash
baldric -p --mode json "list the public functions in src/app.py"
```

## 输出格式

用 `--mode` 选择结果的写法。单独传 `--mode` 也会切入非交互模式，所以一旦设了 `--mode`，`-p` 就是可选的：

```bash
baldric -p --mode text "list the public functions in src/app.py"        # 默认，人类可读
baldric --mode json "list the public functions in src/app.py"           # JSON，供解析
baldric -p --mode transcript "list the public functions in src/app.py"  # 结构化转录
```

- **text** — 带 ANSI 样式的纯文本，用于阅读。
- **json** — 机器可读，供管道给其他工具。
- **transcript** — 该轮的结构化记录。

管道 stdin 会并入 prompt，可以把文件内容喂进来：

```bash
cat README.md | baldric -p "Summarize this text"
```

管道内容也可以就是整个 prompt——不带位置文本、以管道喂 stdin 的 `baldric -p` 是合法的：

```bash
cat README.md | baldric -p
```

## 选择 provider、model 与目录

同样的选择旗标在 print mode 有效：

```bash
baldric -m gpt-5.5 -p "explain this module"
baldric --provider local -p "explain this module"
baldric --cwd ./services/api -p "audit for secrets"
```

## 恢复对话

传入既有 session id，非交互运行一条 follow-up：

```bash
baldric --print --session <session-id> "Follow-up message"
```

Baldric 把该轮追加到既有 transcript，并把它的活动对话历史发给模型。除非显式选择旗标覆盖，它还使用该 session 已保存的工作目录、provider 与 model。这对所有输出模式都有效，并让 stdout 专属于所选格式。未知 id 直接失败、不创建 session。`--session` 不能与 `--new-session`
或 `--session-id` 组合。

用 `baldric sessions` 查找 session id。

## 记录 session id

自动化可以用 `--session-id` 为新建 print-mode session 指定确切 id。这让 stdout 专属于所选输出格式，并免去扫描 `~/.baldric/sessions/`：

```bash
worker_session_id="$(python -c 'import uuid; print(uuid.uuid4().hex)')"
baldric --print --new-session \
  --session-id "$worker_session_id" \
  --cwd /path/to/project \
  "review the current changes"
printf 'Baldric session: %s\n' "$worker_session_id"
```

id 可以包含字母、数字、`.`、`_` 与 `-`，必须以字母或数字开头结尾，最长 128 字节。`default` 与 `index` 是保留字。每个 worker 用唯一 id。Baldric 原子地预留 transcript，在打开或覆盖既有 session 时以错误退出——即使未索引的 transcript 已用该 id，或两个 worker 同时启动。该选项对 text、JSON 与 transcript 模式同样生效，不往 stdout 输出里添加元数据。

## 退出状态

print mode 在运行失败时以非零退出，可用于脚本：

```bash
if baldric --mode text -p "do the tests pass? answer yes or no" | grep -qi yes; then
  echo "looks good"
fi
```

> [!TIP]
> 交互式工作请用 [TUI](/how-to/tui/)——有流式、steering、picker 与 session 分支。
