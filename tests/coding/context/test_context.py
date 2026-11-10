from pathlib import Path

from baldric.coding.config.paths import BaldricPaths
from baldric.coding.context.project import discover_project_context
from baldric.coding.context.resources import BaldricResourcePaths


def test_discovers_user_project_and_agents_context_files(tmp_path: Path) -> None:
    baldric_home = tmp_path / "home" / ".baldric"
    agents_home = tmp_path / "home" / ".agents"
    project = tmp_path / "project"
    nested = project / "pkg"
    nested.mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (baldric_home).mkdir(parents=True)
    (agents_home).mkdir(parents=True)
    (project / ".baldric").mkdir()
    (project / ".agents").mkdir()

    (baldric_home / "AGENTS.md").write_text("User Baldric instructions", encoding="utf-8")
    (agents_home / "AGENTS.md").write_text("User agents instructions", encoding="utf-8")
    (project / "AGENTS.md").write_text("Project instructions", encoding="utf-8")
    (nested / "AGENTS.md").write_text("Nested instructions", encoding="utf-8")
    (nested / ".baldric").mkdir()
    (nested / ".agents").mkdir()
    (nested / ".baldric" / "AGENTS.md").write_text("Project Baldric instructions", encoding="utf-8")
    (nested / ".agents" / "AGENTS.md").write_text("Project agents instructions", encoding="utf-8")

    context_files = discover_project_context(
        BaldricResourcePaths(
            root=baldric_home,
            agents_root=agents_home,
            cwd=nested,
            paths=BaldricPaths(home=baldric_home, agents_home=agents_home),
        )
    )

    assert [Path(context_file.path) for context_file in context_files] == [
        baldric_home / "AGENTS.md",
        agents_home / "AGENTS.md",
        project / "AGENTS.md",
        nested / "AGENTS.md",
        nested / ".baldric" / "AGENTS.md",
        nested / ".agents" / "AGENTS.md",
    ]
    assert [context_file.content for context_file in context_files] == [
        "User Baldric instructions",
        "User agents instructions",
        "Project instructions",
        "Nested instructions",
        "Project Baldric instructions",
        "Project agents instructions",
    ]
