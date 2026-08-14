from pathlib import Path


TEXT_SUFFIXES = {".md", ".py", ".toml", ".yml", ".yaml", ".json", ".ini", ".txt", ".ps1", ".sh"}
FORBIDDEN_PATTERNS = (
    "API" + " ML",
    "API" + "-ML",
    "API" + "_ML",
    "api" + " ml",
    "api" + "-ml",
    "api" + "_ml",
)


def test_legacy_product_name_is_absent_from_tracked_text() -> None:
    root = Path(__file__).resolve().parents[2]
    findings: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern in line for pattern in FORBIDDEN_PATTERNS):
                findings.append(f"{path.relative_to(root)}:{line_number}: {line.strip()}")

    assert not findings, "Legacy product name found:\n" + "\n".join(findings)
