from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from candidate_transformer.core.canonical import (
    CandidateLinks,
    CandidateLocation,
    CanonicalCandidate,
    CanonicalEducation,
    CanonicalEmail,
    CanonicalExperience,
    CanonicalPhone,
    CanonicalSkill,
    ProvenanceRecord,
)
from candidate_transformer.core.confidence import clamp_confidence
from candidate_transformer.core.entity_resolution import CandidateCluster
from candidate_transformer.core.models import Observation
from candidate_transformer.core.normalize import (
    company_identity_key,
    normalize_company,
    normalize_name,
    title_identity_key,
)


SOURCE_PRIORITY = {
    "recruiter_csv": 0,
    "ats_json": 1,
    "recruiter_notes": 2,
    "github_profile": 3,
}

EMAIL_FIRST_NOTES_CORROBORATION_BONUS = 0.03
EMAIL_ADDITIONAL_NOTES_CORROBORATION_BONUS = 0.01
EMAIL_ADDITIONAL_APPLICATION_BONUS = 0.02
EMAIL_MAX_CORROBORATION_BONUS = 0.05
EMAIL_MAX_RESOLVED_CONFIDENCE = 0.99
EMAIL_STATUS_CONFIDENCE_MULTIPLIER = {
    "resolved": 1.00,
    "ambiguous": 0.50,
    "unstructured_only": 0.75,
    "missing": 0.00,
}
PHONE_FIRST_NOTES_CORROBORATION_BONUS = 0.03
PHONE_ADDITIONAL_NOTES_CORROBORATION_BONUS = 0.01
PHONE_ADDITIONAL_APPLICATION_BONUS = 0.02
PHONE_MAX_CORROBORATION_BONUS = 0.05
PHONE_MAX_RESOLVED_CONFIDENCE = 0.99
PHONE_STATUS_CONFIDENCE_MULTIPLIER = EMAIL_STATUS_CONFIDENCE_MULTIPLIER


@dataclass(frozen=True)
class _EmailCandidate:
    detail: CanonicalEmail
    has_csv_observation: bool
    notes_source_count: int
    application_count: int


@dataclass(frozen=True)
class _EmailResolution:
    groups: dict[str, list[Observation]]
    emails: tuple[str, ...]
    primary_email: str | None
    secondary_emails: tuple[str, ...]
    details: tuple[CanonicalEmail, ...]
    status: str
    selection_reason: str | None
    effective_confidence: float


@dataclass(frozen=True)
class _PhoneCandidate:
    detail: CanonicalPhone
    has_csv_observation: bool
    notes_source_count: int
    application_count: int


@dataclass(frozen=True)
class _PhoneResolution:
    groups: dict[str, list[Observation]]
    phones: tuple[str, ...]
    primary_phone: str | None
    secondary_phones: tuple[str, ...]
    details: tuple[CanonicalPhone, ...]
    status: str
    selection_reason: str | None
    effective_confidence: float


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
    email_resolution = _resolve_emails(observations)
    provenance.extend(_provenance_for_groups(email_resolution.groups))
    provenance.extend(
        _provenance_from_observation(obs)
        for obs in _field_observations(observations, "application.applied_at")
    )
    provenance.extend(
        _provenance_from_observation(obs)
        for obs in _field_observations(observations, "application.id")
    )

    phone_resolution = _resolve_phones(observations)
    provenance.extend(_provenance_for_groups(phone_resolution.groups))

    # Links: named link categories keep one best value; `other` remains a
    # deterministic collection.
    github_obs = _best_observation(_field_observations(observations, "links.github"))
    github = _value(github_obs) if github_obs is not None else None
    if github_obs is not None:
        provenance.append(_provenance_from_observation(github_obs))

    linkedin_obs = _best_observation(
        _field_observations(observations, "links.linkedin")
    )
    linkedin = _value(linkedin_obs) if linkedin_obs is not None else None
    if linkedin_obs is not None:
        provenance.append(_provenance_from_observation(linkedin_obs))

    portfolio_obs = _best_observation(
        _field_observations(observations, "links.portfolio")
    )
    portfolio = _value(portfolio_obs) if portfolio_obs is not None else None
    if portfolio_obs is not None:
        provenance.append(_provenance_from_observation(portfolio_obs))

    other_link_groups = _group_by_value(
        _field_observations(observations, "links.other")
    )
    other_links = _sorted_group_values(other_link_groups)
    provenance.extend(_provenance_for_groups(other_link_groups))

    headline_obs = _best_observation(
        _field_observations(observations, "headline")
    )
    headline = _value(headline_obs) if headline_obs is not None else None
    if headline_obs is not None:
        provenance.append(_provenance_from_observation(headline_obs))

    skills, skill_provenance = _resolve_skills(observations)
    provenance.extend(skill_provenance)

    experience, experience_provenance = _resolve_experience(observations)
    provenance.extend(experience_provenance)

    overall_confidence = _calculate_overall_confidence(
        full_name_obs=full_name_obs,
        email_confidence=email_resolution.effective_confidence,
        phone_confidence=phone_resolution.effective_confidence,
        github_obs=github_obs,
        skills=skills,
        experience=experience,
    )

    return CanonicalCandidate(
        candidate_id=cluster.cluster_id,
        full_name=full_name,
        emails=email_resolution.emails,
        phones=phone_resolution.phones,
        location=CandidateLocation(),
        links=CandidateLinks(
            linkedin=linkedin,
            github=github,
            portfolio=portfolio,
            other=other_links,
        ),
        headline=headline,
        years_experience=None,
        skills=skills,
        experience=experience,
        education=(),
        provenance=_dedupe_provenance(provenance),
        overall_confidence=overall_confidence,
        primary_email=email_resolution.primary_email,
        secondary_emails=email_resolution.secondary_emails,
        email_details=email_resolution.details,
        email_resolution_status=email_resolution.status,
        email_selection_reason=email_resolution.selection_reason,
        email_confidence=email_resolution.effective_confidence,
        primary_phone=phone_resolution.primary_phone,
        secondary_phones=phone_resolution.secondary_phones,
        phone_details=phone_resolution.details,
        phone_resolution_status=phone_resolution.status,
        phone_selection_reason=phone_resolution.selection_reason,
        phone_confidence=phone_resolution.effective_confidence,
    )


