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


def test_pipeline_notes_vote_resolves_multiple_csv_application_emails(tmp_path):
    csv_path = tmp_path / "applications.csv"
    csv_path.write_text(
        "candidate_ref,name,email\n"
        "C001,Alex Chen,first@example.com\n"
        "C001,Alex Chen,supported@example.com\n"
        "C001,Alex Chen,third@example.com\n",
        encoding="utf-8",
    )
    note_path = tmp_path / "alex.txt"
    note_path.write_text(
        "Reach Alex at supported@example.com.",
        encoding="utf-8",
    )

    result = run_candidate_pipeline(
        csv_paths=[csv_path],
        note_paths=[note_path],
    )

    assert result.ok
    assert len(result.canonical_candidates) == 1
    candidate = result.canonical_candidates[0]
    assert candidate.primary_email == "supported@example.com"
    assert candidate.secondary_emails == (
        "first@example.com",
        "third@example.com",
    )
    assert candidate.email_details[0].confidence == 0.98


def test_pipeline_notes_vote_resolves_multiple_csv_application_phones(tmp_path):
    csv_path = tmp_path / "applications.csv"
    csv_path.write_text(
        "candidate_ref,application_id,name,phone\n"
        "C001,APP-1,Alex Chen,9876543210\n"
        "C001,APP-2,Alex Chen,9123456789\n"
        "C001,APP-3,Alex Chen,9988776655\n",
        encoding="utf-8",
    )
    note_path = tmp_path / "alex.txt"
    note_path.write_text(
        "Call Alex at +91 91234 56789.",
        encoding="utf-8",
    )

    result = run_candidate_pipeline(
        csv_paths=[csv_path],
        note_paths=[note_path],
        note_candidate_refs={str(note_path): "C001"},
    )

    assert result.ok
    assert len(result.canonical_candidates) == 1
    candidate = result.canonical_candidates[0]
    assert candidate.primary_phone == "+919123456789"
    assert candidate.secondary_phones == (
        "+919876543210",
        "+919988776655",
    )
    assert candidate.phone_confidence == 0.93


def test_pipeline_keeps_same_basename_note_files_as_distinct_records(tmp_path):
    alice_dir = tmp_path / "alice"
    bob_dir = tmp_path / "bob"
    alice_dir.mkdir()
    bob_dir.mkdir()
    alice_note = alice_dir / "note.txt"
    bob_note = bob_dir / "note.txt"
    alice_note.write_text("Contact alice@example.com.", encoding="utf-8")
    bob_note.write_text("Contact bob@example.com.", encoding="utf-8")

    result = run_candidate_pipeline(note_paths=[alice_note, bob_note])

    assert result.ok
    assert len(result.canonical_candidates) == 2
    assert {candidate.emails for candidate in result.canonical_candidates} == {
        ("alice@example.com",),
        ("bob@example.com",),
    }
    assert len({obs.record_id for obs in result.observations}) == 2


def test_pipeline_keeps_same_basename_csv_files_as_distinct_records(tmp_path):
    first_dir = tmp_path / "first_export"
    second_dir = tmp_path / "second_export"
    first_dir.mkdir()
    second_dir.mkdir()
    first_csv = first_dir / "candidates.csv"
    second_csv = second_dir / "candidates.csv"
    first_csv.write_text(
        "name,email\nAlice Example,alice@example.com\n",
        encoding="utf-8",
    )
    second_csv.write_text(
        "name,email\nBob Example,bob@example.com\n",
        encoding="utf-8",
    )

    result = run_candidate_pipeline(csv_paths=[first_csv, second_csv])

    assert result.ok
    assert len(result.canonical_candidates) == 2
    assert {candidate.full_name for candidate in result.canonical_candidates} == {
        "Alice Example",
        "Bob Example",
    }
    assert len({obs.record_id for obs in result.observations}) == 2


def test_pipeline_warns_and_separates_conflicting_candidate_refs(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "candidate_ref,name,email\n"
        "C001,Alice Example,shared@example.com\n"
        "C002,Bob Example,shared@example.com\n",
        encoding="utf-8",
    )

    result = run_candidate_pipeline(csv_paths=[csv_path])

    assert result.ok
    assert len(result.canonical_candidates) == 2
    assert {candidate.full_name for candidate in result.canonical_candidates} == {
        "Alice Example",
        "Bob Example",
    }
    assert any("contradictory candidate_ref" in warning for warning in result.warnings)


def test_pipeline_rejects_malformed_projection_config_without_inputs():
    result = run_candidate_pipeline(
        projection_config={
            "fields": [],
            "on_missing": [],
        }
    )

    assert not result.ok
    assert result.projected_outputs == ()
    assert result.errors == ["config.on_missing must be a string"]
