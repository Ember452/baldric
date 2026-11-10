# 向前兼容的用户配置

## 变更了什么

Baldric 现在忽略用户级运行设置中不认识的字段：

- `~/.baldric/tui.json` 的顶层设置与嵌套键位动作；
- `~/.baldric/settings.json` 的字段；
- `~/.baldric/providers.json` 的顶层设置与嵌套 provider 偏好字段。

已识别字段仍与之前完全一样严格校验。非法的已知值、
畸形对象、空的已知键字符串、冲突的 shell 前缀别名、
已知 TUI 动作间的重复赋值仍是配置错误。

## 为什么

这些 JSON 文件是用户级状态，可能被多个 Baldric 安装共享。新版 Baldric 可能增加一个设置并写进其中某个文件。此前，启动旧版本可能在打开 TUI 之前就失败，报错如：

```text
Unknown TUI settings field: turn_notification
```

每个解析器现在消费其版本理解的字段、忽略未来的元数据。这遵循 session
索引记录（`extra="ignore"`）、凭据对象字段、未知顶层
provider 设置与孤儿 provider 偏好已经在用的兼容原则。

未知字段不属于解析后的设置模型，因此旧版本稍后改写设置文件时不会把它们发出。此变更保护启动兼容性；它不让旧版本理解或保留新特性。

## 刻意严格的格式

该政策不适用于每个持久化文件：

- `~/.baldric/catalog.toml` 保持带 schema 版本且严格，因为它控制
  provider 端点、认证路由、模型能力与定价；
- 自定义主题 JSON 保持严格，让拼错的颜色与角色名产生有用的诊断而不是微妙损坏的主题；
- session transcript entry 保持严格以保护对话完整性。

凭据对象与 session 索引元数据本就容忍额外字段，无需改解析器。

## 怎么测试

1. 给每个 JSON 设置文件加一个编造字段，如
   `"future_setting": true`。
2. 在 `tui.json` 的 `keybindings` 里加编造动作，在 `providers.json` 的一个 provider 偏好里加编造选项。
3. 启动 Baldric，确认 TUI 打开且已识别设置仍然生效。
4. 给已识别设置非法值，确认 Baldric 仍报告那些配置错误。

自动化测试覆盖三个解析器的忽略字段，连同既有对已识别字段的严格校验测试。
