from candidate_transformer.core.canonical import (
    CandidateLinks,
    CanonicalCandidate,
    CanonicalExperience,
    CanonicalSkill,
)
from candidate_transformer.core.projection import project_candidate


def make_candidate() -> CanonicalCandidate:
    return CanonicalCandidate(
        candidate_id="cand_test",
        full_name="Alex Chen",
        emails=("alex@example.com",),
        phones=(),
        links=CandidateLinks(github="https://github.com/alexchen"),
        skills=(
            CanonicalSkill(
                name="Python",
                confidence=0.75,
                sources=("recruiter_notes:alex.txt",),
            ),
            CanonicalSkill(
                name="Kubernetes",
                confidence=0.70,
                sources=("recruiter_notes:alex.txt",),
            ),
        ),
        experience=(
            CanonicalExperience(
                company="Acme",
                title="Backend Engineer",
                confidence=0.85,
                sources=("recruiter_csv:candidates.csv",),
            ),
        ),
        provenance=(),
        overall_confidence=0.82,
    )


def test_project_candidate_basic_fields():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "name",
                "from": "full_name",
                "type": "string",
                "required": True,
            },
            {
                "path": "email",
                "from": "emails[0]",
                "type": "string",
                "required": True,
            },
            {
                "path": "github",
                "from": "links.github",
                "type": "string",
            },
            {
                "path": "skills",
                "from": "skills[].name",
                "type": "string[]",
            },
        ],
        "include_confidence": True,
        "on_missing": "null",
    }

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {
        "name": "Alex Chen",
        "email": "alex@example.com",
        "github": "https://github.com/alexchen",
        "skills": ["Python", "Kubernetes"],
        "overall_confidence": 0.82,
    }


def test_project_candidate_nested_output_path():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "contact.email",
                "from": "emails[0]",
                "type": "string",
            },
            {
                "path": "profile.github",
                "from": "links.github",
                "type": "string",
            },
        ]
    }

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {
        "contact": {
            "email": "alex@example.com",
        },
        "profile": {
            "github": "https://github.com/alexchen",
        },
    }


def test_project_candidate_can_select_primary_secondary_or_all_emails():
    candidate = make_candidate()
    candidate = CanonicalCandidate(
        candidate_id=candidate.candidate_id,
        full_name=candidate.full_name,
        emails=(
            "primary@example.com",
            "secondary-one@example.com",
            "secondary-two@example.com",
        ),
        phones=candidate.phones,
        links=candidate.links,
        skills=candidate.skills,
        experience=candidate.experience,
        provenance=candidate.provenance,
        overall_confidence=candidate.overall_confidence,
        primary_email="primary@example.com",
        secondary_emails=(
            "secondary-one@example.com",
            "secondary-two@example.com",
        ),
        email_resolution_status="resolved",
        email_confidence=0.98,
    )
    config = {
        "fields": [
            {
                "path": "primary_email",
                "from": "primary_email",
                "type": "string",
            },
            {
                "path": "secondary_emails",
                "from": "secondary_emails",
                "type": "string[]",
            },
            {
                "path": "all_emails",
                "from": "emails",
                "type": "string[]",
            },
        ]
    }

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {
        "primary_email": "primary@example.com",
        "secondary_emails": [
            "secondary-one@example.com",
            "secondary-two@example.com",
        ],
        "all_emails": [
            "primary@example.com",
            "secondary-one@example.com",
            "secondary-two@example.com",
        ],
    }


def test_project_candidate_can_select_primary_secondary_or_all_phones():
    candidate = make_candidate()
    candidate = CanonicalCandidate(
        candidate_id=candidate.candidate_id,
        full_name=candidate.full_name,
        emails=candidate.emails,
        phones=(
            "+919111111111",
            "+919222222222",
            "+919333333333",
        ),
        links=candidate.links,
        skills=candidate.skills,
        experience=candidate.experience,
        provenance=candidate.provenance,
        overall_confidence=candidate.overall_confidence,
        primary_phone="+919111111111",
        secondary_phones=("+919222222222", "+919333333333"),
        phone_resolution_status="resolved",
        phone_confidence=0.93,
    )
    config = {
        "fields": [
            {
                "path": "primary_phone",
                "from": "primary_phone",
                "type": "string",
            },
            {
                "path": "secondary_phones",
                "from": "secondary_phones",
                "type": "string[]",
            },
            {
                "path": "all_phones",
                "from": "phones",
                "type": "string[]",
            },
        ]
    }

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {
        "primary_phone": "+919111111111",
        "secondary_phones": ["+919222222222", "+919333333333"],
        "all_phones": [
            "+919111111111",
            "+919222222222",
            "+919333333333",
        ],
    }


