from pathlib import Path


def test_custom_agent_profiles_have_required_frontmatter() -> None:
    root = Path(__file__).resolve().parents[2]
    agents_dir = root / ".github" / "agents"
    profiles = sorted(agents_dir.glob("*.agent.md"))
    assert len(profiles) == 11

    for profile in profiles:
        text = profile.read_text(encoding="utf-8")
        assert text.startswith("---\n"), profile
        assert "\ndescription:" in text, profile
        assert "\ntarget: github-copilot" in text, profile
        assert "\ntools:" in text, profile
        assert "Leia AGENTS.md" in text, profile


def test_shared_agent_rules_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    rules = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Loop Engineering" in rules
    assert "read-only/fail-closed" in rules
    assert "Um agente não aprova o próprio trabalho" in rules
