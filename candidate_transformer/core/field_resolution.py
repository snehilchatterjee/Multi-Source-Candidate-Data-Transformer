from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from candidate_transformer.core.canonical import (
    CandidateLinks,
    CanonicalCandidate,
    CanonicalExperience,
    CanonicalSkill,
    ProvenanceRecord,
)
from candidate_transformer.core.confidence import clamp_confidence
from candidate_transformer.core.entity_resolution import CandidateCluster
from candidate_transformer.core.models import Observation


SOURCE_PRIORITY = {
    "recruiter_csv": 0,
    "ats_json": 1,
    "recruiter_notes": 2,
    "github_profile": 3,
}


def resolve_canonical_candidates(
    clusters: Iterable[CandidateCluster],
) -> list[CanonicalCandidate]:
    return [
        resolve_canonical_candidate(cluster)
        for cluster in sorted(clusters, key=lambda item: item.cluster_id)
    ]


def resolve_canonical_candidate(cluster: CandidateCluster) -> CanonicalCandidate:
    observations = list(cluster.observations)
    provenance: list[ProvenanceRecord] = []

    # Scalar field: choose best observation.
    full_name_obs = _best_observation(_field_observations(observations, "full_name"))
    full_name = _value(full_name_obs) if full_name_obs is not None else None

    if full_name_obs is not None:
        provenance.append(_provenance_from_observation(full_name_obs))

    # Multi-value fields: collect, dedupe, sort.
    email_groups = _group_by_value(_field_observations(observations, "emails"))
    emails = _sorted_group_values(email_groups)
    provenance.extend(_provenance_for_groups(email_groups))

    phone_groups = _group_by_value(_field_observations(observations, "phones"))
    phones = _sorted_group_values(phone_groups)
    provenance.extend(_provenance_for_groups(phone_groups))

    # GitHub: canonical model currently keeps one primary GitHub link.
    github_obs = _best_observation(_field_observations(observations, "links.github"))
    github = _value(github_obs) if github_obs is not None else None

    if github_obs is not None:
        provenance.append(_provenance_from_observation(github_obs))

    skills, skill_provenance = _resolve_skills(observations)
    provenance.extend(skill_provenance)

    experience, experience_provenance = _resolve_experience(observations)
    provenance.extend(experience_provenance)

    overall_confidence = _calculate_overall_confidence(
        full_name_obs=full_name_obs,
        email_groups=email_groups,
        phone_groups=phone_groups,
        github_obs=github_obs,
        skills=skills,
        experience=experience,
    )

    return CanonicalCandidate(
        candidate_id=cluster.cluster_id,
        full_name=full_name,
        emails=emails,
        phones=phones,
        links=CandidateLinks(github=github),
        skills=skills,
        experience=experience,
        provenance=_dedupe_provenance(provenance),
        overall_confidence=overall_confidence,
    )


def _resolve_skills(
    observations: list[Observation],
) -> tuple[tuple[CanonicalSkill, ...], list[ProvenanceRecord]]:
    skill_groups = _group_by_value(_field_observations(observations, "skills"))

    skills: list[CanonicalSkill] = []
    provenance: list[ProvenanceRecord] = []

    for skill_name, skill_observations in skill_groups.items():
        max_confidence = max(obs.confidence for obs in skill_observations)

        distinct_sources = {
            (obs.source.source_type, obs.source.source_id)
            for obs in skill_observations
        }

        corroboration_bonus = 0.05 * max(0, len(distinct_sources) - 1)
        skill_confidence = clamp_confidence(max_confidence + corroboration_bonus)

        source_labels = tuple(
            sorted(
                f"{source_type}:{source_id}"
                for source_type, source_id in distinct_sources
            )
        )

        skills.append(
            CanonicalSkill(
                name=skill_name,
                confidence=skill_confidence,
                sources=source_labels,
            )
        )

        for obs in skill_observations:
            provenance.append(
                _provenance_from_observation(
                    obs,
                    field_path=f"skills[{skill_name}]",
                )
            )

    return (
        tuple(sorted(skills, key=lambda skill: (-skill.confidence, skill.name))),
        provenance,
    )