def test_project_candidate_missing_value_defaults_to_null():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "phone",
                "from": "phones[0]",
                "type": "string",
            }
        ],
        "on_missing": "null",
    }

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {
        "phone": None,
    }


def test_project_candidate_missing_value_can_be_omitted():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "phone",
                "from": "phones[0]",
                "type": "string",
            }
        ],
        "on_missing": "omit",
    }

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {}


def test_project_candidate_required_missing_value_is_error():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "phone",
                "from": "phones[0]",
                "type": "string",
                "required": True,
            }
        ],
        "on_missing": "null",
    }

    result = project_candidate(candidate, config)

    assert not result.ok
    assert result.output == {}
    assert len(result.errors) == 1
    assert "Required field" in result.errors[0]


def test_project_candidate_type_validation_error():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "skills",
                "from": "skills[].name",
                "type": "string",
            }
        ]
    }

    result = project_candidate(candidate, config)

    assert not result.ok
    assert len(result.errors) == 1
    assert "expected string" in result.errors[0]

def test_project_candidate_applies_e164_normalization():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "phone",
                "from": "phones[0]",
                "type": "string",
                "normalize": "E164",
            }
        ],
        "on_missing": "null",
    }

    # The test candidate has no phone, so use a modified candidate.
    candidate = CanonicalCandidate(
        candidate_id=candidate.candidate_id,
        full_name=candidate.full_name,
        emails=candidate.emails,
        phones=("6502530000",),
        links=candidate.links,
        skills=candidate.skills,
        experience=candidate.experience,
        provenance=candidate.provenance,
        overall_confidence=candidate.overall_confidence,
    )

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {
        "phone": "+916502530000",
    }


def test_project_candidate_applies_canonical_skill_normalization():
    candidate = make_candidate()

    candidate = CanonicalCandidate(
        candidate_id=candidate.candidate_id,
        full_name=candidate.full_name,
        emails=candidate.emails,
        phones=candidate.phones,
        links=candidate.links,
        skills=(
            CanonicalSkill(
                name="py",
                confidence=0.70,
                sources=("test:test",),
            ),
            CanonicalSkill(
                name="k8s",
                confidence=0.70,
                sources=("test:test",),
            ),
        ),
        experience=candidate.experience,
        provenance=candidate.provenance,
        overall_confidence=candidate.overall_confidence,
    )

    config = {
        "fields": [
            {
                "path": "skills",
                "from": "skills[].name",
                "type": "string[]",
                "normalize": "canonical",
            }
        ],
        "on_missing": "null",
    }

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {
        "skills": ["Python", "Kubernetes"],
    }


def test_project_candidate_rejects_unknown_normalizer():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "phone",
                "from": "phones[0]",
                "type": "string",
                "normalize": "definitely-invalid",
            }
        ],
        "on_missing": "null",
    }

    result = project_candidate(candidate, config)

    assert not result.ok
    assert len(result.errors) == 1
    assert "normalize must be one of" in result.errors[0]


def test_project_candidate_e164_normalization_rejects_invalid_phone():
    candidate = make_candidate()

    candidate = CanonicalCandidate(
        candidate_id=candidate.candidate_id,
        full_name=candidate.full_name,
        emails=candidate.emails,
        phones=("not-a-phone",),
        links=candidate.links,
        skills=candidate.skills,
        experience=candidate.experience,
        provenance=candidate.provenance,
        overall_confidence=candidate.overall_confidence,
    )

    config = {
        "fields": [
            {
                "path": "phone",
                "from": "phones[0]",
                "type": "string",
                "normalize": "E164",
            }
        ],
        "on_missing": "null",
    }

    result = project_candidate(candidate, config)

    assert not result.ok
    assert len(result.errors) == 1
    assert "could not normalize" in result.errors[0]

def test_project_candidate_can_read_new_default_schema_fields():
    candidate = make_candidate()

    config = {
        "fields": [
            {
                "path": "location",
                "from": "location",
                "type": "object",
            },
            {
                "path": "headline",
                "from": "headline",
                "type": "string",
            },
            {
                "path": "years_experience",
                "from": "years_experience",
                "type": "number",
            },
            {
                "path": "education",
                "from": "education",
                "type": "array",
            },
            {
                "path": "linkedin",
                "from": "links.linkedin",
                "type": "string",
            },
            {
                "path": "portfolio",
                "from": "links.portfolio",
                "type": "string",
            },
            {
                "path": "other_links",
                "from": "links.other",
                "type": "array",
            },
        ],
        "on_missing": "null",
    }

    result = project_candidate(candidate, config)

    assert result.ok
    assert result.output == {
        "location": {
            "city": None,
            "region": None,
            "country": None,
        },
        "headline": None,
        "years_experience": None,
        "education": [],
        "linkedin": None,
        "portfolio": None,
        "other_links": [],
    }
