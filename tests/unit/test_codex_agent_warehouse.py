import json
import re
import tomllib
from pathlib import Path


def test_native_codex_agents_are_installed() -> None:
    root = Path(__file__).resolve().parents[2]
    agents_dir = root / ".codex" / "agents"
    profiles = sorted(agents_dir.glob("*.toml"))
    assert len(profiles) == 11

    names: set[str] = set()
    for profile in profiles:
        data = tomllib.loads(profile.read_text(encoding="utf-8"))
        assert data["name"]
        assert data["description"]
        assert "AGENTS.md" in data["developer_instructions"]
        assert data.get("sandbox_mode") in {"read-only", "workspace-write"}
        names.add(data["name"])

    assert len(names) == 11


def test_codex_parallelism_is_bounded() -> None:
    root = Path(__file__).resolve().parents[2]
    data = tomllib.loads((root / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert data["agents"]["max_concurrent_threads_per_session"] == 6


def test_warehouse_is_pinned_inactive_and_complete() -> None:
    root = Path(__file__).resolve().parents[2]
    inventory = json.loads((root / "agents" / "warehouse" / "recruits.json").read_text(encoding="utf-8"))

    assert inventory["policy"]["warehouse_is_inactive"] is True
    assert inventory["policy"]["auto_execution"] is False
    assert inventory["policy"]["primary_runtime"] == "Codex local"
    assert inventory["counts"] == {
        "active_internal_codex_agents": 11,
        "warehouse_external_recruits": 19,
        "total_specialized_resources": 30,
    }

    recruits = inventory["recruits"]
    assert len(recruits) == 19
    assert len({item["id"] for item in recruits}) == 19

    for item in recruits:
        assert re.fullmatch(r"[0-9a-f]{40}", item["source_ref"]), item["id"]
        assert item["source_ref"] not in {"main", "master", "latest"}
        assert item["license"] in {"MIT", "Apache-2.0"}
        assert item["third_party_execution_allowed"] is False
        assert item["status"].startswith("WAREHOUSE_APPROVED_")


def test_local_codex_and_github_are_the_continuity_policy() -> None:
    root = Path(__file__).resolve().parents[2]
    rules = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Codex local" in rules
    assert "GitHub" in rules
    assert "agents/warehouse" in rules
