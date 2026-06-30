from candidate_transformer.core.entity_resolution import resolve_candidate_clusters
from candidate_transformer.core.field_resolution import (
    OVERALL_CONFIDENCE_WEIGHTS,
    resolve_canonical_candidate,
)
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


def test_overall_confidence_weights():
    assert OVERALL_CONFIDENCE_WEIGHTS == {
        "name": 0.15,
        "email": 0.25,
        "phone": 0.10,
        "github": 0.20,
        "skills": 0.15,
        "experience": 0.15,
    }
    assert sum(OVERALL_CONFIDENCE_WEIGHTS.values()) == 1.0


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


def test_workplace_aliases_deduplicate_only_matching_roles():
    observations: list[Observation] = []
    workplaces = [
        ("r1", "Google", "Software Engineer"),
        ("r2", "Google LLC", "Senior Backend Engineer"),
        ("r3", "GOOGLE L.L.C.", "software engineer"),
        ("r4", "Alphabet", "Backend Engineer"),
    ]

    for record_id, company, title in workplaces:
        observations.extend(
            [
                make_observation(
                    record_id=record_id,
                    field_path="candidate_ref",
                    value="C001",
                ),
                make_observation(
                    record_id=record_id,
                    field_path="experience.company",
                    value=company,
                ),
                make_observation(
                    record_id=record_id,
                    field_path="experience.title",
                    value=title,
                ),
            ]
        )

    candidate = make_candidate(observations)
    workplaces_by_title = {
        experience.title: experience.company
        for experience in candidate.experience
    }

    assert workplaces_by_title == {
        "Backend Engineer": "Alphabet",
        "Senior Backend Engineer": "Google",
        "Software Engineer": "Google",
    }

    software_engineer = next(
        experience
        for experience in candidate.experience
        if experience.title == "Software Engineer"
    )
    assert len(software_engineer.sources) == 1


def test_same_workplace_and_title_with_different_dates_remain_separate():
    observations: list[Observation] = []
    for record_id, company, start, end in (
        ("r1", "Google", "2020", "2021"),
        ("r2", "Google LLC", "2023", "2024"),
    ):
        for field_path, value in (
            ("candidate_ref", "C001"),
            ("experience.company", company),
            ("experience.title", "Software Engineer"),
            ("experience.start", start),
            ("experience.end", end),
        ):
            observations.append(
                make_observation(
                    record_id=record_id,
                    field_path=field_path,
                    value=value,
                )
            )

    candidate = make_candidate(observations)

    assert [
        (experience.company, experience.title, experience.start, experience.end)
        for experience in candidate.experience
    ] == [
        ("Google", "Software Engineer", "2020", "2021"),
        ("Google", "Software Engineer", "2023", "2024"),
    ]


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


def test_notes_corroboration_selects_primary_among_equal_csv_emails():
    observations = [
        make_observation(
            record_id="csv_1",
            field_path="candidate_ref",
            value="C001",
            confidence=0.95,
        ),
        make_observation(
            record_id="csv_1",
            field_path="emails",
            value="first@example.com",
            confidence=0.95,
        ),
        make_observation(
            record_id="csv_2",
            field_path="candidate_ref",
            value="C001",
            confidence=0.95,
        ),
        make_observation(
            record_id="csv_2",
            field_path="emails",
            value="supported@example.com",
            confidence=0.95,
        ),
        make_observation(
            record_id="note_1",
            field_path="emails",
            value="supported@example.com",
            confidence=0.76,
            source_type="recruiter_notes",
            source_id="alex.txt",
        ),
    ]

    candidate = make_candidate(observations)

    assert candidate.primary_email == "supported@example.com"
    assert candidate.secondary_emails == ("first@example.com",)
    assert candidate.emails == (
        "supported@example.com",
        "first@example.com",
    )
    assert candidate.email_resolution_status == "resolved"
    assert candidate.email_selection_reason == "csv_email_corroborated_by_notes"
    assert candidate.email_details[0].confidence == 0.98
    assert candidate.email_details[0].sources == (
        "recruiter_csv:test.csv",
        "recruiter_notes:alex.txt",
    )


