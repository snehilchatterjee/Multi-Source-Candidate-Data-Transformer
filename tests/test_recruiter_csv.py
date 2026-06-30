from pathlib import Path

from candidate_transformer.adapters.recruiter_csv import parse_recruiter_csv


def test_parse_recruiter_csv_basic(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email,phone,current_company,title,github_url\n"
        "Alex Chen,ALEX.CHEN@Example.com,+91 98765 43210,Acme,Backend Engineer,github.com/alexchen\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path)

    assert result.errors == []
    assert result.warnings == []

    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert ("full_name", "Alex Chen") in values
    assert ("emails", "alex.chen@example.com") in values
    assert ("phones", "+919876543210") in values
    assert ("experience.company", "Acme") in values
    assert ("experience.title", "Backend Engineer") in values
    assert ("links.github", "https://github.com/alexchen") in values


def test_parse_recruiter_csv_skips_null_values(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email,phone,current_company,title,github_url\n"
        "Alex Chen,,NULL,Acme,n/a,-\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path)

    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert ("full_name", "Alex Chen") in values
    assert ("experience.company", "Acme") in values

    assert not any(obs.field_path == "emails" for obs in result.observations)
    assert not any(obs.field_path == "phones" for obs in result.observations)
    assert not any(obs.field_path == "experience.title" for obs in result.observations)
    assert not any(obs.field_path == "links.github" for obs in result.observations)


def test_parse_recruiter_csv_invalid_values_become_warnings(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email,phone,github_url\n"
        "Alex Chen,not-an-email,12345,linkedin.com/in/alexchen\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path)

    assert result.errors == []
    assert len(result.warnings) == 3

    assert not any(obs.field_path == "emails" for obs in result.observations)
    assert not any(obs.field_path == "phones" for obs in result.observations)
    assert not any(obs.field_path == "links.github" for obs in result.observations)


def test_messy_fixture_rejects_consecutive_dot_email():
    csv_path = (
        Path(__file__).parents[1]
        / "sample_dataset"
        / "recruiter_export_messy.csv"
    )

    result = parse_recruiter_csv(csv_path, default_phone_region="IN")

    assert not any(
        obs.field_path == "emails"
        and obs.normalized_value == "theo.martin@example..com"
        for obs in result.observations
    )
    assert any(
        "theo.martin@example..com" in warning for warning in result.warnings
    )


def test_parse_recruiter_csv_supports_column_aliases(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "full_name,primary_email,mobile,employer,role,github_profile\n"
        "Alex Chen,alex@example.com,9876543210,Acme,Engineer,https://github.com/alexchen/project\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path, default_phone_region="IN")

    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert ("full_name", "Alex Chen") in values
    assert ("emails", "alex@example.com") in values
    assert ("phones", "+919876543210") in values
    assert ("experience.company", "Acme") in values
    assert ("experience.title", "Engineer") in values
    assert ("links.github", "https://github.com/alexchen") in values


def test_parse_recruiter_csv_directory_path_returns_error(tmp_path):
    csv_dir = tmp_path / "not_a_file"
    csv_dir.mkdir()

    result = parse_recruiter_csv(csv_dir)

    assert result.observations == []
    assert len(result.errors) == 1
    assert "directory" in result.errors[0]


def test_parse_recruiter_csv_missing_file_returns_error(tmp_path):
    csv_path = tmp_path / "missing.csv"

    result = parse_recruiter_csv(csv_path)

    assert result.observations == []
    assert len(result.errors) == 1
    assert "does not exist" in result.errors[0]


def test_parse_recruiter_csv_rejects_local_phone_without_region(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email,phone\nAlex Chen,alex@example.com,6502530000\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path)

    assert not any(obs.field_path == "phones" for obs in result.observations)
    assert len(result.warnings) == 1
    assert "requires an explicit region" in result.warnings[0]


def test_parse_recruiter_csv_uses_explicit_phone_region(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email,phone\nAlex Chen,alex@example.com,6502530000\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path, default_phone_region="US")

    assert ("phones", "+16502530000") in {
        (obs.field_path, obs.normalized_value) for obs in result.observations
    }
    assert result.warnings == []

def test_parse_recruiter_csv_extracts_candidate_ref(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "candidate_ref,name,email\n"
        "C001,Alex Chen,alex@example.com\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path)

    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert ("candidate_ref", "C001") in values
    assert ("full_name", "Alex Chen") in values
    assert ("emails", "alex@example.com") in values


def test_parse_recruiter_csv_extracts_application_time_alias(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "candidate_ref,email,submitted_at\n"
        "C001,alex@example.com,2026-06-30T10:15:00+05:30\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path)
    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert result.warnings == []
    assert ("application.applied_at", "2026-06-30T04:45:00Z") in values


def test_parse_recruiter_csv_invalid_application_time_becomes_warning(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "candidate_ref,email,application_date\n"
        "C001,alex@example.com,not-a-date\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path)

    assert len(result.warnings) == 1
    assert "Invalid application time" in result.warnings[0]
    assert not any(
        obs.field_path == "application.applied_at"
        for obs in result.observations
    )


def test_parse_recruiter_csv_extracts_application_id_alias(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "candidate_ref,application_number,email\n"
        "C001,APP-42,alex@example.com\n",
        encoding="utf-8",
    )

    result = parse_recruiter_csv(csv_path)
    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert ("application.id", "APP-42") in values
