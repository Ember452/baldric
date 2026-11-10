---
title: "extension 安装器"
---

# extension 安装器

Baldric 现在有 `baldric install <source>` 命令，让 extension 在后续运行中可用。它有意实现 Pi 包安装器的有用第一片，而不引入设置/包管理系统。

## 加了什么

命令接受：

```text
baldric install ./extension.py
baldric install ./extension-directory
baldric install git:github.com/owner/repository
baldric install git:github.com/owner/repository@ref
baldric install https://github.com/owner/repository.git
```

本地来源被复制、Git 来源被克隆进
`~/.baldric/extensions/`。目标已存在时保留，除非调用者传 `--force`。

## 为什么是这个形状

此前用户必须知道 Baldric 的资源目录并手工复制/克隆进去，或每次运行重复 `baldric -e PATH`。Pi 用 `pi install` 解决该问题。Baldric 现在镜像该命令的面向来源 UX 与
Pi 风格 `git:` 拼写，同时复用 Baldric 既有的 extension 发现。

第一版刻意比 Pi 的包管理器窄：

- 只装 extension，不装 skill、prompt 或主题；
- 支持本地路径与 Git，不支持 npm/PyPI 包；
- 不安装 Python 依赖；
- 没有包 registry、remove 或 update 命令。

这把包策略留在 `baldric_coding`，不改可移植的
`baldric_agent` harness。

## 安装流程

```text
source argument
      ↓
resolve local path or normalize Git source/ref
      ↓
copy or clone into a temporary root/extensions/<name> layout
      ↓
validate that normal user-directory discovery can see it
      ↓
atomically rename into ~/.baldric/extensions
      ↓
load through the existing runtime on the next Baldric startup
```

校验不导入也不执行 extension 代码。单个本地文件必须以 `.py` 结尾。目录必须含 `extension.py` 或在
`[tool.baldric].extensions` 声明入口；散装的 Python 文件目录被拒——因为
`-e` 能发现它而用户目录发现不能。

staging 发生在目标目录内，发布因此是同文件系统 rename。临时树复现确切的
`root/extensions/<name>` 发现布局，防止"仅嵌套可用"的包通过显式路径校验却在安装后消失。失败的复制、克隆、checkout、校验与文件系统操作会清理其
staging 产物并以 `ExtensionInstallError` 呈现。强制替换把先前目标保留为临时备份，发布失败时还原。

## 安全边界

安装不是沙箱。命令打印警告，但审查来源是用户的责任。已安装模块在 Baldric 进程内执行，拥有用户的文件系统、网络、凭据与进程访问。

## 主要文件

| 文件 | 职责 |
| --- | --- |
| `src/baldric_coding/extension_installer.py` | 来源解析、staging、校验与发布 |
| `src/baldric_coding/cli.py` | `baldric install` 命令分发与面向用户的输出 |
| `src/baldric_coding/paths.py` | 规范的用户 extension 目录 |
| `tests/test_extension_installer.py` | 本地/Git 安装、校验、替换、清理 |
| `tests/test_cli.py` | CLI 分发与错误 |

## 验证

运行：

```bash
uv run pytest tests/test_extension_installer.py tests/test_cli.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```
