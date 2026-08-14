from pathlib import Path


FORBIDDEN_ADAPTER_IMPORTS = (
    "market_intelligence.marketplaces.mercadolivre",
    "market_intelligence.marketplaces.amazon",
    "market_intelligence.marketplaces.shopee",
    "market_intelligence.marketplaces.tiktok",
    "market_intelligence.marketplaces.shein",
)


def test_core_layers_do_not_depend_on_concrete_marketplace_adapters() -> None:
    root = Path("src/market_intelligence")
    protected = ("core", "intelligence", "skills", "agents")
    violations: list[str] = []

    for package in protected:
        for path in (root / package).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_ADAPTER_IMPORTS:
                if forbidden in text:
                    violations.append(f"{path}:{forbidden}")

    assert violations == []
