---
title: "Phase 20：安装与配置文档"
---

本阶段启动 Baldric 的打包与安装打磨。

项目已经通过下列方式暴露面向用户的控制台命令：

```toml
[project.scripts]
baldric = "baldric_coding.cli:app"
```

这一片文档化如何像普通工具一样安装与操作该命令。

## 加了什么

新的面向用户文档：

```text
docs/installation.md
docs/configuration.md
```

更新的文档：

```text
README.md
docs/getting-started.md
docs/index.md
docs/providers.md
mkdocs.yml
```

## 覆盖的流程

文档现在覆盖：

- 用 `uv tool install` 安装 Baldric
- 用 `pipx` 安装 Baldric
- 验证安装好的 `baldric` 命令
- 首次运行的 provider setup
- 用 `baldric` 打开 TUI
- 在 print mode 跑一条 prompt
- `~/.baldric/providers.json` 下的 provider 配置
- `~/.baldric/sessions` 下的 session 存储
- skill 与 prompt template 位置
- 项目 context 文件发现
- 当前禁用的 shell 补全

## 边界

本阶段不改 `baldric_agent` 或 provider/runtime 行为。它把当前面向用户的应用安装与配置路径显式化。

## 测试

文档片经以下验证：

```text
uv run baldric --version
uv build
uv run --group docs mkdocs build --strict
```
