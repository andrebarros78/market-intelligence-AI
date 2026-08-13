from __future__ import annotations

import math
from typing import Any


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if isinstance(item, float) and not math.isfinite(item):
                result[name] = None
                marker = "nan" if math.isnan(item) else "positive_infinity" if item > 0 else "negative_infinity"
                result[f"{name}_non_finite"] = marker
            else:
                result[name] = json_safe(item)
        return result
    return value