def _resolve_experience(
    observations: list[Observation],
) -> tuple[tuple[CanonicalExperience, ...], list[ProvenanceRecord]]:
    by_record: dict[str, dict[str, list[Observation]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for obs in observations:
        if obs.field_path == "experience.company":
            by_record[obs.record_id]["company"].append(obs)
        elif obs.field_path == "experience.title":
            by_record[obs.record_id]["title"].append(obs)

    experience_observation_groups: dict[
        tuple[str | None, str | None],
        list[Observation],
    ] = defaultdict(list)

    for record_id in sorted(by_record):
        company_obs = _best_observation(by_record[record_id].get("company", []))
        title_obs = _best_observation(by_record[record_id].get("title", []))

        company = _value(company_obs) if company_obs is not None else None
        title = _value(title_obs) if title_obs is not None else None

        if company is None and title is None:
            continue

        key = (company, title)

        if company_obs is not None:
            experience_observation_groups[key].append(company_obs)

        if title_obs is not None:
            experience_observation_groups[key].append(title_obs)

    experiences: list[CanonicalExperience] = []
    provenance: list[ProvenanceRecord] = []

    for (company, title), group_observations in experience_observation_groups.items():
        confidence = clamp_confidence(
            sum(obs.confidence for obs in group_observations)
            / len(group_observations)
        )

        distinct_sources = {
            (obs.source.source_type, obs.source.source_id)
            for obs in group_observations
        }

        source_labels = tuple(
            sorted(
                f"{source_type}:{source_id}"
                for source_type, source_id in distinct_sources
            )
        )

        experiences.append(
            CanonicalExperience(
                company=company,
                title=title,
                confidence=confidence,
                sources=source_labels,
            )
        )

        for obs in group_observations:
            provenance.append(_provenance_from_observation(obs))

    return (
        tuple(
            sorted(
                experiences,
                key=lambda exp: (
                    -exp.confidence,
                    exp.company or "",
                    exp.title or "",
                ),
            )
        ),
        provenance,
    )


def _field_observations(
    observations: Iterable[Observation],
    field_path: str,
) -> list[Observation]:
    return [obs for obs in observations if obs.field_path == field_path]


def _best_observation(observations: Iterable[Observation]) -> Observation | None:
    candidates = list(observations)

    if not candidates:
        return None

    return sorted(candidates, key=_best_observation_sort_key)[0]


def _best_observation_sort_key(obs: Observation) -> tuple[float, int, int, str, str]:
    value = _value(obs) or ""

    return (
        -obs.confidence,
        -len(value),
        SOURCE_PRIORITY.get(obs.source.source_type, 99),
        value,
        obs.source.locator or "",
    )


def _group_by_value(
    observations: Iterable[Observation],
) -> dict[str, list[Observation]]:
    groups: dict[str, list[Observation]] = defaultdict(list)

    for obs in observations:
        value = _value(obs)

        if value is None:
            continue

        groups[value].append(obs)

    return dict(groups)


def _sorted_group_values(groups: dict[str, list[Observation]]) -> tuple[str, ...]:
    return tuple(
        sorted(
            groups,
            key=lambda value: (
                -max(obs.confidence for obs in groups[value]),
                value,
            ),
        )
    )


def _value(obs: Observation | None) -> str | None:
    if obs is None:
        return None

    if obs.normalized_value is None:
        return None

    value = str(obs.normalized_value).strip()

    if not value:
        return None

    return value


def _provenance_for_groups(
    groups: dict[str, list[Observation]],
) -> list[ProvenanceRecord]:
    records: list[ProvenanceRecord] = []

    for value in sorted(groups):
        for obs in groups[value]:
            records.append(_provenance_from_observation(obs))

    return records


def _provenance_from_observation(
    obs: Observation,
    *,
    field_path: str | None = None,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        field_path=field_path or obs.field_path,
        value=str(obs.normalized_value),
        source_type=obs.source.source_type,
        source_id=obs.source.source_id,
        locator=obs.source.locator,
        method=obs.method,
        confidence=obs.confidence,
    )


def _dedupe_provenance(
    records: Iterable[ProvenanceRecord],
) -> tuple[ProvenanceRecord, ...]:
    seen: set[tuple[str, str, str, str, str | None, str]] = set()
    output: list[ProvenanceRecord] = []

    for record in sorted(
        records,
        key=lambda item: (
            item.field_path,
            item.value,
            item.source_type,
            item.source_id,
            item.locator or "",
            item.method,
        ),
    ):
        key = (
            record.field_path,
            record.value,
            record.source_type,
            record.source_id,
            record.locator,
            record.method,
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(record)

    return tuple(output)


def _calculate_overall_confidence(
    *,
    full_name_obs: Observation | None,
    email_groups: dict[str, list[Observation]],
    phone_groups: dict[str, list[Observation]],
    github_obs: Observation | None,
    skills: tuple[CanonicalSkill, ...],
    experience: tuple[CanonicalExperience, ...],
) -> float:
    """
    Overall confidence combines reliability and completeness.

    Missing important fields contribute 0 for their weight.
    """

    name_confidence = full_name_obs.confidence if full_name_obs is not None else 0.0
    email_confidence = _best_group_confidence(email_groups)
    phone_confidence = _best_group_confidence(phone_groups)
    github_confidence = github_obs.confidence if github_obs is not None else 0.0

    skills_confidence = (
        sum(skill.confidence for skill in skills) / len(skills)
        if skills
        else 0.0
    )

    experience_confidence = (
        sum(exp.confidence for exp in experience) / len(experience)
        if experience
        else 0.0
    )

    score = (
        0.20 * name_confidence
        + 0.25 * email_confidence
        + 0.15 * phone_confidence
        + 0.10 * github_confidence
        + 0.15 * skills_confidence
        + 0.15 * experience_confidence
    )

    return clamp_confidence(score)


def _best_group_confidence(groups: dict[str, list[Observation]]) -> float:
    if not groups:
        return 0.0

    return max(obs.confidence for group in groups.values() for obs in group)