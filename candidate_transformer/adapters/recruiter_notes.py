from __future__ import annotations

import re
from pathlib import Path

import phonenumbers

from candidate_transformer.core.confidence import confidence_for
from candidate_transformer.core.models import AdapterResult, Observation, SourceRef
from candidate_transformer.core.normalize import (
    SKILL_ALIASES,
    normalize_candidate_ref,
    normalize_email,
    normalize_github_url,
    normalize_skill,
    normalize_url,
)


EMAIL_FIND_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

GITHUB_FIND_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9-]+(?:/[^\s,)]*)?",
    re.IGNORECASE,
)

LINKEDIN_FIND_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_%.-]+"
    r"(?:/[^\s,;)]*)?",
    re.IGNORECASE,
)

URL_VALUE_PATTERN = (
    r"(?:(?:https?://|www\.)[^\s,;<>\[\]{}()]+|"
    r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/[^\s,;<>\[\]{}()]*)?)"
)
LABELED_PROFILE_URL_RE = re.compile(
    rf"\b(?P<label>portfolio(?:\s+(?:url|link))?|website|homepage|"
    rf"personal\s+(?:site|website)|blog|other\s+(?:url|link))"
    rf"\s*[:=-]\s*(?P<url>{URL_VALUE_PATTERN})",
    re.IGNORECASE,
)

CONTEXT_TOKEN_RE = re.compile(
    r"[A-Za-z0-9+#]+(?:\.[A-Za-z0-9+#]+)*(?:['’][A-Za-z]+)?"
)
CLAUSE_BOUNDARY_RE = re.compile(r"[.!?;\r\n]")
NEGATION_WINDOW_TOKENS = 8
NEGATION_CUES = {
    "no",
    "not",
    "never",
    "without",
    "neither",
    "nor",
    "lack",
    "lacks",
    "lacked",
    "lacking",
    "cannot",
    "can't",
    "cant",
    "doesn't",
    "doesnt",
    "didn't",
    "didnt",
    "hasn't",
    "hasnt",
    "haven't",
    "havent",
    "hadn't",
    "hadnt",
    "isn't",
    "isnt",
    "aren't",
    "arent",
    "wasn't",
    "wasnt",
    "weren't",
    "werent",
    "unable",
}
SCOPE_BREAKERS = {"but", "however", "yet", "although", "though", "except"}
PSEUDO_NEGATIONS = {
    ("not", "only"),
    ("not", "just"),
    ("not", "merely"),
    ("not", "bad"),
    ("not", "unfamiliar"),
    ("no", "concern"),
    ("no", "concerns"),
    ("no", "problem"),
    ("no", "problems"),
    ("no", "issue"),
    ("no", "issues"),
}
POST_SKILL_COPULAS = {
    "is",
    "are",
    "was",
    "were",
    "seems",
    "seemed",
    "appears",
    "appeared",
}
POST_SKILL_ATTRIBUTES = {
    "ability",
    "background",
    "experience",
    "expertise",
    "familiarity",
    "knowledge",
    "proficiency",
    "skills",
}

# These are valid skills, but too ambiguous to extract from free text
# without extra context. Example: "go" could be a verb or the Go language.
AMBIGUOUS_FREE_TEXT_SKILLS = {"go"}

LABELED_LOCAL_PHONE_RE = re.compile(
    r"\b(?:phone|mobile|tel(?:ephone)?|contact)\s*[:=-]?\s*"
    r"(?P<number>\d(?:[\s().-]*\d){6,14})",
    re.IGNORECASE,
)


def parse_recruiter_notes_file(
    note_path: str | Path,
    *,
    source_id: str | None = None,
    default_phone_region: str | None = None,
    candidate_ref: str | None = None,
) -> AdapterResult:
    path = Path(note_path)
    # A basename is not unique within one ingestion run (for example,
    # applications/alice/note.txt and applications/bob/note.txt). Since the
    # source ID is also part of the record ID, use the canonical path by
    # default so unrelated files cannot collapse into one source record.
    source_id = source_id or str(path.resolve())

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
        candidate_ref=candidate_ref,
    )


