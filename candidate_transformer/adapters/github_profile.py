from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import requests

from candidate_transformer.core.confidence import confidence_for
from candidate_transformer.core.models import AdapterResult, Observation, SourceRef
from candidate_transformer.core.normalize import (
    normalize_email,
    normalize_github_url,
    normalize_name,
    normalize_skill,
    normalize_url,
)


GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_REPOSITORIES = 100


def fetch_github_profile(
    github_url: str,
    *,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    session: Any | None = None,
) -> AdapterResult:
    """Fetch one public GitHub profile and translate it into observations.

    The normalized profile URL is emitted even when GitHub is unavailable, so
    an optional enrichment failure never discards evidence supplied by the
    caller. Expected HTTP, decoding, and network failures become warnings.
    """

    result = AdapterResult()
    normalized_url = normalize_github_url(github_url)

    if normalized_url is None:
        result.warnings.append(f"Invalid GitHub profile URL: {github_url!r}")
        return result

    username = _username_from_url(normalized_url)
    record_id = f"github_profile:{normalized_url}"
    source_id = normalized_url

    result.observations.append(
        _make_observation(
            record_id=record_id,
            field_path="links.github",
            raw_value=github_url,
            normalized_value=normalized_url,
            source_id=source_id,
            locator="input_url",
            method="github_profile_url -> normalize_github_url",
            confidence=confidence_for("github_profile", "provided_profile_url"),
        )
    )

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "candidate-transformer",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    http = session or requests.Session()
    profile_endpoint = f"{GITHUB_API_BASE}/users/{username}"

    profile = _get_json(
        http,
        profile_endpoint,
        headers=headers,
        timeout=timeout,
        label=f"GitHub profile {username!r}",
        result=result,
    )
    if not isinstance(profile, Mapping):
        if profile is not None:
            result.warnings.append(
                f"GitHub profile {username!r} returned an unexpected JSON shape."
            )
        return result

    repositories_endpoint = f"{profile_endpoint}/repos"
    repositories_payload = _get_json(
        http,
        repositories_endpoint,
        headers=headers,
        params={
            "type": "owner",
            "sort": "full_name",
            "direction": "asc",
            "per_page": MAX_REPOSITORIES,
            "page": 1,
        },
        timeout=timeout,
        label=f"GitHub repositories for {username!r}",
        result=result,
    )
    if isinstance(repositories_payload, list):
        repositories = repositories_payload
    else:
        repositories = []
        if repositories_payload is not None:
            result.warnings.append(
                f"GitHub repositories for {username!r} returned an unexpected JSON shape."
            )

    result.observations.extend(
        observations_from_github_payload(
            normalized_url,
            profile=profile,
            repositories=repositories,
        )
    )

    public_repo_count = profile.get("public_repos")
    if (
        isinstance(public_repo_count, int)
        and not isinstance(public_repo_count, bool)
        and public_repo_count > MAX_REPOSITORIES
    ):
        result.warnings.append(
            f"GitHub profile {username!r} has {public_repo_count} public repositories; "
            f"language evidence is limited to the first {MAX_REPOSITORIES}."
        )

    return result


