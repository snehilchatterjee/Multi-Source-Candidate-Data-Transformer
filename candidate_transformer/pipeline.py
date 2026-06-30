from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from candidate_transformer.adapters.recruiter_csv import parse_recruiter_csv
from candidate_transformer.adapters.recruiter_notes import parse_recruiter_notes_file
from candidate_transformer.core.canonical import CanonicalCandidate
from candidate_transformer.core.canonical_schema import validate_canonical_candidate
from candidate_transformer.core.entity_resolution import (
    CandidateCluster,
    resolve_candidate_clusters,
)
from candidate_transformer.core.field_resolution import resolve_canonical_candidates
from candidate_transformer.core.models import Observation
from candidate_transformer.core.projection import (
    project_candidate,
    validate_projection_config,
)


@dataclass
class PipelineResult:
    observations: tuple[Observation, ...] = ()
    clusters: tuple[CandidateCluster, ...] = ()
    canonical_candidates: tuple[CanonicalCandidate, ...] = ()
    projected_outputs: tuple[dict[str, Any], ...] | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_candidate_pipeline(
    *,
    csv_paths: Sequence[str | Path] = (),
    note_paths: Sequence[str | Path] = (),
    note_candidate_refs: Mapping[str | Path, str] | None = None,
    projection_config: Mapping[str, Any] | None = None,
    default_phone_region: str = "IN",
) -> PipelineResult:
    """
    End-to-end pipeline runner.

    This function intentionally stays small:
      1. parse sources into observations
      2. resolve candidate clusters
      3. build canonical candidates
      4. optionally project into caller-requested output shape
    """

    observations: list[Observation] = []
    warnings: list[str] = []
    errors: list[str] = []

    if projection_config is not None:
        config_errors = validate_projection_config(projection_config)
        if config_errors:
            return PipelineResult(
                projected_outputs=(),
                errors=config_errors,
            )

    for csv_path in csv_paths:
        adapter_result = parse_recruiter_csv(
            csv_path,
            default_phone_region=default_phone_region,
        )
        observations.extend(adapter_result.observations)
        warnings.extend(adapter_result.warnings)
        errors.extend(adapter_result.errors)

    normalized_note_candidate_refs = _normalize_note_candidate_refs(note_candidate_refs)
    for note_path in note_paths:
        candidate_ref = _candidate_ref_for_note_path(
            note_path,
            normalized_note_candidate_refs,
        )

        adapter_result = parse_recruiter_notes_file(
            note_path,
            default_phone_region=default_phone_region,
            candidate_ref=candidate_ref,
        )
        observations.extend(adapter_result.observations)
        warnings.extend(adapter_result.warnings)
        errors.extend(adapter_result.errors)

    if not observations:
        warnings.append("No observations were extracted from the provided sources.")
        return PipelineResult(
            observations=(),
            clusters=(),
            canonical_candidates=(),
            projected_outputs=() if projection_config is not None else None,
            warnings=warnings,
            errors=errors,
        )

    clusters = tuple(resolve_candidate_clusters(observations, warnings=warnings))
    resolved_candidates = resolve_canonical_candidates(clusters)
    valid_candidates: list[CanonicalCandidate] = []

    for candidate in resolved_candidates:
        schema_errors = validate_canonical_candidate(candidate)

        if schema_errors:
            errors.extend(
                f"{candidate.candidate_id}: canonical schema validation failed: {error}"
                for error in schema_errors
            )
            continue

        valid_candidates.append(candidate)

    canonical_candidates = tuple(valid_candidates)

    projected_outputs: tuple[dict[str, Any], ...] | None = None

    if projection_config is not None:
        projected: list[dict[str, Any]] = []

        for candidate in canonical_candidates:
            projection_result = project_candidate(candidate, projection_config)

            warnings.extend(
                f"{candidate.candidate_id}: {warning}"
                for warning in projection_result.warnings
            )

            if projection_result.errors:
                errors.extend(
                    f"{candidate.candidate_id}: {error}"
                    for error in projection_result.errors
                )
                continue

            projected.append(projection_result.output)

        projected_outputs = tuple(projected)

    return PipelineResult(
        observations=tuple(observations),
        clusters=clusters,
        canonical_candidates=canonical_candidates,
        projected_outputs=projected_outputs,
        warnings=warnings,
        errors=errors,
    )

def _normalize_note_candidate_refs(
    note_candidate_refs: Mapping[str | Path, str] | None,
) -> dict[str, str]:
    if note_candidate_refs is None:
        return {}

    output: dict[str, str] = {}

    for path_like, candidate_ref in note_candidate_refs.items():
        path = Path(path_like)
        output[str(path)] = candidate_ref
        output[path.name] = candidate_ref

    return output


def _candidate_ref_for_note_path(
    note_path: str | Path,
    note_candidate_refs: Mapping[str, str],
) -> str | None:
    path = Path(note_path)

    return note_candidate_refs.get(str(path)) or note_candidate_refs.get(path.name)
