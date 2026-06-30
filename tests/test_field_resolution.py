from candidate_transformer.core.entity_resolution import resolve_candidate_clusters
from candidate_transformer.core.field_resolution import resolve_canonical_candidate
from candidate_transformer.core.models import Observation, SourceRef


def make_observation(
    *,
    record_id: str,
    field_path: str,
    value: str,
    confidence: float = 0.9,
    source_type: str = "recruiter_csv",
    source_id: str = "test.csv",
) -> Observation:
    return Observation(
        record_id=record_id,
        field_path=field_path,
        raw_value=value,
        normalized_value=value,
        source=SourceRef(
            source_type=source_type,
            source_id=source_id,
            locator=None,
        ),
        method="test",
        confidence=confidence,
    )


def make_candidate(observations: list[Observation]):
    clusters = resolve_candidate_clusters(observations)
    assert len(clusters) == 1
    return resolve_canonical_candidate(clusters[0])


def test_resolve_basic_canonical_candidate():
    observations = [
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex Chen",
            confidence=0.90,
        ),
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex@example.com",
            confidence=0.95,
        ),
        make_observation(
            record_id="r1",
            field_path="phones",
            value="+917697077601",
            confidence=0.90,
        ),
        make_observation(
            record_id="r1",
            field_path="links.github",
            value="https://github.com/alexchen",
            confidence=0.90,
        ),
        make_observation(
            record_id="r1",
            field_path="experience.company",
            value="Acme",
            confidence=0.85,
        ),
        make_observation(
            record_id="r1",
            field_path="experience.title",
            value="Backend Engineer",
            confidence=0.85,
        ),
        make_observation(
            record_id="r1",
            field_path="skills",
            value="Python",
            confidence=0.70,
            source_type="recruiter_notes",
            source_id="alex.txt",
        ),
    ]

    candidate = make_candidate(observations)

    assert candidate.full_name == "Alex Chen"
    assert candidate.emails == ("alex@example.com",)
    assert candidate.phones == ("+917697077601",)
    assert candidate.links.github == "https://github.com/alexchen"

    assert len(candidate.skills) == 1
    assert candidate.skills[0].name == "Python"

    assert len(candidate.experience) == 1
    assert candidate.experience[0].company == "Acme"
    assert candidate.experience[0].title == "Backend Engineer"

    assert candidate.overall_confidence > 0
    assert candidate.provenance


def test_same_email_records_are_unioned():
    observations = [
        make_observation(
            record_id="csv_row_1",
            field_path="full_name",
            value="Alex Chen",
        ),
        make_observation(
            record_id="csv_row_1",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="note_1",
            field_path="emails",
            value="alex@example.com",
            source_type="recruiter_notes",
            source_id="alex.txt",
        ),
        make_observation(
            record_id="note_1",
            field_path="phones",
            value="+917697077601",
            source_type="recruiter_notes",
            source_id="alex.txt",
        ),
    ]

    candidate = make_candidate(observations)

    assert candidate.full_name == "Alex Chen"
    assert candidate.emails == ("alex@example.com",)
    assert candidate.phones == ("+917697077601",)


def test_scalar_field_chooses_highest_confidence_value():
    observations = [
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex C.",
            confidence=0.70,
            source_type="recruiter_notes",
            source_id="alex.txt",
        ),
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex Chen",
            confidence=0.90,
            source_type="recruiter_csv",
            source_id="candidates.csv",
        ),
    ]

    candidate = make_candidate(observations)

    assert candidate.full_name == "Alex Chen"


def test_skills_are_deduped_and_corroborated():
    observations = [
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r1",
            field_path="skills",
            value="Python",
            confidence=0.70,
            source_type="recruiter_notes",
            source_id="alex.txt",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="skills",
            value="Python",
            confidence=0.65,
            source_type="github_profile",
            source_id="github.com/alexchen",
        ),
    ]

    candidate = make_candidate(observations)

    assert len(candidate.skills) == 1
    assert candidate.skills[0].name == "Python"
    assert candidate.skills[0].confidence == 0.75


def test_duplicate_experience_is_deduped():
    observations = [
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r1",
            field_path="experience.company",
            value="Acme",
            confidence=0.85,
        ),
        make_observation(
            record_id="r1",
            field_path="experience.title",
            value="Engineer",
            confidence=0.85,
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="experience.company",
            value="Acme",
            confidence=0.85,
        ),
        make_observation(
            record_id="r2",
            field_path="experience.title",
            value="Engineer",
            confidence=0.85,
        ),
    ]

    candidate = make_candidate(observations)

    assert len(candidate.experience) == 1
    assert candidate.experience[0].company == "Acme"
    assert candidate.experience[0].title == "Engineer"


def test_canonical_candidate_contains_full_default_schema():
    observations = [
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex Chen",
        ),
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex@example.com",
        ),
    ]

    candidate = make_candidate(observations)
    candidate_dict = candidate.to_dict()

    assert candidate_dict["location"] == {
        "city": None,
        "region": None,
        "country": None,
    }

    assert candidate_dict["headline"] is None
    assert candidate_dict["years_experience"] is None
    assert candidate_dict["education"] == ()

    assert candidate_dict["links"] == {
        "linkedin": None,
        "github": None,
        "portfolio": None,
        "other": (),
    }