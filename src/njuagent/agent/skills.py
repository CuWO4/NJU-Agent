"""Dynamic skills: preset prompt-only files under .njuagent/skills/*.md.

Skills contain only prompt text (no tools). Their content is inserted into
the system prompt. The user manages the files; the agent reloads them when a
task starts.
"""

from __future__ import annotations

from pathlib import Path


def load_skills(workdir: str) -> list[str]:
    """Return the trimmed contents of every *.md file in .njuagent/skills/."""
    skills_dir = Path(workdir) / ".njuagent" / "skills"
    if not skills_dir.is_dir():
        return []
    skills: list[str] = []
    for path in sorted(skills_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if content.strip():
            skills.append(content.strip())
    return skills