def observations_from_github_payload(
    github_url: str,
    *,
    profile: Mapping[str, Any],
    repositories: Sequence[Any] = (),
) -> list[Observation]:
    """Convert a captured GitHub API payload into deterministic evidence."""

    normalized_url = normalize_github_url(github_url)
    if normalized_url is None:
        return []

    record_id = f"github_profile:{normalized_url}"
    source_id = normalized_url
    observations: list[Observation] = []

    _append_profile_value(
        observations,
        record_id=record_id,
        source_id=source_id,
        profile=profile,
        api_field="name",
        field_path="full_name",
        normalizer=normalize_name,
        field_kind="api_profile_name",
    )
    _append_profile_value(
        observations,
        record_id=record_id,
        source_id=source_id,
        profile=profile,
        api_field="email",
        field_path="emails",
        normalizer=normalize_email,
        field_kind="api_profile_email",
    )
    _append_profile_value(
        observations,
        record_id=record_id,
        source_id=source_id,
        profile=profile,
        api_field="html_url",
        field_path="links.github",
        normalizer=normalize_github_url,
        field_kind="api_profile_url",
    )
    _append_profile_value(
        observations,
        record_id=record_id,
        source_id=source_id,
        profile=profile,
        api_field="blog",
        field_path="links.portfolio",
        normalizer=normalize_url,
        field_kind="api_profile_blog",
    )
    _append_profile_value(
        observations,
        record_id=record_id,
        source_id=source_id,
        profile=profile,
        api_field="bio",
        field_path="headline",
        normalizer=normalize_name,
        field_kind="api_profile_bio",
    )
    _append_profile_value(
        observations,
        record_id=record_id,
        source_id=source_id,
        profile=profile,
        api_field="company",
        field_path="experience.company",
        normalizer=_normalize_company,
        field_kind="api_profile_company",
    )

    language_repositories: dict[str, list[str]] = {}
    language_counts: Counter[str] = Counter()

    for repository in repositories:
        if not isinstance(repository, Mapping) or repository.get("fork") is True:
            continue

        raw_language = repository.get("language")
        if not isinstance(raw_language, str):
            continue

        language = normalize_skill(raw_language)
        if language is None:
            continue

        repository_name = repository.get("full_name") or repository.get("name")
        repository_label = (
            str(repository_name).strip()
            if repository_name is not None
            else "unknown_repository"
        )
        language_counts[language] += 1
        language_repositories.setdefault(language, []).append(repository_label)

    for language in sorted(language_counts):
        count = language_counts[language]
        repository_names = sorted(set(language_repositories[language]))
        extraction_quality = min(1.0, 0.75 + 0.05 * count)
        observations.append(
            _make_observation(
                record_id=record_id,
                field_path="skills",
                raw_value=language,
                normalized_value=language,
                source_id=source_id,
                locator="repositories:" + ",".join(repository_names),
                method=(
                    "github_repositories[].language -> normalize_skill "
                    f"({count} non-fork repositories)"
                ),
                confidence=confidence_for(
                    "github_profile",
                    "github_repo_language",
                    extraction_quality=extraction_quality,
                ),
            )
        )

    return observations


def _append_profile_value(
    observations: list[Observation],
    *,
    record_id: str,
    source_id: str,
    profile: Mapping[str, Any],
    api_field: str,
    field_path: str,
    normalizer: Any,
    field_kind: str,
) -> None:
    raw_value = profile.get(api_field)
    if not isinstance(raw_value, str):
        return

    normalized_value = normalizer(raw_value)
    if normalized_value is None:
        return

    observations.append(
        _make_observation(
            record_id=record_id,
            field_path=field_path,
            raw_value=raw_value,
            normalized_value=normalized_value,
            source_id=source_id,
            locator=f"GET /users/:username#/{api_field}",
            method=f"github_api:{api_field} -> {normalizer.__name__}",
            confidence=confidence_for("github_profile", field_kind),
        )
    )


def _get_json(
    http: Any,
    url: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
    label: str,
    result: AdapterResult,
    params: Mapping[str, Any] | None = None,
) -> Any | None:
    try:
        response = http.get(
            url,
            headers=dict(headers),
            params=dict(params) if params is not None else None,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        result.warnings.append(f"Could not fetch {label}: {exc}")
        return None

    status_code = getattr(response, "status_code", None)
    if status_code != 200:
        if status_code == 404:
            reason = "profile or resource was not found"
        elif status_code in {403, 429}:
            reason = "request was forbidden or rate-limited"
        else:
            reason = f"unexpected HTTP status {status_code}"
        result.warnings.append(f"Could not fetch {label}: {reason}.")
        return None

    try:
        return response.json()
    except (ValueError, TypeError) as exc:
        result.warnings.append(f"Could not decode {label} response as JSON: {exc}")
        return None


def _username_from_url(github_url: str) -> str:
    return urlparse(github_url).path.strip("/").split("/", 1)[0]


def _normalize_company(value: str | None) -> str | None:
    if value is None:
        return None

    # GitHub commonly displays organizations as "@company".
    return normalize_name(value.removeprefix("@"))


def _make_observation(
    *,
    record_id: str,
    field_path: str,
    raw_value: str,
    normalized_value: str,
    source_id: str,
    locator: str,
    method: str,
    confidence: float,
) -> Observation:
    return Observation(
        record_id=record_id,
        field_path=field_path,
        raw_value=raw_value,
        normalized_value=normalized_value,
        source=SourceRef(
            source_type="github_profile",
            source_id=source_id,
            locator=locator,
        ),
        method=method,
        confidence=confidence,
    )
