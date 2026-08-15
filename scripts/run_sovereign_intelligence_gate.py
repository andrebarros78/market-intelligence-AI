from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LIMIT = 20000


def _env() -> dict[str, str]:
    env = os.environ.copy()
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["MI_READ_ONLY"] = "true"
    env["MI_ALLOW_MARKETPLACE_WRITES"] = "false"
    env["MARKETPLACE_WRITES"] = "0"
    return env


def run(label: str, command: list[str], *, timeout: int = 900) -> dict[str, object]:
    try:
        completed = subprocess.run(command, cwd=ROOT, env=_env(), text=True, capture_output=True, timeout=timeout)
        return {
            "label": label, "returncode": completed.returncode,
            "stdout": completed.stdout[-OUTPUT_LIMIT:], "stderr": completed.stderr[-OUTPUT_LIMIT:],
            "passed": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "label": label, "returncode": 124,
            "stdout": (exc.stdout or "")[-OUTPUT_LIMIT:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-OUTPUT_LIMIT:] if isinstance(exc.stderr, str) else "",
            "passed": False,
        }


def main() -> int:
    if os.getenv("MI_READ_ONLY", "true").lower() != "true":
        raise SystemExit("MI_READ_ONLY must be true")
    if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").lower() != "false":
        raise SystemExit("MI_ALLOW_MARKETPLACE_WRITES must be false")

    python = sys.executable
    checks = [
        run("core_compile", [python, "-m", "compileall", "-q", "src/market_intelligence/intelligence/sovereign", "src/market_intelligence/persistence/sovereign_intelligence.py", "src/market_intelligence/persistence/sovereign_intelligence_models.py", "scripts/run_sovereign_intelligence_core.py"]),
        run("core_unit", [python, "-m", "pytest", "-q", "tests/unit/test_sovereign_intelligence_core.py", "tests/unit/test_sovereign_intelligence_architecture.py", "tests/unit/test_sovereign_intelligence_unit.py"]),
        run("core_stress_12000", [python, "-m", "pytest", "-q", "tests/unit/test_sovereign_intelligence_stress.py"]),
    ]

    test_db = (os.getenv("TEST_DATABASE_URL") or "").strip()
    if test_db:
        checks.extend([
            run("legacy_sovereign_learning_gate", [python, "scripts/run_sovereign_learning_gate.py"], timeout=1200),
            run("core_runtime_cycle", [python, "-c", "import asyncio, os; from market_intelligence.intelligence.sovereign.runtime import run_cycle; r=asyncio.run(run_cycle(os.environ['TEST_DATABASE_URL'], max_records=8)); assert r['core_health']=='PASS', r; assert r['marketplace_writes']==0, r; print('CORE_RUNTIME='+str(r))"], timeout=600),
            run("core_persistence", [python, "-c", "import os, psycopg; u=os.environ['TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1); c=psycopg.connect(u); cur=c.cursor(); tables=['sovereign_intelligence','exposure_map','cognitive_audits','sovereign_core_checkpoints']; counts={}; [(cur.execute('select count(*) from '+t), counts.__setitem__(t,cur.fetchone()[0])) for t in tables]; cur.execute('select coalesce(sum(marketplace_writes),0) from sovereign_core_checkpoints'); writes=cur.fetchone()[0]; assert writes==0,writes; print('CORE_COUNTS='+str(counts)); print('MARKETPLACE_WRITES='+str(writes)); c.close()"]),
        ])

    failed = [str(item["label"]) for item in checks if not item["passed"]]
    if not test_db:
        failed.append("test_database_required_for_full_gate")
    report = {
        "gate": "SOVEREIGN_INTELLIGENCE_COUNTERINTELLIGENCE_CORE",
        "core_version": "1.0.0",
        "radar_is_subsystem": True,
        "read_only": True,
        "marketplace_writes": 0,
        "test_database_executed": bool(test_db),
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not failed:
        print("SOVEREIGN_INTELLIGENCE_CORE_GATE=PASS")
        print("MARKETPLACE_WRITES=0")
        print("CRITICAL_FAILURES=0")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