def test_latest_complete_csv_application_wins_over_corroborated_old_email():
    observations = [
        make_observation(
            record_id="csv_old",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="csv_old",
            field_path="emails",
            value="old@example.com",
            confidence=0.95,
        ),
        make_observation(
            record_id="csv_old",
            field_path="application.applied_at",
            value="2025-01-01T00:00:00Z",
            confidence=0.90,
        ),
        make_observation(
            record_id="csv_new",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="csv_new",
            field_path="emails",
            value="new@example.com",
            confidence=0.95,
        ),
        make_observation(
            record_id="csv_new",
            field_path="application.applied_at",
            value="2026-01-01T00:00:00Z",
            confidence=0.90,
        ),
        make_observation(
            record_id="note_1",
            field_path="emails",
            value="old@example.com",
            confidence=0.76,
            source_type="recruiter_notes",
            source_id="old-note.txt",
        ),
    ]

    candidate = make_candidate(observations)

    assert candidate.primary_email == "new@example.com"
    assert candidate.secondary_emails == ("old@example.com",)
    assert candidate.email_selection_reason == "latest_csv_application"
    assert candidate.email_details[0].latest_application_at == (
        "2026-01-01T00:00:00Z"
    )
    assert candidate.email_details[1].confidence == 0.98


def test_incomplete_recency_falls_back_to_corroboration():
    observations = [
        make_observation(
            record_id="csv_dated",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="csv_dated",
            field_path="emails",
            value="dated@example.com",
            confidence=0.95,
        ),
        make_observation(
            record_id="csv_dated",
            field_path="application.applied_at",
            value="2026-01-01T00:00:00Z",
        ),
        make_observation(
            record_id="csv_undated",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="csv_undated",
            field_path="emails",
            value="supported@example.com",
            confidence=0.95,
        ),
        make_observation(
            record_id="note",
            field_path="emails",
            value="supported@example.com",
            confidence=0.76,
            source_type="recruiter_notes",
            source_id="note.txt",
        ),
    ]

    candidate = make_candidate(observations)

    assert candidate.primary_email == "supported@example.com"
    assert candidate.email_selection_reason == "csv_email_corroborated_by_notes"


def test_equal_csv_email_evidence_is_left_ambiguous():
    observations = [
        make_observation(
            record_id="csv_1",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="csv_1",
            field_path="emails",
            value="first@example.com",
            confidence=0.95,
        ),
        make_observation(
            record_id="csv_2",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="csv_2",
            field_path="emails",
            value="second@example.com",
            confidence=0.95,
        ),
    ]

    candidate = make_candidate(observations)

    assert candidate.primary_email is None
    assert candidate.secondary_emails == (
        "first@example.com",
        "second@example.com",
    )
    assert candidate.email_resolution_status == "ambiguous"
    assert candidate.email_selection_reason == "equal_csv_email_evidence"


def test_notes_only_email_is_preserved_but_not_promoted_to_primary():
    candidate = make_candidate(
        [
            make_observation(
                record_id="note",
                field_path="emails",
                value="notes@example.com",
                confidence=0.76,
                source_type="recruiter_notes",
                source_id="note.txt",
            )
        ]
    )

    assert candidate.primary_email is None
    assert candidate.secondary_emails == ("notes@example.com",)
    assert candidate.email_resolution_status == "unstructured_only"


def test_email_corroboration_bonus_is_bounded_and_sources_are_distinct():
    observations = [
        make_observation(
            record_id="csv",
            field_path="emails",
            value="alex@example.com",
            confidence=0.95,
        )
    ]
    for index in range(10):
        observations.append(
            make_observation(
                record_id=f"note_{index}",
                field_path="emails",
                value="alex@example.com",
                confidence=0.76,
                source_type="recruiter_notes",
                source_id=f"note-{index}.txt",
            )
        )

    candidate = make_candidate(observations)

    assert candidate.email_details[0].confidence == 0.99


