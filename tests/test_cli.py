import json

from candidate_transformer.cli import main


def test_cli_writes_projected_json(tmp_path):
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

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
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
                        "path": "skills",
                        "from": "skills[].name",
                        "type": "string[]",
                    },
                ],
                "include_confidence": True,
                "on_missing": "null",
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "output.json"

    exit_code = main(
        [
            "--csv",
            str(csv_path),
            "--note",
            str(note_path),
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["kind"] == "projected"
    assert payload["candidate_count"] == 1

    candidate = payload["candidates"][0]

    assert candidate["name"] == "Alex Chen"
    assert candidate["email"] == "alex@example.com"
    assert candidate["skills"] == ["Kubernetes", "Python"]
    assert "overall_confidence" in candidate


def test_cli_writes_canonical_json_without_config(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email,current_company,title\n"
        "Alex Chen,alex@example.com,Acme,Backend Engineer\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "canonical.json"

    exit_code = main(
        [
            "--csv",
            str(csv_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["kind"] == "canonical"
    assert payload["candidate_count"] == 1

    candidate = payload["candidates"][0]

    assert candidate["full_name"] == "Alex Chen"
    assert candidate["emails"] == ["alex@example.com"]
    assert candidate["experience"][0]["company"] == "Acme"
    assert candidate["experience"][0]["title"] == "Backend Engineer"


def test_cli_missing_config_file_returns_error(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email\n"
        "Alex Chen,alex@example.com\n",
        encoding="utf-8",
    )

    missing_config_path = tmp_path / "missing.json"

    exit_code = main(
        [
            "--csv",
            str(csv_path),
            "--config",
            str(missing_config_path),
        ]
    )

    assert exit_code == 1


def test_cli_projection_error_returns_nonzero(tmp_path):
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "name,email\n"
        "Alex Chen,alex@example.com\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "output.json"

    exit_code = main(
        [
            "--csv",
            str(csv_path),
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    assert not output_path.exists()
