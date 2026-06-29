from candidate_transformer.core.confidence import (
    clamp_confidence,
    confidence_for,
    observation_confidence,
)


def test_clamp_confidence():
    assert clamp_confidence(1.5) == 1.0
    assert clamp_confidence(-0.2) == 0.0
    assert clamp_confidence(0.876) == 0.88


def test_observation_confidence():
    assert observation_confidence(
        source_reliability=0.95,
        field_reliability=1.0,
    ) == 0.95

    assert observation_confidence(
        source_reliability=0.95,
        field_reliability=0.95,
    ) == 0.9


def test_confidence_for_recruiter_csv_email():
    assert confidence_for("recruiter_csv", "explicit_email") == 0.95


def test_confidence_for_recruiter_csv_company_or_title():
    assert confidence_for("recruiter_csv", "explicit_company_or_title") == 0.85