from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

import phonenumbers


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None

    email = value.strip().lower()

    if not email:
        return None

    if not EMAIL_RE.match(email):
        return None

    return email


def normalize_name(value: str | None) -> str | None:
    if value is None:
        return None

    name = " ".join(value.strip().split())

    if not name:
        return None

    return name


def normalize_phone(value: str | None, default_region: str = "IN") -> str | None:
    """
    Normalize Indian phone numbers to E.164.

    Example:
      "9876543210" -> "+919876543210"
      "09876543210" -> "+919876543210"
      "+91 98765 43210" -> "+919876543210"

    default_region is needed for local numbers without country code.
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