def _resolve_emails(observations: list[Observation]) -> _EmailResolution:
    groups = _group_by_value(_field_observations(observations, "emails"))

    if not groups:
        return _EmailResolution(
            groups={},
            emails=(),
            primary_email=None,
            secondary_emails=(),
            details=(),
            status="missing",
            selection_reason=None,
            effective_confidence=0.0,
        )

    record_application_times = _record_application_times(observations)
    record_application_keys = _record_application_keys(
        observations,
        record_application_times,
    )
    candidates: list[_EmailCandidate] = []

    for value, email_observations in groups.items():
        max_confidence = max(obs.confidence for obs in email_observations)
        has_csv_observation = any(
            obs.source.source_type == "recruiter_csv"
            for obs in email_observations
        )
        notes_sources = {
            (obs.source.source_type, obs.source.source_id)
            for obs in email_observations
            if obs.source.source_type == "recruiter_notes"
        }

        application_keys = {
            record_application_keys[obs.record_id]
            for obs in email_observations
            if (
                obs.source.source_type == "recruiter_csv"
                and obs.record_id in record_application_keys
            )
        }

        notes_bonus = 0.0
        if has_csv_observation and notes_sources:
            notes_bonus = EMAIL_FIRST_NOTES_CORROBORATION_BONUS
            notes_bonus += EMAIL_ADDITIONAL_NOTES_CORROBORATION_BONUS * (
                len(notes_sources) - 1
            )

        application_bonus = EMAIL_ADDITIONAL_APPLICATION_BONUS * max(
            0,
            len(application_keys) - 1,
        )
        corroboration_bonus = min(
            notes_bonus + application_bonus,
            EMAIL_MAX_CORROBORATION_BONUS,
        )

        latest_application_at = _latest_csv_application_time(
            email_observations,
            record_application_times,
        )
        sources = tuple(
            sorted(
                {
                    f"{obs.source.source_type}:{obs.source.source_id}"
                    for obs in email_observations
                }
            )
        )

        candidates.append(
            _EmailCandidate(
                detail=CanonicalEmail(
                    value=value,
                    confidence=min(
                        EMAIL_MAX_RESOLVED_CONFIDENCE,
                        clamp_confidence(max_confidence + corroboration_bonus),
                    ),
                    sources=sources,
                    latest_application_at=latest_application_at,
                    distinct_application_count=len(application_keys),
                    corroborating_notes_count=len(notes_sources),
                ),
                has_csv_observation=has_csv_observation,
                notes_source_count=len(notes_sources),
                application_count=len(application_keys),
            )
        )

    ranked = _rank_email_candidates(candidates)
    csv_candidates = [candidate for candidate in ranked if candidate.has_csv_observation]
    primary: _EmailCandidate | None = None
    status = "ambiguous"
    reason: str | None = None

    if not csv_candidates:
        status = "unstructured_only"
        reason = "no_structured_csv_email"
    elif len(csv_candidates) == 1:
        primary = csv_candidates[0]
        status = "resolved"
        reason = (
            "csv_email_corroborated_by_notes"
            if primary.notes_source_count
            else (
                "repeated_distinct_applications"
                if primary.application_count > 1
                else "only_csv_email"
            )
        )
    else:
        contenders = csv_candidates
        recency_is_complete = all(
            candidate.detail.latest_application_at is not None
            for candidate in csv_candidates
        )

        if recency_is_complete:
            latest_application_at = max(
                candidate.detail.latest_application_at or ""
                for candidate in csv_candidates
            )
            latest_candidates = [
                candidate
                for candidate in csv_candidates
                if candidate.detail.latest_application_at == latest_application_at
            ]
            if len(latest_candidates) == 1:
                primary = latest_candidates[0]
                status = "resolved"
                reason = "latest_csv_application"
            else:
                contenders = latest_candidates

        if primary is None:
            highest_confidence = max(
                candidate.detail.confidence for candidate in contenders
            )
            highest_candidates = [
                candidate
                for candidate in contenders
                if candidate.detail.confidence == highest_confidence
            ]
            if len(highest_candidates) == 1:
                primary = highest_candidates[0]
                status = "resolved"
                reason = (
                    "csv_email_corroborated_by_notes"
                    if primary.notes_source_count
                    else (
                        "repeated_distinct_applications"
                        if primary.application_count > 1
                        else "highest_email_confidence"
                    )
                )
            else:
                status = "ambiguous"
                reason = "equal_csv_email_evidence"

    if primary is not None:
        ranked = [primary] + [candidate for candidate in ranked if candidate != primary]

    emails = tuple(candidate.detail.value for candidate in ranked)
    primary_email = primary.detail.value if primary is not None else None
    secondary_emails = tuple(email for email in emails if email != primary_email)

    strongest_confidence = max(
        candidate.detail.confidence for candidate in candidates
    )
    selected_confidence = (
        primary.detail.confidence if primary is not None else strongest_confidence
    )
    effective_confidence = clamp_confidence(
        selected_confidence * EMAIL_STATUS_CONFIDENCE_MULTIPLIER[status]
    )

    return _EmailResolution(
        groups=groups,
        emails=emails,
        primary_email=primary_email,
        secondary_emails=secondary_emails,
        details=tuple(candidate.detail for candidate in ranked),
        status=status,
        selection_reason=reason,
        effective_confidence=effective_confidence,
    )


