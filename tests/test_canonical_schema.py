from dataclasses import replace

from candidate_transformer.core.canonical import (
    CandidateLinks,
    CandidateLocation,
    CanonicalCandidate,
)
from candidate_transformer.core.canonical_schema import validate_canonical_candidate


def make_candidate() -> CanonicalCandidate:
    return CanonicalCandidate(
        candidate_id="cand_schema_test",
        full_name="Alex Chen",
        emails=("alex@example.com",),
        phones=("+919876543210",),
        links=CandidateLinks(),
        skills=(),
        experience=(),
        provenance=(),
        overall_confidence=0.8,
        primary_email="alex@example.com",
        email_resolution_status="resolved",
        email_confidence=0.95,
        primary_phone="+919876543210",
        phone_resolution_status="resolved",
        phone_confidence=0.9,
    )


def test_canonical_schema_accepts_valid_candidate():
    assert validate_canonical_candidate(make_candidate()) == []


def test_canonical_schema_rejects_confidence_outside_range():
    candidate = replace(make_candidate(), overall_confidence=1.2)

    errors = validate_canonical_candidate(candidate)

    assert len(errors) == 1
    assert errors[0].startswith("$.overall_confidence:")
    assert "greater than the maximum" in errors[0]


def test_canonical_schema_rejects_invalid_nested_field_type():
    candidate = replace(
        make_candidate(),
        location=CandidateLocation(city=123),
    )

    errors = validate_canonical_candidate(candidate)

    assert len(errors) == 1
    assert errors[0].startswith("$.location.city:")
    assert "is not of type" in errors[0]


def test_canonical_schema_rejects_unknown_resolution_status():
    candidate = replace(make_candidate(), email_resolution_status="guessed")

    errors = validate_canonical_candidate(candidate)

    assert len(errors) == 1
    assert errors[0].startswith("$.email_resolution_status:")
    assert "is not one of" in errors[0]
