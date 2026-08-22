import importlib

import pytest


def load_smoke_module():
    try:
        return importlib.import_module("smoke_test_requirements_verification")
    except ModuleNotFoundError:
        pytest.fail(
            "smoke_test_requirements_verification has not been implemented"
        )


def test_smoke_harness_proves_valid_and_atomic_invalid_paths() -> None:
    smoke = load_smoke_module()
    output: list[str] = []

    exit_code = smoke.run_smoke(output=output.append)

    assert exit_code == 0
    assert output == [
        "requirements-verification-validator pass "
        "requirements=5 assessed=5 evidence=3 all_statuses=true "
        "ungrounded_rejected=true"
    ]


def test_smoke_harness_fails_when_ungrounded_candidate_is_accepted() -> None:
    smoke = load_smoke_module()
    output: list[str] = []
    accepted_result = smoke.normalize_requirements_verification_candidate(
        smoke.DEFAULT_REQUEST,
        smoke.DEFAULT_CANDIDATE,
    )

    def always_accept(_request, _candidate):
        return accepted_result

    exit_code = smoke.run_smoke(
        normalizer=always_accept,
        output=output.append,
    )

    assert exit_code == 1
    assert output == ["requirements-verification-validator failed"]
