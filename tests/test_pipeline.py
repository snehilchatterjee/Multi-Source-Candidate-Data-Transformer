from candidate_transformer.pipeline import run_candidate_pipeline


def test_pipeline_csv_and_notes_end_to_end(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email,phone,current_company,title,github_url\n"
        "Alex Chen,alex@example.com,6502530000,Acme,Backend Engineer,github.com/alexchen\n",
        encoding="utf-8",
    )

    note_path = tmp_path / "alex.txt"
    note_path.write_text(
        "Alex is strong in Python and k8s. Reach alex@example.com.",
        encoding="utf-8",
    )

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
                "path": "phone",
                "from": "phones[0]",
                "type": "string",
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
            {
                "path": "companies",
                "from": "experience[].company",
                "type": "string[]",
            },
        ],
        "include_confidence": True,
        "on_missing": "null",
    }

    result = run_candidate_pipeline(
        csv_paths=[csv_path],
        note_paths=[note_path],
        projection_config=config,
    )

    assert result.ok
    assert len(result.observations) > 0
    assert len(result.clusters) == 1
    assert len(result.canonical_candidates) == 1
    assert len(result.projected_outputs) == 1

    candidate = result.canonical_candidates[0]

    assert candidate.full_name == "Alex Chen"
    assert candidate.emails == ("alex@example.com",)
    assert candidate.phones == ("+916502530000",)
    assert candidate.links.github == "https://github.com/alexchen"

    skill_names = [skill.name for skill in candidate.skills]
    assert skill_names == ["Kubernetes", "Python"]

    projected = result.projected_outputs[0]

    assert projected["name"] == "Alex Chen"
    assert projected["email"] == "alex@example.com"
    assert projected["phone"] == "+916502530000"
    assert projected["github"] == "https://github.com/alexchen"
    assert projected["skills"] == skill_names
    assert projected["companies"] == ["Acme"]
    assert "overall_confidence" in projected


def test_pipeline_without_projection_returns_canonical_only(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email,current_company,title\n"
        "Alex Chen,alex@example.com,Acme,Backend Engineer\n",
        encoding="utf-8",
    )

    result = run_candidate_pipeline(csv_paths=[csv_path])

    assert result.ok
    assert len(result.canonical_candidates) == 1
    assert result.projected_outputs is None

    candidate = result.canonical_candidates[0]

    assert candidate.full_name == "Alex Chen"
    assert candidate.emails == ("alex@example.com",)


def test_pipeline_missing_required_projection_field_becomes_error(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email\n"
        "Alex Chen,alex@example.com\n",
        encoding="utf-8",
    )

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

    result = run_candidate_pipeline(
        csv_paths=[csv_path],
        projection_config=config,
    )

    assert not result.ok
    assert len(result.errors) == 1
    assert "Required field" in result.errors[0]
    assert result.projected_outputs == ()

def test_pipeline_uses_candidate_ref_to_join_csv_and_note_without_shared_identifiers(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "candidate_ref,name,email\n"
        "C001,Alex Chen,alex@example.com\n",
        encoding="utf-8",
    )

    note_path = tmp_path / "alex.txt"
    note_path.write_text(
        "Strong in Python and k8s. No email or phone repeated here.",
        encoding="utf-8",
    )

    result = run_candidate_pipeline(
        csv_paths=[csv_path],
        note_paths=[note_path],
        note_candidate_refs={
            str(note_path): "C001",
        },
    )

    assert result.ok
    assert len(result.canonical_candidates) == 1

    candidate = result.canonical_candidates[0]

    assert candidate.full_name == "Alex Chen"
    assert candidate.emails == ("alex@example.com",)

    skill_names = {skill.name for skill in candidate.skills}

    assert skill_names == {"Kubernetes", "Python"}
