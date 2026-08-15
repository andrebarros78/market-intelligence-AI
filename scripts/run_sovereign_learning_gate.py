from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return {
        "label": label,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "passed": completed.returncode == 0,
    }


def main() -> int:
    if os.getenv("MI_READ_ONLY", "true").strip().lower() != "true":
        raise SystemExit("MI_READ_ONLY must be true")
    if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").strip().lower() != "false":
        raise SystemExit("MI_ALLOW_MARKETPLACE_WRITES must be false")

    python = sys.executable
    checks = [
        run("compile", [python, "-m", "compileall", "-q", "src", "tests", "migrations", "scripts"]),
        run(
            "sovereign_unit_and_stress",
            [python, "-m", "pytest", "-q", "tests/unit/test_sovereign_learning.py", "tests/unit/test_sovereign_learning_stress.py"],
        ),
    ]

    database_configured = bool(os.getenv("TEST_DATABASE_URL"))
    if database_configured:
        checks.extend(
            [
                run("alembic_upgrade", [python, "-m", "alembic", "upgrade", "head"]),
                run("alembic_check", [python, "-m", "alembic", "check"]),
                run(
                    "postgres_learning",
                    [python, "-m", "pytest", "-q", "tests/integration/test_sovereign_learning_persistence.py"],
                ),
                run(
                    "temporal_radar_learning",
                    [python, "-m", "pytest", "-q", "tests/integration/test_temporal_workflow.py"],
                ),
                run("radar_digital_twin", [python, "scripts/run_radar_digital_twin.py"]),
            ]
        )

    report = {
        "gate": "RADAR_UNIVERSAL_SOBERANO_MCL",
        "database_configured": database_configured,
        "marketplace_read_only": True,
        "marketplace_writes_allowed": False,
        "checks": checks,
        "passed": all(bool(item["passed"]) for item in checks) and database_configured,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
