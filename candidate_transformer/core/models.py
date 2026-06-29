from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceRef:
    """
    Points back to the exact place where a value came from.

    Examples:
      source_type = "recruiter_csv"
      source_id = "candidates.csv"
      locator = "row=12,column=email"
    """

    source_type: str
    source_id: str
    locator: str | None = None


@dataclass(frozen=True)
class Observation:
    """
    A single extracted claim from one source.

    record_id groups observations that came from the same source record,
    for example the same CSV row.

    This is not yet the final truth. It is evidence.
    """

    record_id: str
    field_path: str
    raw_value: Any
    normalized_value: Any
    source: SourceRef
    method: str
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass
class AdapterResult:
    """
    Standard return type for all source adapters.

    A bad source should usually produce warnings/errors here,
    not crash the whole pipeline.
    """

    observations: list[Observation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)