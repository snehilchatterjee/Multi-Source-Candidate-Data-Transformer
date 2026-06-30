from __future__ import annotations

from dataclasses import asdict, dataclass
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
class CandidateLinks:
    github: str | None = None


@dataclass(frozen=True)
class CanonicalSkill:
    name: str
    confidence: float
    sources: tuple[str, ...]


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)