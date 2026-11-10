---
title: "ADR 0003 — 技能发现统一到 Agent Skills 规范"
---

## 状态

已接受。

## 背景

Baldric 从四个位置发现 Markdown skill，优先级递增：

```text
~/.baldric/skills/
~/.agents/skills/
<cwd>/.baldric/skills/
<cwd>/.agents/skills/
```

历史上 Baldric 在这些目录里**两种**布局都接受：

- 根下的 `foo.md` 文件（skill 名 = `foo`），或
- `foo/SKILL.md` 子目录（skill 名 = `foo`）。

PR [#280](https://github.com/huggingface/tau/pull/280) 把 `.agents/` 位置的发现收紧到 [Agent Skills
spec](https://agentskills.io/specification#directory-structure)，它要求 `subdir/SKILL.md` 形式。它有意让 `.baldric/skills/` 保留宽松的"任意 `.md`"规则。

这让 Baldric 对两个外观完全相同的位置适用两条不同规则：

| 位置 | `foo.md`（裸文件） | `foo/SKILL.md`（目录） |
|---|---|---|
| `.baldric/skills/` | ✅ 加载 | ✅ 加载 |
| `.agents/skills/` | ❌ 忽略 | ✅ 加载 |

## 决策

把 Agent Skills 规范统一应用到 Baldric 扫描的**每一个** skills 位置。skill 一律是 `<skills-dir>/<name>/SKILL.md`。skills 目录根下的裸 `.md` 文件不再作为 skill 加载；Baldric 改为发出一条信息级 `ResourceDiagnostic`，告知用户如何迁移：

```text
mv foo.md foo/SKILL.md
```

#280 引入的 `agents_mode` 分支从 `_load_skills_from_dir_with_diagnostics` 中移除。

## 为什么在这里偏离 Pi

Pi 在 `packages/coding-agent/src/core/package-manager.ts` 里维护显式的 `SkillDiscoveryMode = "pi" | "agents"` 分裂：

- `.pi/skills/` 与 `~/.pi/agent/skills/` 用 "pi mode"（允许裸 `.md`）。
- `.agents/skills/` 用 "agents mode"（只认严格的 `SKILL.md`）。

读 Pi 自己的 changelog 可以看出这个分裂**不是哲学选择**——它是**向后兼容的特例**：

> **Pi skills now use `SKILL.md` convention**: Pi skills must now be named
> `SKILL.md` inside a directory, matching Codex CLI format. Previously any
> `*.md` file was treated as a skill. Migrate by renaming
> `~/.pi/agent/skills/foo.md` to `~/.pi/agent/skills/foo/SKILL.md`.

以及与 #280 对应的修复：

> Fixed skill discovery to stop recursing once a directory contains
> `SKILL.md`, and to ignore root `*.md` files in `.agents/skills` while
> keeping root markdown skill files supported in `~/.pi/agent/skills`,
> `.pi/skills`, and package `skills/` directories (pi-mono#2603)

Pi 的行进方向明确是"`SKILL.md` 处处如此"。Pi 无法干净地完成这次迁移，因为它有大量已安装的裸 `.md` skill 会因此损坏。

Baldric 没有这个约束。我们处于 pre-1.0（`0.1.3`），对 `.baldric/skills/` 布局没有实质的向后兼容契约，可以直接交付终局，不必拖着一个 legacy 路径前进。

## 后果

- 所有 skills 目录一条规则。`agents_mode` 启发式
  （`skills_dir.parent.name == ".agents"`）消失。
- 以裸 `.md` 形式写在 `.baldric/skills/` 下的用户 skill 不再加载，必须迁移。Baldric 在加载时以诊断暴露这一点，失败可见而非静默。
- skill 加载器行为不再依赖父目录名，调用者传入非常规的 `BaldricResourcePaths.agents_root` 值（例如测试或嵌入时的自定义 skills 根）时依然正确。
- 文档（`docs/user/how-to/skills-and-prompts.md`）现在把规范布局作为唯一受支持形式展示。

## 迁移

对任何 Baldric 扫描的 skills 目录下的每个裸 `.md` skill：

```bash
cd ~/.baldric/skills          # or .baldric/skills, .agents/skills, etc.
for f in *.md; do
  name="${f%.md}"
  mkdir -p "$name"
  mv "$f" "$name/SKILL.md"
done
```

加载时诊断会把每个文件应重命名的目标路径准确指给用户。

## 参考

- PR [#280](https://github.com/huggingface/tau/pull/280) — 只针对
  `.agents/` 的较窄修复。
- Issue [#292](https://github.com/huggingface/tau/issues/292) — 本次统一。
- Agent Skills spec: <https://agentskills.io/specification#directory-structure>
- Pi 的 `SkillDiscoveryMode`：pi-mono 仓库的 `packages/coding-agent/src/core/package-manager.ts`
