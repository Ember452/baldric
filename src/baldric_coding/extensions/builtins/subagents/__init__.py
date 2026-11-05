"""Subagents: spawnable agent types, background runs with completion
notifications, git worktree isolation, per-agent memory, and scheduled jobs.

`extension.setup` is the entry point. It registers the `agent`,
`get_subagent_result` and `steer_subagent` tools, the `/agents` command, the
fleet strip and the conversation viewer, and starts the scheduler for the
session's stored jobs.
"""
