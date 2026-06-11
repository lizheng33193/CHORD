"""Orchestrator Agent System Prompt v1 loader + country skill assembly."""

from __future__ import annotations

from app.core.config import settings


def get_system_prompt_v1() -> str:
    """Read the canonical System Prompt v1 from disk."""
    path = (
        settings.project_root
        / "app" / "prompts" / "orchestrator_system_prompt_v1.md"
    )
    if not path.exists():
        raise FileNotFoundError(
            f"System Prompt v1 missing: {path}. "
            "Plan #03 Phase 1 Task 1.7 落地的文件被误删，请从 git 历史恢复。"
        )
    return path.read_text(encoding="utf-8")


def assemble_system_prompt(country: str | None = None) -> str:
    """Assemble base prompt + country skill (lazy injection)."""
    base = get_system_prompt_v1()
    if country is None:
        return base
    from app.services.orchestrator_agent.skills_loader import load_skill
    skill_md = load_skill(country)
    return f"{base}\n\n## 国别规则（自动注入：{country}）\n\n{skill_md}"