def _resolve_phones(observations: list[Observation]) -> _PhoneResolution:
    groups = _group_by_value(_field_observations(observations, "phones"))

    if not groups:
        return _PhoneResolution(
            groups={},
            phones=(),
            primary_phone=None,
            secondary_phones=(),
            details=(),
            status="missing",
            selection_reason=None,
            effective_confidence=0.0,
        )

    record_application_times = _record_application_times(observations)
    record_application_keys = _record_application_keys(
        observations,
        record_application_times,
    )
    candidates: list[_PhoneCandidate] = []

    for value, phone_observations in groups.items():
        max_confidence = max(obs.confidence for obs in phone_observations)
        has_csv_observation = any(
            obs.source.source_type == "recruiter_csv"
            for obs in phone_observations
        )
        notes_sources = {
            (obs.source.source_type, obs.source.source_id)
            for obs in phone_observations
            if obs.source.source_type == "recruiter_notes"
        }
        application_keys = {
            record_application_keys[obs.record_id]
            for obs in phone_observations
            if (
                obs.source.source_type == "recruiter_csv"
                and obs.record_id in record_application_keys
            )
        }

        notes_bonus = 0.0
        if has_csv_observation and notes_sources:
            notes_bonus = PHONE_FIRST_NOTES_CORROBORATION_BONUS
            notes_bonus += PHONE_ADDITIONAL_NOTES_CORROBORATION_BONUS * (
                len(notes_sources) - 1
            )

        application_bonus = PHONE_ADDITIONAL_APPLICATION_BONUS * max(
            0,
            len(application_keys) - 1,
        )
        corroboration_bonus = min(
            notes_bonus + application_bonus,
            PHONE_MAX_CORROBORATION_BONUS,
        )
        latest_application_at = _latest_csv_application_time(
            phone_observations,
            record_application_times,
        )
        sources = tuple(
            sorted(
                {
                    f"{obs.source.source_type}:{obs.source.source_id}"
                    for obs in phone_observations
                }
            )
        )

        candidates.append(
            _PhoneCandidate(
                detail=CanonicalPhone(
                    value=value,
                    confidence=min(
                        PHONE_MAX_RESOLVED_CONFIDENCE,
                        clamp_confidence(max_confidence + corroboration_bonus),
                    ),
                    sources=sources,
                    latest_application_at=latest_application_at,
                    distinct_application_count=len(application_keys),
                    corroborating_notes_count=len(notes_sources),
                ),
                has_csv_observation=has_csv_observation,
                notes_source_count=len(notes_sources),
                application_count=len(application_keys),
            )
        )

    ranked = _rank_phone_candidates(candidates)
    csv_candidates = [candidate for candidate in ranked if candidate.has_csv_observation]
    primary: _PhoneCandidate | None = None
    status = "ambiguous"
    reason: str | None = None

    if not csv_candidates:
        status = "unstructured_only"
        reason = "no_structured_csv_phone"
    elif len(csv_candidates) == 1:
        primary = csv_candidates[0]
        status = "resolved"
        reason = (
            "csv_phone_corroborated_by_notes"
            if primary.notes_source_count
            else (
                "repeated_distinct_applications"
                if primary.application_count > 1
                else "only_csv_phone"
            )
        )
    else:
        contenders = csv_candidates
        recency_is_complete = all(
            candidate.detail.latest_application_at is not None
            for candidate in csv_candidates
        )

        if recency_is_complete:
            latest_application_at = max(
                candidate.detail.latest_application_at or ""
                for candidate in csv_candidates
            )
            latest_candidates = [
                candidate
                for candidate in csv_candidates
                if candidate.detail.latest_application_at == latest_application_at
            ]
            if len(latest_candidates) == 1:
                primary = latest_candidates[0]
                status = "resolved"
                reason = "latest_csv_application"
            else:
                contenders = latest_candidates

        if primary is None:
            highest_confidence = max(
                candidate.detail.confidence for candidate in contenders
            )
            highest_candidates = [
                candidate
                for candidate in contenders
                if candidate.detail.confidence == highest_confidence
            ]
            if len(highest_candidates) == 1:
                primary = highest_candidates[0]
                status = "resolved"
                reason = (
                    "csv_phone_corroborated_by_notes"
                    if primary.notes_source_count
                    else (
                        "repeated_distinct_applications"
                        if primary.application_count > 1
                        else "highest_phone_confidence"
                    )
                )
            else:
                status = "ambiguous"
                reason = "equal_csv_phone_evidence"

    if primary is not None:
        ranked = [primary] + [candidate for candidate in ranked if candidate != primary]

    phones = tuple(candidate.detail.value for candidate in ranked)
    primary_phone = primary.detail.value if primary is not None else None
    secondary_phones = tuple(phone for phone in phones if phone != primary_phone)
    strongest_confidence = max(
        candidate.detail.confidence for candidate in candidates
    )
    selected_confidence = (
        primary.detail.confidence if primary is not None else strongest_confidence
    )
    effective_confidence = clamp_confidence(
        selected_confidence * PHONE_STATUS_CONFIDENCE_MULTIPLIER[status]
    )

    return _PhoneResolution(
        groups=groups,
        phones=phones,
        primary_phone=primary_phone,
        secondary_phones=secondary_phones,
        details=tuple(candidate.detail for candidate in ranked),
        status=status,
        selection_reason=reason,
        effective_confidence=effective_confidence,
    )


