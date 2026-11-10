---
title: "Phase 9：skill 与 prompt template"
---

Phase 9 加了 Baldric 第一个 markdown 资源系统。

实现位于：

```text
src/baldric_coding/resources.py
src/baldric_coding/skills.py
src/baldric_coding/prompt_templates.py
```

## 加了什么

Baldric 现在能从 Baldric 资源根加载并使用 markdown 资源：

```text
~/.baldric/
  skills/
  prompts/
```

本阶段包含：

- 资源路径 helper
- 最小 markdown frontmatter 解析
- skill 加载
- `/skill:name` prompt 展开
- skill 索引生成
- prompt template 加载
- `{{ variable }}` 模板渲染
- `CodingSession` 的轻量 skill 展开集成

## 资源路径

`BaldricResourcePaths` 描述 Baldric 资源在哪里：

```python
from baldric_coding import BaldricResourcePaths

paths = BaldricResourcePaths()  # ~/.baldric
paths.skills_dir            # ~/.baldric/skills
paths.prompts_dir           # ~/.baldric/prompts
```

测试与调用者可以提供自定义根：

```python
paths = BaldricResourcePaths(root=Path("/tmp/resources"))
```

## frontmatter

skill 与 prompt template 可以带简单 frontmatter：

```md
---
description: Write and run Python tests.
---

# Python Testing

Use pytest.
```

解析器有意只支持简单 `key: value` 对。不执行代码、也不实现完整 YAML 解析器。

## skill

Baldric 支持两种 skill 布局：

```text
~/.baldric/skills/python-testing/SKILL.md
~/.baldric/skills/git-review.md
```

用以下方式加载 skill：

```python
from baldric_coding import BaldricResourcePaths, load_skills

skills = load_skills(BaldricResourcePaths())
```

重复 skill 名抛 `ResourceError`。

## skill 展开

skill 命令使用路线图语法：

```text
/skill:python-testing add tests for parser.py
```

展开产出类似这样的 prompt 文本：

```md
<skill name="python-testing" location="/path/to/python-testing/SKILL.md">
References are relative to /path/to/python-testing.

...skill markdown...
</skill>

add tests for parser.py
```

`CodingSession.prompt()` 在把 prompt 发给 `AgentHarness` 之前展开 skill 命令。`/skill:name` 不被 `handle_command()` 消费，因为它是 prompt 展开指令，不是结束运行的命令。

## skill 索引

`build_skill_index()` 为未来 system prompt 组装创建一份可用的 skill 简表：

```md
Available skills:
- python-testing: Write and run Python tests.
- git-review: Review git changes safely.
```

Phase 10 构建完整 system prompt 时可以使用它。

## prompt template

prompt template 位于：

```text
~/.baldric/prompts/review.md
.agents/prompts/review.md
```

Baldric 把已加载 prompt template 当作 slash 命令的 prompt 展开。名为 `.agents/prompts/example.md` 的文件可用以下方式调用：

```text
/example src/app.py
```

Baldric 在把 prompt 发给模型前展开命令。命令后的调用文本支持 Pi 兼容参数变量：

- `$1`、`$2`…… 位置参数
- `$@` 或 `$ARGUMENTS` 全部参数
- `${N:-default}` 位置默认
- `${@:N}` 与 `${@:N:L}` 简单切片

```md
Review $@ for correctness.
```

prompt template 没有参数占位符时，Baldric 在空行后追加调用
参数。legacy `{{ arguments }}` 与 `{{ args }}`
占位符继续支持。其他占位符在 slash 命令展开期间留空，自定义 prompt 因此可以带可选字段而不崩 TUI。

直接模板渲染还支持简单 `{{ variable }}` 占位符：

```md
Review {{ target }} for {{ focus }}.
```

直接渲染模板：

```python
from baldric_coding import load_prompt_templates, render_prompt_template

templates = load_prompt_templates(paths)
text = render_prompt_template(
    templates[0],
    {"target": "auth.py", "focus": "security"},
)
```

缺失变量抛 `ResourceError`；多余变量忽略。严格行为适用于直接渲染。slash 命令展开更宽容，缺失的自定义变量渲染为空文本。

## 边界

本阶段不实现完整 system prompt 组装。只加资源原语与
`CodingSession` 里的最小 skill 展开钩子。

完整 prompt 组装仍是后续阶段，将组合：

- Baldric 基础身份
- 工具与工具指引
- 项目指令
- skill 索引
- prompt template
- 日后的 extension 片段
- 环境 context

## 测试

本阶段覆盖于：

```text
tests/test_resources.py
tests/test_skills.py
tests/test_prompt_templates.py
tests/test_coding_session.py
```

测试验证：

- 资源路径
- frontmatter 解析
- skill 加载与重复检测
- skill 展开
- skill 索引输出
- prompt template 加载
- 模板渲染
- coding-session 的 skill 展开

## 下一阶段

路线图下一阶段是 system prompt 组装。这里加的资源模型与加载器为那个阶段提供所需的 skill 与 template 输入。
