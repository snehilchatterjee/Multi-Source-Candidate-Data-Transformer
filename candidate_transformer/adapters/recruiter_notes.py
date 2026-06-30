from __future__ import annotations

import re
from pathlib import Path

import phonenumbers

from candidate_transformer.core.confidence import confidence_for
from candidate_transformer.core.models import AdapterResult, Observation, SourceRef
from candidate_transformer.core.normalize import (
    SKILL_ALIASES,
    normalize_email,
    normalize_github_url,
    normalize_skill,
)


EMAIL_FIND_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

GITHUB_FIND_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9-]+(?:/[^\s,)]*)?",
    re.IGNORECASE,
)

# These are valid skills, but too ambiguous to extract from free text
# without extra context. Example: "go" could be a verb or the Go language.
AMBIGUOUS_FREE_TEXT_SKILLS = {"go"}


def parse_recruiter_notes_file(
    note_path: str | Path,
    *,
    source_id: str | None = None,
    default_phone_region: str = "IN",
) -> AdapterResult:
    path = Path(note_path)
    source_id = source_id or path.name

    result = AdapterResult()

    try:
        if not path.exists():
            result.errors.append(f"Notes file does not exist: {path}")
            return result

        if path.is_dir():
            result.errors.append(f"Notes path is a directory, not a file: {path}")
            return result

        text = path.read_text(encoding="utf-8")

    except UnicodeDecodeError as exc:
        result.errors.append(f"Could not decode notes file {path}: {exc}")
        return result
    except OSError as exc:
        result.errors.append(f"Could not read notes file {path}: {exc}")
        return result

    if not text.strip():
        result.warnings.append(f"Notes file is empty: {path}")
        return result

    return parse_recruiter_note_text(
        text,
        source_id=source_id,
        default_phone_region=default_phone_region,
    )


def parse_recruiter_note_text(
    text: str,
    *,
    source_id: str = "inline_note",
    default_phone_region: str = "IN",
) -> AdapterResult:
    result = AdapterResult()
    record_id = f"recruiter_notes:{source_id}"

    _extract_emails(text, source_id, record_id, result)
    _extract_phones(text, source_id, record_id, default_phone_region, result)
    _extract_github_urls(text, source_id, record_id, result)
    _extract_skills(text, source_id, record_id, result)

    return result


def _extract_emails(
    text: str,
    source_id: str,
    record_id: str,
    result: AdapterResult,
) -> None:
    seen: set[str] = set()

    for match in EMAIL_FIND_RE.finditer(text):
        raw_value = match.group(0)
        normalized = normalize_email(raw_value)

        if normalized is None:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)

        result.observations.append(
            _make_observation(
                record_id=record_id,
                field_path="emails",
                raw_value=raw_value,
                normalized_value=normalized,
                source_id=source_id,
                span=(match.start(), match.end()),
                method="regex_email -> normalize_email",
                confidence=confidence_for("recruiter_notes", "regex_email"),
            )
        )


def _extract_phones(
    text: str,
    source_id: str,
    record_id: str,
    default_phone_region: str,
    result: AdapterResult,
) -> None:
    seen: set[str] = set()

    for match in phonenumbers.PhoneNumberMatcher(text, default_phone_region):
        raw_value = match.raw_string
        normalized = phonenumbers.format_number(
            match.number,
            phonenumbers.PhoneNumberFormat.E164,
        )

        if normalized in seen:
            continue

        seen.add(normalized)

        result.observations.append(
            _make_observation(
                record_id=record_id,
                field_path="phones",
                raw_value=raw_value,
                normalized_value=normalized,
                source_id=source_id,
                span=(match.start, match.end),
                method="phonenumbers_matcher -> normalize_phone",
                confidence=confidence_for("recruiter_notes", "regex_phone"),
            )
        )


def _extract_github_urls(
    text: str,
    source_id: str,
    record_id: str,
    result: AdapterResult,
) -> None:
    seen: set[str] = set()

    for match in GITHUB_FIND_RE.finditer(text):
        raw_value = match.group(0).rstrip(".,;:]})")
        normalized = normalize_github_url(raw_value)

        if normalized is None:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)

        result.observations.append(
            _make_observation(
                record_id=record_id,
                field_path="links.github",
                raw_value=raw_value,
                normalized_value=normalized,
                source_id=source_id,
                span=(match.start(), match.start() + len(raw_value)),
                method="regex_github_url -> normalize_github_url",
                confidence=confidence_for("recruiter_notes", "regex_url"),
            )
        )


def _extract_skills(
    text: str,
    source_id: str,
    record_id: str,
    result: AdapterResult,
) -> None:
    seen: set[str] = set()

    aliases = sorted(SKILL_ALIASES.keys(), key=len, reverse=True)

    for alias in aliases:
        if alias in AMBIGUOUS_FREE_TEXT_SKILLS:
            continue

        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            re.IGNORECASE,
        )

        for match in pattern.finditer(text):
            raw_value = match.group(0)
            normalized = normalize_skill(raw_value)

            if normalized is None:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)

            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="skills",
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_id=source_id,
                    span=(match.start(), match.end()),
                    method="skill_dictionary_match -> normalize_skill",
                    confidence=confidence_for(
                        "recruiter_notes",
                        "skill_dictionary_match",
                    ),
                )
            )


def _make_observation(
    *,
    record_id: str,
    field_path: str,
    raw_value: str,
    normalized_value: str,
    source_id: str,
    span: tuple[int, int],
    method: str,
    confidence: float,
) -> Observation:
    start, end = span

    return Observation(
        record_id=record_id,
        field_path=field_path,
        raw_value=raw_value,
        normalized_value=normalized_value,
        source=SourceRef(
            source_type="recruiter_notes",
            source_id=source_id,
            locator=f"chars={start}:{end}",
        ),
        method=method,
        confidence=confidence,
    )
