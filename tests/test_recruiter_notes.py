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

    result = parse_recruiter_note_text(
        text,
        source_id="alex_note.txt",
        default_phone_region="IN",
    )

    assert result.errors == []

    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert ("emails", "alex.chen@example.com") in values
    assert ("phones", "+917697077601") in values
    assert ("links.github", "https://github.com/alexchen") in values
    assert ("skills", "Python") in values
    assert ("skills", "Kubernetes") in values
    assert ("skills", "Distributed Systems") in values


def test_parse_recruiter_note_warns_for_labeled_local_phone_without_region():
    result = parse_recruiter_note_text("Phone: 6502530000")

    assert not any(obs.field_path == "phones" for obs in result.observations)
    assert len(result.warnings) == 1
    assert "requires an explicit region" in result.warnings[0]


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

def test_parse_recruiter_note_text_accepts_candidate_ref():
    result = parse_recruiter_note_text(
        "Strong in Python and k8s.",
        source_id="alex.txt",
        candidate_ref="C001",
    )

    values = {(obs.field_path, obs.normalized_value) for obs in result.observations}

    assert ("candidate_ref", "C001") in values
    assert ("skills", "Python") in values
    assert ("skills", "Kubernetes") in values


def test_parse_recruiter_note_text_skips_negated_skills():
    result = parse_recruiter_note_text(
        "No production experience with Python. "
        "Not familiar with Kubernetes. "
        "Has never used React."
    )

    skills = {
        obs.normalized_value
        for obs in result.observations
        if obs.field_path == "skills"
    }

    assert skills == set()


def test_parse_recruiter_note_text_handles_negation_contractions():
    result = parse_recruiter_note_text(
        "Isn't familiar with Python. Wasn't trained in React."
    )

    assert not any(obs.field_path == "skills" for obs in result.observations)


def test_parse_recruiter_note_text_limits_negation_to_local_clause():
    result = parse_recruiter_note_text(
        "No Python experience, but strong in JavaScript. "
        "Not sure about the interview. Experienced with Docker."
    )

    skills = {
        obs.normalized_value
        for obs in result.observations
        if obs.field_path == "skills"
    }

    assert skills == {"JavaScript", "Docker"}


def test_parse_recruiter_note_text_handles_post_skill_negation():
    result = parse_recruiter_note_text(
        "Python is not a strength. Kubernetes experience is lacking."
    )

    assert not any(obs.field_path == "skills" for obs in result.observations)


def test_post_skill_negation_does_not_reach_back_across_another_skill():
    result = parse_recruiter_note_text(
        "Python is useful and JavaScript is not a strength."
    )

    skills = {
        obs.normalized_value
        for obs in result.observations
        if obs.field_path == "skills"
    }

    assert skills == {"Python"}


def test_parse_recruiter_note_text_preserves_pseudo_negations():
    result = parse_recruiter_note_text(
        "Not only Python but also React. No concerns with Kubernetes."
    )

    skills = {
        obs.normalized_value
        for obs in result.observations
        if obs.field_path == "skills"
    }

    assert skills == {"Python", "React", "Kubernetes"}


def test_positive_skill_after_negated_mention_is_still_extracted():
    result = parse_recruiter_note_text(
        "No previous Python experience. Now strong in Python."
    )

    python_observations = [
        obs
        for obs in result.observations
        if obs.field_path == "skills" and obs.normalized_value == "Python"
    ]

    assert len(python_observations) == 1
    assert python_observations[0].source.locator == "chars=45:51"