def test_distinct_application_ids_add_email_support():
    observations = []
    for record_id, application_id, email in (
        ("csv_1", "APP-1", "repeated@example.com"),
        ("csv_2", "APP-2", "repeated@example.com"),
        ("csv_3", "APP-3", "other@example.com"),
    ):
        observations.extend(
            [
                make_observation(
                    record_id=record_id,
                    field_path="candidate_ref",
                    value="C001",
                ),
                make_observation(
                    record_id=record_id,
                    field_path="application.id",
                    value=application_id,
                ),
                make_observation(
                    record_id=record_id,
                    field_path="emails",
                    value=email,
                    confidence=0.95,
                ),
            ]
        )

    candidate = make_candidate(observations)

    assert candidate.primary_email == "repeated@example.com"
    assert candidate.email_selection_reason == "repeated_distinct_applications"
    assert candidate.email_details[0].confidence == 0.97
    assert candidate.email_details[0].distinct_application_count == 2


def test_duplicate_rows_with_same_application_id_do_not_add_support():
    observations = []
    for record_id, application_id, email in (
        ("csv_1", "APP-1", "duplicate@example.com"),
        ("csv_2", "APP-1", "duplicate@example.com"),
        ("csv_3", "APP-2", "other@example.com"),
    ):
        observations.extend(
            [
                make_observation(
                    record_id=record_id,
                    field_path="candidate_ref",
                    value="C001",
                ),
                make_observation(
                    record_id=record_id,
                    field_path="application.id",
                    value=application_id,
                ),
                make_observation(
                    record_id=record_id,
                    field_path="emails",
                    value=email,
                    confidence=0.95,
                ),
            ]
        )

    candidate = make_candidate(observations)

    assert candidate.primary_email is None
    assert candidate.email_resolution_status == "ambiguous"
    assert all(detail.confidence == 0.95 for detail in candidate.email_details)
    duplicate_detail = next(
        detail
        for detail in candidate.email_details
        if detail.value == "duplicate@example.com"
    )
    assert duplicate_detail.distinct_application_count == 1


def test_email_resolution_status_affects_email_and_overall_confidence():
    resolved = make_candidate(
        [
            make_observation(
                record_id="resolved",
                field_path="emails",
                value="resolved@example.com",
                confidence=0.95,
            )
        ]
    )
    ambiguous = make_candidate(
        [
            make_observation(
                record_id="ambiguous_1",
                field_path="candidate_ref",
                value="C001",
            ),
            make_observation(
                record_id="ambiguous_1",
                field_path="emails",
                value="one@example.com",
                confidence=0.95,
            ),
            make_observation(
                record_id="ambiguous_2",
                field_path="candidate_ref",
                value="C001",
            ),
            make_observation(
                record_id="ambiguous_2",
                field_path="emails",
                value="two@example.com",
                confidence=0.95,
            ),
        ]
    )

    assert resolved.email_confidence == 0.95
    assert ambiguous.email_confidence < ambiguous.email_details[0].confidence
    assert ambiguous.email_confidence == 0.47
    assert resolved.overall_confidence > ambiguous.overall_confidence


def test_notes_corroboration_selects_primary_among_equal_csv_phones():
    observations = [
        make_observation(
            record_id="csv_1",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="csv_1",
            field_path="phones",
            value="+919111111111",
            confidence=0.90,
        ),
        make_observation(
            record_id="csv_2",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="csv_2",
            field_path="phones",
            value="+919222222222",
            confidence=0.90,
        ),
        make_observation(
            record_id="note",
            field_path="candidate_ref",
            value="C001",
            source_type="ingestion_manifest",
        ),
        make_observation(
            record_id="note",
            field_path="phones",
            value="+919222222222",
            confidence=0.72,
            source_type="recruiter_notes",
            source_id="note.txt",
        ),
    ]

    candidate = make_candidate(observations)

    assert candidate.primary_phone == "+919222222222"
    assert candidate.secondary_phones == ("+919111111111",)
    assert candidate.phone_resolution_status == "resolved"
    assert candidate.phone_selection_reason == "csv_phone_corroborated_by_notes"
    assert candidate.phone_confidence == 0.93
    assert candidate.phone_details[0].corroborating_notes_count == 1


