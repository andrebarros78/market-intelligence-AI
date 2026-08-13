import json

from market_intelligence.core.json_safety import json_safe


def test_non_finite_detector_evidence_becomes_strict_json() -> None:
    safe = json_safe({"robust_z": float("inf"), "nested": [float("nan"), 1.0]})
    assert safe["robust_z"] is None
    assert safe["robust_z_non_finite"] == "positive_infinity"
    assert safe["nested"] == [None, 1.0]
    encoded = json.dumps(safe, allow_nan=False)
    assert "Infinity" not in encoded
    assert "NaN" not in encoded
