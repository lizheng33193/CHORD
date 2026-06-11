"""LLM input assembly helpers for orchestrator decisions."""

from __future__ import annotations


def build_llm_input(system_prompt: str, messages: list) -> str:
    parts = [system_prompt, "\n\n--- 对话历史 ---\n"]
    for message in messages:
        parts.append(f"[{message.role}] {message.content}\n")
    parts.append("\n--- 请输出下一步决策 JSON ---\n")
    return "".join(parts)