def test_latest_complete_csv_application_phone_wins_over_old_votes():
    observations = []
    for record_id, application_time, phone in (
        ("csv_old", "2025-01-01T00:00:00Z", "+919111111111"),
        ("csv_new", "2026-01-01T00:00:00Z", "+919222222222"),
    ):
        observations.extend(
            [
                make_observation(
                    record_id=record_id,
                    field_path="candidate_ref",
                    value="C001",
                ),
                make_observation(
                    record_id=record_id,
                    field_path="application.applied_at",
                    value=application_time,
                ),
                make_observation(
                    record_id=record_id,
                    field_path="phones",
                    value=phone,
                    confidence=0.90,
                ),
            ]
        )
    observations.extend(
        [
            make_observation(
                record_id="note",
                field_path="candidate_ref",
                value="C001",
                source_type="ingestion_manifest",
            ),
            make_observation(
                record_id="note",
                field_path="phones",
                value="+919111111111",
                confidence=0.72,
                source_type="recruiter_notes",
                source_id="old-note.txt",
            ),
        ]
    )

    candidate = make_candidate(observations)

    assert candidate.primary_phone == "+919222222222"
    assert candidate.phone_selection_reason == "latest_csv_application"
    assert candidate.phone_confidence == 0.90
    assert candidate.phone_details[1].confidence == 0.93


def test_distinct_applications_add_phone_support_but_duplicates_do_not():
    distinct_observations = []
    for record_id, application_id, phone in (
        ("csv_1", "APP-1", "+919111111111"),
        ("csv_2", "APP-2", "+919111111111"),
        ("csv_3", "APP-3", "+919222222222"),
    ):
        distinct_observations.extend(
            [
                make_observation(
                    record_id=record_id,
                    field_path="candidate_ref",
                    value="C001",
                ),
                make_observation(
                    record_id=record_id,
                    field_path="application.id",
                    value=application_id,
                ),
                make_observation(
                    record_id=record_id,
                    field_path="phones",
                    value=phone,
                    confidence=0.90,
                ),
            ]
        )

    distinct_candidate = make_candidate(distinct_observations)

    assert distinct_candidate.primary_phone == "+919111111111"
    assert distinct_candidate.phone_confidence == 0.92
    assert distinct_candidate.phone_details[0].distinct_application_count == 2

    duplicate_observations = []
    for record_id, application_id, phone in (
        ("csv_1", "APP-1", "+919111111111"),
        ("csv_2", "APP-1", "+919111111111"),
        ("csv_3", "APP-2", "+919222222222"),
    ):
        duplicate_observations.extend(
            [
                make_observation(
                    record_id=record_id,
                    field_path="candidate_ref",
                    value="C001",
                ),
                make_observation(
                    record_id=record_id,
                    field_path="application.id",
                    value=application_id,
                ),
                make_observation(
                    record_id=record_id,
                    field_path="phones",
                    value=phone,
                    confidence=0.90,
                ),
            ]
        )

    duplicate_candidate = make_candidate(duplicate_observations)

    assert duplicate_candidate.primary_phone is None
    assert duplicate_candidate.phone_resolution_status == "ambiguous"
    assert duplicate_candidate.phone_confidence == 0.45


def test_notes_only_phone_is_secondary_with_reduced_confidence():
    candidate = make_candidate(
        [
            make_observation(
                record_id="note",
                field_path="phones",
                value="+919111111111",
                confidence=0.72,
                source_type="recruiter_notes",
                source_id="note.txt",
            )
        ]
    )

    assert candidate.primary_phone is None
    assert candidate.secondary_phones == ("+919111111111",)
    assert candidate.phone_resolution_status == "unstructured_only"
    assert candidate.phone_confidence == 0.54


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
    assert candidate_dict["primary_email"] == "alex@example.com"
    assert candidate_dict["secondary_emails"] == ()
    assert candidate_dict["email_resolution_status"] == "resolved"

    assert candidate_dict["links"] == {
        "linkedin": None,
        "github": None,
        "portfolio": None,
        "other": (),
    }
