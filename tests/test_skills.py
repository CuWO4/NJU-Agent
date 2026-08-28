"""Unit tests for dynamic skill loading."""

from pathlib import Path

from njuagent.agent.skills import load_skills


def test_load_skills_empty_when_no_dir(tmp_path: Path):
    assert load_skills(str(tmp_path)) == []


def test_load_skills_reads_md_files_sorted(tmp_path: Path):
    skills_dir = tmp_path / ".njuagent" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "b.md").write_text("Skill B instructions", encoding="utf-8")
    (skills_dir / "a.md").write_text("  \nSkill A instructions\n  \n", encoding="utf-8")
    (skills_dir / "note.txt").write_text("ignored", encoding="utf-8")
    (skills_dir / "empty.md").write_text("   \n", encoding="utf-8")

    assert load_skills(str(tmp_path)) == ["Skill A instructions", "Skill B instructions"]