def _record_application_times(observations: list[Observation]) -> dict[str, str]:
    by_record: dict[str, list[str]] = defaultdict(list)

    for obs in observations:
        if obs.field_path != "application.applied_at":
            continue
        value = _value(obs)
        if value is not None:
            by_record[obs.record_id].append(value)

    return {
        record_id: max(application_times)
        for record_id, application_times in by_record.items()
    }


def _record_application_keys(
    observations: list[Observation],
    record_application_times: dict[str, str],
) -> dict[str, str]:
    application_ids: dict[str, list[str]] = defaultdict(list)

    for obs in observations:
        if obs.field_path != "application.id":
            continue
        value = _value(obs)
        if value is not None:
            application_ids[obs.record_id].append(value)

    record_ids = {
        obs.record_id
        for obs in observations
        if obs.source.source_type == "recruiter_csv"
    }
    output: dict[str, str] = {}

    for record_id in record_ids:
        if application_ids.get(record_id):
            output[record_id] = f"id:{min(application_ids[record_id])}"
        elif record_id in record_application_times:
            output[record_id] = f"time:{record_application_times[record_id]}"

    return output


def _latest_csv_application_time(
    email_observations: list[Observation],
    record_application_times: dict[str, str],
) -> str | None:
    application_times = [
        record_application_times[obs.record_id]
        for obs in email_observations
        if (
            obs.source.source_type == "recruiter_csv"
            and obs.record_id in record_application_times
        )
    ]
    return max(application_times) if application_times else None


