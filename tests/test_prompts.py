"""Unit tests for system prompts."""

from njuagent.agent.prompts import (
    PLAN_MODE_PREFIX,
    SUBAGENT_SYSTEM_PROMPT,
    build_main_prompt,
)


def test_main_prompt_always_contains_plan_rule():
    prompt = build_main_prompt()
    assert PLAN_MODE_PREFIX in prompt
    assert "plan mode" in prompt.lower()


def test_main_prompt_with_skills():
    prompt = build_main_prompt(skills=["SKILL-A", "SKILL-B"])
    assert "SKILL-A" in prompt
    assert "SKILL-B" in prompt


def test_subagent_prompt_mentions_approval_denial():
    assert "approval" in SUBAGENT_SYSTEM_PROMPT.lower()
    assert "denied" in SUBAGENT_SYSTEM_PROMPT.lower()
