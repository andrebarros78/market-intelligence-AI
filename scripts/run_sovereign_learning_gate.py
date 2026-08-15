from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LIMIT = 20000


def _workspace_env() -> dict[str, str]:
    env = os.environ.copy()
    local_src = str(ROOT / "src")
    inherited = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = local_src + (os.pathsep + inherited if inherited else "")
    return env


def run(label: str, command: list[str], *, timeout: int = 600) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=_workspace_env(),
        )
        return {
            "label": label,
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-OUTPUT_LIMIT:],
            "stderr": completed.stderr[-OUTPUT_LIMIT:],
            "passed": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "label": label,
            "command": command,
            "returncode": 124,
            "stdout": (exc.stdout or "")[-OUTPUT_LIMIT:] if isinstance(exc.stdout, str) else "",
            "stderr": ((exc.stderr or "")[-OUTPUT_LIMIT:] if isinstance(exc.stderr, str) else "")
            + f"\nTIMEOUT after {timeout}s",
            "passed": False,
        }


def require_safe_environment() -> str:
    if os.getenv("MI_READ_ONLY", "true").strip().lower() != "true":
        raise SystemExit("MI_READ_ONLY must be true")
    if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").strip().lower() != "false":
        raise SystemExit("MI_ALLOW_MARKETPLACE_WRITES must be false")
    if os.getenv("MARKETPLACE_WRITES", "0").strip() not in {"", "0"}:
        raise SystemExit("MARKETPLACE_WRITES must be 0")

    database_url = (os.getenv("TEST_DATABASE_URL") or "").strip()
    if not database_url:
        raise SystemExit("TEST_DATABASE_URL must point to a test PostgreSQL database")

    parsed = urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise SystemExit("TEST_DATABASE_URL must be PostgreSQL")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Sovereign learning gate accepts only a local test PostgreSQL host")
    if "test" not in parsed.path.lower():
        raise SystemExit("TEST_DATABASE_URL database name must contain 'test'")

    configured_runtime_db = (os.getenv("MI_DATABASE_URL") or "").strip()
    if configured_runtime_db and configured_runtime_db != database_url:
        raise SystemExit("MI_DATABASE_URL differs from TEST_DATABASE_URL; refusing unsafe database target")
    os.environ["MI_DATABASE_URL"] = database_url
    os.environ["MI_READ_ONLY"] = "true"
    os.environ["MI_ALLOW_MARKETPLACE_WRITES"] = "false"
    os.environ["MARKETPLACE_WRITES"] = "0"

    # A proof gate must never inherit temporary write authorization or a write token.
    os.environ.pop("MI_CONTROLLED_WRITE_TEST_APPROVED", None)
    os.environ.pop("MI_ML_TEMP_WRITE_TOKEN", None)
    return database_url


def parse_pytest_summary(check: dict[str, object]) -> dict[str, int]:
    text = f"{check.get('stdout', '')}\n{check.get('stderr', '')}"
    result: dict[str, int] = {}
    for key in ("passed", "failed", "skipped", "xfailed", "xpassed", "errors"):
        match = re.search(rf"(\d+)\s+{key}\b", text)
        if match:
            result[key] = int(match.group(1))
    return result