def parse_recruiter_note_text(
    text: str,
    *,
    source_id: str = "inline_note",
    default_phone_region: str | None = None,
    candidate_ref: str | None = None,
) -> AdapterResult:
    result = AdapterResult()
    record_id = f"recruiter_notes:{source_id}"

    _extract_candidate_ref(candidate_ref, source_id, record_id, result)
    _extract_emails(text, source_id, record_id, result)
    _extract_phones(text, source_id, record_id, default_phone_region, result)
    _extract_github_urls(text, source_id, record_id, result)
    _extract_profile_urls(text, source_id, record_id, result)
    _extract_skills(text, source_id, record_id, result)

    return result

def _extract_candidate_ref(
    candidate_ref: str | None,
    source_id: str,
    record_id: str,
    result: AdapterResult,
) -> None:
    normalized = normalize_candidate_ref(candidate_ref)

    if candidate_ref is not None and normalized is None:
        result.warnings.append(
            f"Provided candidate_ref for notes source {source_id!r} is empty"
        )
        return

    if normalized is None:
        return

    result.observations.append(
        Observation(
            record_id=record_id,
            field_path="candidate_ref",
            raw_value=candidate_ref,
            normalized_value=normalized,
            source=SourceRef(
                source_type="ingestion_manifest",
                source_id=source_id,
                locator="candidate_ref",
            ),
            method="provided_candidate_ref -> normalize_candidate_ref",
            confidence=confidence_for(
                "ingestion_manifest",
                "provided_candidate_ref",
            ),
        )
    )


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
    default_phone_region: str | None,
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

    if default_phone_region is None:
        for match in LABELED_LOCAL_PHONE_RE.finditer(text):
            raw_value = match.group("number").strip()
            result.warnings.append(
                "Local phone in notes requires an explicit region at "
                f"chars={match.start('number')}:{match.end('number')}: {raw_value!r}"
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


def _extract_profile_urls(
    text: str,
    source_id: str,
    record_id: str,
    result: AdapterResult,
) -> None:
    """Extract candidate links without treating every URL as a portfolio.

    LinkedIn profile URLs are recognizable from their domain. Other domains
    require an explicit candidate-oriented label so job postings, meeting
    links, and company URLs are not silently classified as personal links.
    """

    seen: dict[str, set[str]] = {
        "links.linkedin": set(),
        "links.portfolio": set(),
        "links.other": set(),
    }

    for match in LINKEDIN_FIND_RE.finditer(text):
        raw_value = _trim_url(match.group(0))
        normalized = normalize_url(raw_value)
        if normalized is None or normalized in seen["links.linkedin"]:
            continue

        seen["links.linkedin"].add(normalized)
        result.observations.append(
            _make_observation(
                record_id=record_id,
                field_path="links.linkedin",
                raw_value=raw_value,
                normalized_value=normalized,
                source_id=source_id,
                span=(match.start(), match.start() + len(raw_value)),
                method="regex_linkedin_profile_url -> normalize_url",
                confidence=confidence_for("recruiter_notes", "regex_url"),
            )
        )

    for match in LABELED_PROFILE_URL_RE.finditer(text):
        raw_value = _trim_url(match.group("url"))
        normalized = normalize_url(raw_value)
        if normalized is None:
            continue

        # Dedicated extractors own these domains, preventing one URL from
        # appearing in both a named field and links.other.
        if normalized.startswith("https://github.com/") or normalized.startswith(
            "https://linkedin.com/in/"
        ):
            continue

        label = " ".join(match.group("label").lower().split())
        field_path = (
            "links.other"
            if label == "blog" or label.startswith("other ")
            else "links.portfolio"
        )
        if normalized in seen[field_path]:
            continue

        seen[field_path].add(normalized)
        result.observations.append(
            _make_observation(
                record_id=record_id,
                field_path=field_path,
                raw_value=raw_value,
                normalized_value=normalized,
                source_id=source_id,
                span=(match.start("url"), match.start("url") + len(raw_value)),
                method=f"labeled_{label.replace(' ', '_')}_url -> normalize_url",
                confidence=confidence_for("recruiter_notes", "regex_url"),
            )
        )


def _trim_url(value: str) -> str:
    return value.rstrip(".,;:!?\"'\u2019]})")


def _extract_skills(
    text: str,
    source_id: str,
    record_id: str,
    result: AdapterResult,
) -> None:
    seen: set[str] = set()
    context_tokens = _tokenize_context(text)

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

            if _is_negated_skill_mention(
                text,
                match_start=match.start(),
                match_end=match.end(),
                tokens=context_tokens,
            ):
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


def _tokenize_context(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group(0).lower().replace("’", "'"), match.start(), match.end())
        for match in CONTEXT_TOKEN_RE.finditer(text)
    ]


