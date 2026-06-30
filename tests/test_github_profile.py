import requests

from candidate_transformer.adapters.github_profile import fetch_github_profile


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def get(self, url, *, headers, params, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
            }
        )
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


def test_fetch_github_profile_builds_profile_and_language_observations():
    session = FakeSession(
        responses=[
            FakeResponse(
                {
                    "login": "alexchen",
                    "name": "Alex Chen",
                    "email": "ALEX@EXAMPLE.COM",
                    "html_url": "https://github.com/alexchen",
                    "blog": "alex.example.com",
                    "bio": "Backend engineer and distributed systems enthusiast",
                    "company": "@Acme",
                    "public_repos": 4,
                }
            ),
            FakeResponse(
                [
                    {
                        "full_name": "alexchen/api",
                        "language": "Python",
                        "fork": False,
                    },
                    {
                        "full_name": "alexchen/worker",
                        "language": "Python",
                        "fork": False,
                    },
                    {
                        "full_name": "alexchen/web",
                        "language": "TypeScript",
                        "fork": False,
                    },
                    {
                        "full_name": "someone/forked",
                        "language": "Go",
                        "fork": True,
                    },
                ]
            ),
        ]
    )

    result = fetch_github_profile(
        "github.com/alexchen/",
        token="test-token",
        session=session,
    )

    assert result.errors == []
    assert result.warnings == []
    assert len(session.calls) == 2
    assert session.calls[0]["url"].endswith("/users/alexchen")
    assert session.calls[1]["url"].endswith("/users/alexchen/repos")
    assert session.calls[0]["headers"]["Authorization"] == "Bearer test-token"
    assert session.calls[1]["params"]["per_page"] == 100

    values = {
        (observation.field_path, observation.normalized_value)
        for observation in result.observations
    }
    assert ("full_name", "Alex Chen") in values
    assert ("emails", "alex@example.com") in values
    assert ("links.github", "https://github.com/alexchen") in values
    assert ("links.portfolio", "https://alex.example.com") in values
    assert (
        "headline",
        "Backend engineer and distributed systems enthusiast",
    ) in values
    assert ("experience.company", "Acme") in values
    assert ("skills", "Python") in values
    assert ("skills", "TypeScript") in values
    assert ("skills", "Go") not in values

    python_observation = next(
        observation
        for observation in result.observations
        if observation.field_path == "skills"
        and observation.normalized_value == "Python"
    )
    assert "2 non-fork repositories" in python_observation.method
    assert python_observation.source.source_type == "github_profile"


def test_fetch_github_profile_timeout_keeps_url_and_becomes_warning():
    session = FakeSession(error=requests.Timeout("timed out"))

    result = fetch_github_profile(
        "https://github.com/alexchen",
        session=session,
    )

    assert result.errors == []
    assert len(result.warnings) == 1
    assert "timed out" in result.warnings[0]
    assert [observation.field_path for observation in result.observations] == [
        "links.github"
    ]


def test_fetch_github_profile_rate_limit_keeps_url_and_becomes_warning():
    session = FakeSession(responses=[FakeResponse({}, status_code=403)])

    result = fetch_github_profile(
        "https://github.com/alexchen",
        session=session,
    )

    assert result.errors == []
    assert "rate-limited" in result.warnings[0]
    assert len(result.observations) == 1


def test_fetch_github_profile_rejects_invalid_url_without_network_request():
    session = FakeSession()

    result = fetch_github_profile("https://example.com/not-github", session=session)

    assert result.observations == []
    assert result.errors == []
    assert result.warnings == [
        "Invalid GitHub profile URL: 'https://example.com/not-github'"
    ]
    assert session.calls == []


def test_fetch_github_profile_caps_language_evidence_at_first_hundred_repos():
    session = FakeSession(
        responses=[
            FakeResponse(
                {
                    "login": "alexchen",
                    "html_url": "https://github.com/alexchen",
                    "public_repos": 101,
                }
            ),
            FakeResponse([]),
        ]
    )

    result = fetch_github_profile(
        "https://github.com/alexchen",
        session=session,
    )

    assert any("first 100" in warning for warning in result.warnings)
