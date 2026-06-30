from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import phonenumbers


EMAIL_LOCAL_RE = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~.-]+$")
EMAIL_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
EMAIL_MAX_LENGTH = 254
EMAIL_LOCAL_MAX_LENGTH = 64
EMAIL_DOMAIN_MAX_LENGTH = 253


SKILL_ALIASES = {
    "py": "Python",
    "python": "Python",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "golang": "Go",
    "go": "Go",
    "reactjs": "React",
    "react": "React",
    "nodejs": "Node.js",
    "node": "Node.js",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "distributed systems": "Distributed Systems",
    "docker": "Docker",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "sql": "SQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
}


# Suffix removal deliberately covers only common legal designators. It does
# not contain parent-company or brand aliases: names such as "Alphabet" and
# "Google" must remain distinct unless a caller supplies stronger evidence.
COMPANY_LEGAL_SUFFIX_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r",?\s+private\s+limited\.?$",
        r",?\s+pvt\.?\s+ltd\.?$",
        r",?\s+public\s+limited\s+company\.?$",
        r",?\s+pte\.?\s+ltd\.?$",
        r",?\s+l\.?\s*l\.?\s*c\.?$",
        r",?\s+l\.?\s*l\.?\s*p\.?$",
        r",?\s+p\.?\s*l\.?\s*c\.?$",
        r",?\s+incorporated\.?$",
        r",?\s+corporation\.?$",
        r",?\s+limited\.?$",
        r",?\s+inc\.?$",
        r",?\s+corp\.?$",
        r",?\s+ltd\.?$",
        r",?\s+gmbh\.?$",
        r",?\s+s\.?\s*a\.?$",
        r",?\s+a\.?\s*g\.?$",
    )
)


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None

    email = value.strip().lower()

    if not email:
        return None

    if len(email) > EMAIL_MAX_LENGTH or email.count("@") != 1:
        return None

    local, domain = email.split("@", 1)

    if not local or len(local) > EMAIL_LOCAL_MAX_LENGTH:
        return None

    if (
        not EMAIL_LOCAL_RE.fullmatch(local)
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        return None

    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        return None

    if (
        not ascii_domain
        or len(ascii_domain) > EMAIL_DOMAIN_MAX_LENGTH
        or "." not in ascii_domain
    ):
        return None

    labels = ascii_domain.split(".")
    if any(not EMAIL_DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        return None

    normalized = f"{local}@{ascii_domain}"
    return normalized if len(normalized) <= EMAIL_MAX_LENGTH else None


def normalize_name(value: str | None) -> str | None:
    if value is None:
        return None

    name = " ".join(value.strip().split())

    if not name:
        return None

    return name


def normalize_company(value: str | None) -> str | None:
    """Remove superficial formatting and trailing legal designators.

    This intentionally does not attempt corporate-family resolution. For
    example, ``Google LLC`` normalizes to ``Google`` while ``Alphabet`` stays
    ``Alphabet``.
    """

    normalized = normalize_name(value)
    if normalized is None:
        return None

    normalized = unicodedata.normalize("NFKC", normalized).strip(" ,;:-")
    previous = None
    while normalized and normalized != previous:
        previous = normalized
        for suffix_pattern in COMPANY_LEGAL_SUFFIX_PATTERNS:
            normalized = suffix_pattern.sub("", normalized).strip(" ,;:-")

    return normalized or None


def company_identity_key(value: str | None) -> str | None:
    """Return a case/punctuation-insensitive key for an obvious company alias."""

    normalized = normalize_company(value)
    if normalized is None:
        return None

    key = "".join(
        character if character.isalnum() else " "
        for character in normalized.casefold()
    )
    key = " ".join(key.split())
    return key or None


def title_identity_key(value: str | None) -> str | None:
    """Normalize only superficial title differences; preserve distinct roles."""

    normalized = normalize_name(value)
    if normalized is None:
        return None

    key = "".join(
        character if character.isalnum() else " "
        for character in normalized.casefold()
    )
    key = " ".join(key.split())
    return key or None


def normalize_phone(
    value: str | None,
    default_region: str | None = None,
) -> str | None:
    """
    Normalize phone numbers to E.164.

    Local numbers require an explicitly supplied default_region. International
    numbers beginning with a country code do not.
    """

    if value is None:
        return None

    raw = value.strip()

    if not raw:
        return None

    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None

    if not phonenumbers.is_valid_number(parsed):
        return None

    return phonenumbers.format_number(
        parsed,
        phonenumbers.PhoneNumberFormat.E164,
    )


def normalize_url(value: str | None) -> str | None:
    if value is None:
        return None

    raw = value.strip()

    if not raw:
        return None

    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw

    parsed = urlparse(raw)

    if not parsed.netloc:
        return None

    scheme = "https"
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")

    return urlunparse((scheme, netloc, path, "", "", ""))


def normalize_github_url(value: str | None) -> str | None:
    """
    Normalize GitHub profile URLs.

    Examples:
      "github.com/alexchen" -> "https://github.com/alexchen"
      "https://www.github.com/alexchen/" -> "https://github.com/alexchen"

    If someone passes a repo URL like:
      "https://github.com/alexchen/project"

    MVP behavior:
      return profile URL:
      "https://github.com/alexchen"
    """

    url = normalize_url(value)

    if url is None:
        return None

    parsed = urlparse(url)

    if parsed.netloc != "github.com":
        return None

    parts = [part for part in parsed.path.split("/") if part]

    if not parts:
        return None

    username = parts[0]

    return f"https://github.com/{username}"


def normalize_skill(value: str | None) -> str | None:
    if value is None:
        return None

    raw = " ".join(value.strip().split())

    if not raw:
        return None

    key = raw.lower()

    return SKILL_ALIASES.get(key, raw)

def normalize_candidate_ref(value: str | None) -> str | None:
    """
    Normalize explicit candidate references from source systems or manifests.

    We intentionally do not lowercase because external IDs may be case-sensitive.
    """

    if value is None:
        return None

    ref = str(value).strip()

    if not ref:
        return None

    return ref


def normalize_experience_date(
    value: str | None,
    *,
    allow_present: bool = False,
) -> str | None:
    """Normalize an employment date while preserving its source precision.

    Canonical values use ``YYYY``, ``YYYY-MM``, or ``YYYY-MM-DD``. Common
    unambiguous numeric and month-name forms are accepted. An open-ended role
    may use ``present`` when the caller explicitly permits it (normally only
    for an experience end date).
    """

    if value is None:
        return None

    raw = " ".join(str(value).strip().split())
    if not raw:
        return None

    if allow_present and raw.casefold().rstrip(".") in {
        "current",
        "now",
        "ongoing",
        "present",
    }:
        return "present"

    if re.fullmatch(r"\d{4}", raw):
        year = int(raw)
        return f"{year:04d}" if year > 0 else None

    month_match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})", raw)
    if month_match is not None:
        year, month = map(int, month_match.groups())
        if year > 0 and 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
        return None

    date_match = re.fullmatch(
        r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})",
        raw,
    )
    if date_match is not None:
        year, month, day = map(int, date_match.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None

    compact_format = None
    if re.fullmatch(r"\d{6}", raw):
        compact_format = "%Y%m"
    elif re.fullmatch(r"\d{8}", raw):
        compact_format = "%Y%m%d"

    if compact_format is not None:
        try:
            parsed = datetime.strptime(raw, compact_format)
        except ValueError:
            return None
        return parsed.strftime("%Y-%m" if compact_format == "%Y%m" else "%Y-%m-%d")

    for date_format, output_format in (
        ("%b %Y", "%Y-%m"),
        ("%B %Y", "%Y-%m"),
        ("%Y %b", "%Y-%m"),
        ("%Y %B", "%Y-%m"),
        ("%d %b %Y", "%Y-%m-%d"),
        ("%d %B %Y", "%Y-%m-%d"),
    ):
        try:
            return datetime.strptime(raw, date_format).strftime(output_format)
        except ValueError:
            continue

    return None


def normalize_application_time(value: str | None) -> str | None:
    """Normalize unambiguous application dates/timestamps to UTC ISO-8601."""

    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    normalized_input = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw

    try:
        parsed = datetime.fromisoformat(normalized_input)
    except ValueError:
        parsed = None

    if parsed is None:
        for date_format in ("%Y/%m/%d", "%Y%m%d"):
            try:
                parsed = datetime.strptime(raw, date_format)
                break
            except ValueError:
                continue

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    return parsed.isoformat().replace("+00:00", "Z")
