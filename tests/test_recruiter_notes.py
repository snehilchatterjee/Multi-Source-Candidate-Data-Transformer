from candidate_transformer.adapters.recruiter_notes import (
    parse_recruiter_note_text,
    parse_recruiter_notes_file,
)


def test_parse_recruiter_note_text_basic():
    text = """
    Alex is strong in Python, k8s, and distributed systems.
    Email alex.chen@example.com.
    Phone: 7697077601.
    GitHub: github.com/alexchen.
    """

    result = parse_recruiter_note_text(text, source_id="alex_note.txt")

    assert result.errors == []

    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert ("emails", "alex.chen@example.com") in values
    assert ("phones", "+917697077601") in values
    assert ("links.github", "https://github.com/alexchen") in values
    assert ("skills", "Python") in values
    assert ("skills", "Kubernetes") in values
    assert ("skills", "Distributed Systems") in values


def test_parse_recruiter_note_text_deduplicates_repeated_skills():
    text = "Python python py k8s Kubernetes"

    result = parse_recruiter_note_text(text)

    python_observations = [
        obs
        for obs in result.observations
        if obs.field_path == "skills" and obs.normalized_value == "Python"
    ]

    kubernetes_observations = [
        obs
        for obs in result.observations
        if obs.field_path == "skills" and obs.normalized_value == "Kubernetes"
    ]

    assert len(python_observations) == 1
    assert len(kubernetes_observations) == 1


def test_parse_recruiter_note_text_does_not_extract_ambiguous_go():
    text = "Alex can go onsite next week."

    result = parse_recruiter_note_text(text)

    assert not any(
        obs.field_path == "skills" and obs.normalized_value == "Go"
        for obs in result.observations
    )


def test_parse_recruiter_notes_file_empty_file(tmp_path):
    note_path = tmp_path / "empty.txt"
    note_path.write_text("   ", encoding="utf-8")

    result = parse_recruiter_notes_file(note_path)

    assert result.errors == []
    assert len(result.warnings) == 1
    assert result.observations == []


def test_parse_recruiter_notes_file_missing_file(tmp_path):
    note_path = tmp_path / "missing.txt"

    result = parse_recruiter_notes_file(note_path)

    assert len(result.errors) == 1
    assert result.observations == []

def test_parse_recruiter_notes_file_directory_path_returns_error(tmp_path):
    notes_dir = tmp_path / "not_a_file"
    notes_dir.mkdir()

    result = parse_recruiter_notes_file(notes_dir)

    assert result.observations == []
    assert len(result.errors) == 1
    assert "directory" in result.errors[0]