def _is_negated_skill_mention(
    text: str,
    *,
    match_start: int,
    match_end: int,
    tokens: list[tuple[str, int, int]],
) -> bool:
    preceding = _context_tokens_before(
        text,
        position=match_start,
        tokens=tokens,
    )
    following = _context_tokens_after(
        text,
        position=match_end,
        tokens=tokens,
    )

    if _contains_effective_negation([token[0] for token in preceding]):
        return True

    return _contains_post_skill_negation(
        text,
        match_end=match_end,
        following=following,
    )


def _context_tokens_before(
    text: str,
    *,
    position: int,
    tokens: list[tuple[str, int, int]],
) -> list[tuple[str, int, int]]:
    context: list[tuple[str, int, int]] = []
    cursor = position

    for token in reversed(tokens):
        value, start, end = token

        if end > position:
            continue

        if CLAUSE_BOUNDARY_RE.search(text[end:cursor]) or value in SCOPE_BREAKERS:
            break

        context.append(token)
        cursor = start

        if len(context) == NEGATION_WINDOW_TOKENS:
            break

    context.reverse()
    return context


def _context_tokens_after(
    text: str,
    *,
    position: int,
    tokens: list[tuple[str, int, int]],
) -> list[tuple[str, int, int]]:
    context: list[tuple[str, int, int]] = []
    cursor = position

    for token in tokens:
        value, start, end = token

        if start < position:
            continue

        if CLAUSE_BOUNDARY_RE.search(text[cursor:start]) or value in SCOPE_BREAKERS:
            break

        context.append(token)
        cursor = end

        if len(context) == NEGATION_WINDOW_TOKENS:
            break

    return context


def _contains_effective_negation(values: list[str]) -> bool:
    for index, value in enumerate(values):
        if value not in NEGATION_CUES:
            continue

        if tuple(values[index : index + 2]) in PSEUDO_NEGATIONS:
            continue

        return True

    return False


def _contains_post_skill_negation(
    text: str,
    *,
    match_end: int,
    following: list[tuple[str, int, int]],
) -> bool:
    values = [token[0] for token in following]

    if not values:
        return False

    if _is_effective_negation_at(values, 0):
        gap = text[match_end : following[0][1]]
        return "," not in gap

    if (
        values[0] in POST_SKILL_COPULAS
        and _is_effective_negation_at(values, 1)
    ):
        return True

    if values[0] in POST_SKILL_ATTRIBUTES:
        if _is_effective_negation_at(values, 1):
            return True

        if (
            len(values) > 1
            and values[1] in POST_SKILL_COPULAS
            and _is_effective_negation_at(values, 2)
        ):
            return True

    return False


def _is_effective_negation_at(values: list[str], index: int) -> bool:
    if index >= len(values) or values[index] not in NEGATION_CUES:
        return False

    return tuple(values[index : index + 2]) not in PSEUDO_NEGATIONS


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
