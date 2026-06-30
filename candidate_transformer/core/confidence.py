from __future__ import annotations


SOURCE_RELIABILITY = {
    "recruiter_csv": 0.95,
    "recruiter_notes": 0.80,
    "github_profile": 0.75,
    "ingestion_manifest": 0.98,
}


FIELD_RELIABILITY = {
    # Structured CSV fields
    "explicit_candidate_ref": 1.00,
    "explicit_email": 1.00,
    "explicit_phone": 0.95,
    "explicit_name": 0.95,
    "explicit_company_or_title": 0.90,
    "explicit_url": 0.95,
    "explicit_application_time": 0.95,
    "explicit_application_ref": 1.00,

    # Future notes/GitHub fields
    "provided_candidate_ref": 1.00,
    "regex_email": 0.95,
    "regex_phone": 0.90,
    "regex_url": 0.90,
    "skill_dictionary_match": 0.85,
    "provided_profile_url": 0.95,
    "api_profile_name": 0.85,
    "api_profile_email": 0.90,
    "api_profile_url": 1.00,
    "api_profile_blog": 0.85,
    "api_profile_bio": 0.70,
    "api_profile_company": 0.75,
    "github_repo_language": 0.85,
}


def clamp_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def observation_confidence(
    *,
    source_reliability: float,
    field_reliability: float,
    extraction_quality: float = 1.0,
    validation_quality: float = 1.0,
) -> float:
    """
    Observation confidence is our prior trust in one extracted value.

    It is not final field confidence.
    Final confidence will later consider corroboration and conflicts.
    """

    value = (
        source_reliability
        * field_reliability
        * extraction_quality
        * validation_quality
    )

    return clamp_confidence(value)


def confidence_for(
    source_type: str,
    field_kind: str,
    *,
    extraction_quality: float = 1.0,
    validation_quality: float = 1.0,
) -> float:
    if source_type not in SOURCE_RELIABILITY:
        raise ValueError(f"Unknown source_type: {source_type}")

    if field_kind not in FIELD_RELIABILITY:
        raise ValueError(f"Unknown field_kind: {field_kind}")

    return observation_confidence(
        source_reliability=SOURCE_RELIABILITY[source_type],
        field_reliability=FIELD_RELIABILITY[field_kind],
        extraction_quality=extraction_quality,
        validation_quality=validation_quality,
    )