def _rank_email_candidates(
    candidates: list[_EmailCandidate],
) -> list[_EmailCandidate]:
    # Stable sorts produce confidence desc, application time desc, value asc.
    ranked = sorted(candidates, key=lambda candidate: candidate.detail.value)
    ranked.sort(
        key=lambda candidate: candidate.detail.latest_application_at or "",
        reverse=True,
    )
    ranked.sort(key=lambda candidate: candidate.detail.confidence, reverse=True)
    return ranked


def _rank_phone_candidates(
    candidates: list[_PhoneCandidate],
) -> list[_PhoneCandidate]:
    # Stable sorts produce confidence desc, application time desc, value asc.
    ranked = sorted(candidates, key=lambda candidate: candidate.detail.value)
    ranked.sort(
        key=lambda candidate: candidate.detail.latest_application_at or "",
        reverse=True,
    )
    ranked.sort(key=lambda candidate: candidate.detail.confidence, reverse=True)
    return ranked


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
        elif obs.field_path == "experience.start":
            by_record[obs.record_id]["start"].append(obs)
        elif obs.field_path == "experience.end":
            by_record[obs.record_id]["end"].append(obs)

    experience_observation_groups: dict[
        tuple[str, str, str | None, str | None],
        dict[str, list[Observation]],
    ] = defaultdict(lambda: defaultdict(list))

    for record_id in sorted(by_record):
        company_obs = _best_observation(by_record[record_id].get("company", []))
        title_obs = _best_observation(by_record[record_id].get("title", []))
        start_obs = _best_observation(by_record[record_id].get("start", []))
        end_obs = _best_observation(by_record[record_id].get("end", []))

        company = _value(company_obs) if company_obs is not None else None
        title = _value(title_obs) if title_obs is not None else None
        start = _value(start_obs) if start_obs is not None else None
        end = _value(end_obs) if end_obs is not None else None

        if company is None and title is None:
            continue

        # Organization equivalence is deliberately narrow: case, punctuation,
        # whitespace, and trailing legal suffixes. Different base names (for
        # example Google and Alphabet) never merge here, even if their dates
        # happen to overlap.
        company_key = company_identity_key(company)
        title_key = title_identity_key(title)
        key = (
            company_key or f"missing-company:{record_id}",
            title_key or f"missing-title:{record_id}",
            start.casefold() if start else None,
            end.casefold() if end else None,
        )

        if company_obs is not None:
            experience_observation_groups[key]["company"].append(company_obs)

        if title_obs is not None:
            experience_observation_groups[key]["title"].append(title_obs)

        if start_obs is not None:
            experience_observation_groups[key]["start"].append(start_obs)

        if end_obs is not None:
            experience_observation_groups[key]["end"].append(end_obs)

    experiences: list[CanonicalExperience] = []
    provenance: list[ProvenanceRecord] = []

    for field_groups in experience_observation_groups.values():
        company_observations = field_groups.get("company", [])
        title_observations = field_groups.get("title", [])
        start_observations = field_groups.get("start", [])
        end_observations = field_groups.get("end", [])
        group_observations = [
            *company_observations,
            *title_observations,
            *start_observations,
            *end_observations,
        ]

        company_obs = _best_company_observation(company_observations)
        title_obs = _best_observation(title_observations)
        start_obs = _best_observation(start_observations)
        end_obs = _best_observation(end_observations)
        company = normalize_company(_value(company_obs))
        title = normalize_name(_value(title_obs))
        start = _value(start_obs)
        end = _value(end_obs)

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
                start=start,
                end=end,
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


def _best_company_observation(
    observations: Iterable[Observation],
) -> Observation | None:
    candidates = list(observations)
    if not candidates:
        return None

    def sort_key(obs: Observation) -> tuple[float, int, int, str, str]:
        value = normalize_company(_value(obs)) or ""
        if value.isupper() or value.islower():
            casing_penalty = 1
        else:
            casing_penalty = 0
        return (
            -obs.confidence,
            casing_penalty,
            SOURCE_PRIORITY.get(obs.source.source_type, 99),
            value.casefold(),
            obs.source.locator or "",
        )

    return sorted(candidates, key=sort_key)[0]


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
    email_confidence: float,
    phone_confidence: float,
    github_obs: Observation | None,
    skills: tuple[CanonicalSkill, ...],
    experience: tuple[CanonicalExperience, ...],
) -> float:
    """
    Overall confidence combines reliability and completeness.

    Missing important fields contribute 0 for their weight.
    """

    name_confidence = full_name_obs.confidence if full_name_obs is not None else 0.0
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
