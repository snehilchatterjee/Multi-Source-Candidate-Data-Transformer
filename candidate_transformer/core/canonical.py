from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProvenanceRecord:
    field_path: str
    value: str
    source_type: str
    source_id: str
    locator: str | None
    method: str
    confidence: float


@dataclass(frozen=True)
class CandidateLocation:
    city: str | None = None
    region: str | None = None
    country: str | None = None


@dataclass(frozen=True)
class CandidateLinks:
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalSkill:
    name: str
    confidence: float
    sources: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalEmail:
    value: str
    confidence: float
    sources: tuple[str, ...]
    latest_application_at: str | None = None
    distinct_application_count: int = 0
    corroborating_notes_count: int = 0


@dataclass(frozen=True)
class CanonicalPhone:
    value: str
    confidence: float
    sources: tuple[str, ...]
    latest_application_at: str | None = None
    distinct_application_count: int = 0
    corroborating_notes_count: int = 0


@dataclass(frozen=True)
class CanonicalExperience:
    company: str | None
    title: str | None
    start: str | None = None
    end: str | None = None
    summary: str | None = None
    confidence: float = 0.0
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalEducation:
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    end_year: int | None = None
    confidence: float = 0.0
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalCandidate:
    candidate_id: str
    full_name: str | None
    emails: tuple[str, ...]
    phones: tuple[str, ...]
    links: CandidateLinks
    skills: tuple[CanonicalSkill, ...]
    experience: tuple[CanonicalExperience, ...]
    provenance: tuple[ProvenanceRecord, ...]
    overall_confidence: float

    # Fields required by the assignment's fixed canonical schema.
    # Current MVP adapters may not populate these yet, but the schema should expose them.
    location: CandidateLocation = field(default_factory=CandidateLocation)
    headline: str | None = None
    years_experience: float | None = None
    education: tuple[CanonicalEducation, ...] = ()
    primary_email: str | None = None
    secondary_emails: tuple[str, ...] = ()
    email_details: tuple[CanonicalEmail, ...] = ()
    email_resolution_status: str = "missing"
    email_selection_reason: str | None = None
    email_confidence: float = 0.0
    primary_phone: str | None = None
    secondary_phones: tuple[str, ...] = ()
    phone_details: tuple[CanonicalPhone, ...] = ()
    phone_resolution_status: str = "missing"
    phone_selection_reason: str | None = None
    phone_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
