from market_intelligence.ai.probe_policy import classify_probe_result


def test_probe_policy_remains_strict_by_default() -> None:
    decision = classify_probe_result(
        authenticated=True,
        model_available=False,
        allow_model_unlisted=False,
    )

    assert decision.status == "model_unavailable"
    assert decision.exit_code == 3


def test_probe_policy_allows_explicit_advisory_model_catalog() -> None:
    decision = classify_probe_result(
        authenticated=True,
        model_available=False,
        allow_model_unlisted=True,
    )

    assert decision.status == "authenticated_model_unlisted"
    assert decision.exit_code == 0


def test_probe_policy_still_requires_authentication() -> None:
    decision = classify_probe_result(
        authenticated=False,
        model_available=False,
        allow_model_unlisted=True,
    )

    assert decision.status == "model_unavailable"
    assert decision.exit_code == 3


def test_probe_policy_passes_when_model_is_listed() -> None:
    decision = classify_probe_result(
        authenticated=True,
        model_available=True,
        allow_model_unlisted=False,
    )

    assert decision.status == "ok"
    assert decision.exit_code == 0
