from __future__ import annotations

import ast
from pathlib import Path


def test_sovereign_core_has_no_marketplace_transport_or_write_adapter_imports() -> None:
    package = Path("src/market_intelligence/intelligence/sovereign")
    forbidden_fragments = ("mercadolivre.client", "controlled_write", "write_adapter", "httpx", "requests")
    violations: list[str] = []
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = ",".join(alias.name for alias in node.names)
            if any(fragment in module.lower() for fragment in forbidden_fragments):
                violations.append(f"{path}:{module}")
    assert violations == []