def main() -> int:
    database_url = require_safe_environment()
    python = sys.executable

    checks: list[dict[str, object]] = []
    checks.append(run("compile", [python, "-m", "compileall", "-q", "src", "tests", "migrations", "scripts"]))
    checks.append(
        run(
            "workspace_source",
            [
                python,
                "-c",
                (
                    "import market_intelligence, pathlib; "
                    "actual=pathlib.Path(market_intelligence.__file__).resolve(); "
                    "expected=pathlib.Path('src/market_intelligence/__init__.py').resolve(); "
                    "assert actual == expected, (actual, expected); "
                    "print('WORKSPACE_SOURCE='+str(actual))"
                ),
            ],
        )
    )
    checks.append(
        run(
            "postgresql",
            [
                python,
                "-c",
                (
                    "import os, psycopg; "
                    "u=os.environ['TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1); "
                    "c=psycopg.connect(u); cur=c.cursor(); cur.execute('select current_database(), current_user'); "
                    "row=cur.fetchone(); assert 'test' in row[0].lower(); print('POSTGRESQL_TEST_DB='+row[0]); c.close()"
                ),
            ],
        )
    )
    checks.append(run("alembic_upgrade", [python, "-m", "alembic", "upgrade", "head"]))
    checks.append(run("alembic_check", [python, "-m", "alembic", "check"]))
    checks.append(run("alembic_downgrade", [python, "-m", "alembic", "downgrade", "-1"]))
    checks.append(run("alembic_reupgrade", [python, "-m", "alembic", "upgrade", "head"]))

    checks.append(run("pytest_full", [python, "-m", "pytest", "-q"], timeout=900))
    checks.append(
        run(
            "sovereign_policy_guards",
            [
                python,
                "-m",
                "pytest",
                "-q",
                "tests/unit/test_sovereign_learning.py",
                "tests/unit/test_sovereign_learning_metadata.py",
            ],
        )
    )
    checks.append(
        run(
            "sovereign_stress_11000",
            [python, "-m", "pytest", "-q", "tests/unit/test_sovereign_learning_stress.py"],
        )
    )
    checks.append(
        run(
            "sovereign_persistence",
            [python, "-m", "pytest", "-q", "tests/integration/test_sovereign_learning_persistence.py"],
        )
    )
    checks.append(
        run(
            "temporal_and_replay",
            [python, "-m", "pytest", "-q", "tests/integration/test_temporal_workflow.py"],
            timeout=600,
        )
    )
    checks.append(run("radar", [python, "-m", "pytest", "-q", "tests/unit/test_radar.py"]))
    checks.append(run("radar_digital_twin", [python, "scripts/run_radar_digital_twin.py"], timeout=600))
    checks.append(
        run(
            "learning_persistence_tables",
            [
                python,
                "-c",
                (
                    "import os, psycopg; "
                    "u=os.environ['TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1); "
                    "c=psycopg.connect(u); cur=c.cursor(); "
                    "tables=['learning_episodes','learning_promotions','learning_checkpoints']; "
                    "counts={}; "
                    "[(cur.execute('select count(*) from '+t), counts.__setitem__(t, cur.fetchone()[0])) for t in tables]; "
                    "cur.execute('select coalesce(sum(marketplace_writes),0) from learning_checkpoints'); writes=cur.fetchone()[0]; "
                    "assert all(counts[t] > 0 for t in tables), counts; assert writes == 0, writes; "
                    "print('LEARNING_COUNTS='+str(counts)); print('MARKETPLACE_WRITES='+str(writes)); c.close()"
                ),
            ],
        )
    )

    by_label = {str(item["label"]): item for item in checks}
    def ok(label: str) -> bool:
        return bool(by_label.get(label, {}).get("passed"))

    pytest_summary = parse_pytest_summary(by_label["pytest_full"])
    failed_checks = [str(item["label"]) for item in checks if not bool(item["passed"])]

    criteria = {
        "COMPILE": ok("compile"),
        "ALEMBIC_UPGRADE": ok("alembic_upgrade") and ok("alembic_reupgrade"),
        "ALEMBIC_CHECK": ok("alembic_check"),
        "ALEMBIC_ROLLBACK": ok("alembic_downgrade") and ok("alembic_reupgrade"),
        "POSTGRESQL": ok("postgresql") and ok("learning_persistence_tables"),
        "PYTEST": ok("pytest_full"),
        "TEMPORAL": ok("temporal_and_replay"),
        "TEMPORAL_REPLAY": ok("temporal_and_replay"),
        "RADAR": ok("radar"),
        "RADAR_DIGITAL_TWIN": ok("radar_digital_twin"),
        "MCL_P_PLUS": ok("sovereign_policy_guards") and ok("sovereign_stress_11000") and ok("sovereign_persistence"),
        "CHECKPOINT_RESUME": ok("sovereign_persistence"),
        "IDEMPOTENCY": ok("sovereign_persistence") and ok("temporal_and_replay"),
        "WATCHDOGS": ok("sovereign_policy_guards") and ok("temporal_and_replay"),
        "SECRET_CONTAMINATION_BLOCK": ok("sovereign_policy_guards"),
        "CAUSAL_OVERCLAIM_BLOCK": ok("sovereign_policy_guards"),
        "PROMOTION_GATE": ok("sovereign_policy_guards"),
        "STRESS_11000_10000": ok("sovereign_stress_11000"),
        "MARKETPLACE_WRITES_ZERO": ok("learning_persistence_tables"),
    }

    passed = all(criteria.values()) and not failed_checks
    report = {
        "gate": "RADAR_UNIVERSAL_SOBERANO_MCL",
        "database_configured": True,
        "database_target": {
            "host": urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://", 1)).hostname,
            "database": urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://", 1)).path.lstrip("/"),
            "test_only": True,
        },
        "marketplace_read_only": True,
        "marketplace_writes_allowed": False,
        "marketplace_writes": 0 if criteria["MARKETPLACE_WRITES_ZERO"] else None,
        "stress": "11000/10000_PASS" if criteria["STRESS_11000_10000"] else "FAIL",
        "critical_failures": len(failed_checks),
        "pytest_summary": pytest_summary,
        "criteria": criteria,
        "checks": checks,
        "failed_checks": failed_checks,
        "passed": passed,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if passed:
        print("SOVEREIGN_LEARNING_GATE=PASS")
        print("MARKETPLACE_WRITES=0")
        print("CRITICAL_FAILURES=0")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
