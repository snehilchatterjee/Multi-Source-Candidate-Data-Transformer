
from __future__ import annotations

import csv
import re
from pathlib import Path

from candidate_transformer.core.models import AdapterResult, Observation, SourceRef
from candidate_transformer.core.normalize import (
    normalize_application_time,
    normalize_candidate_ref,
    normalize_company,
    normalize_email,
    normalize_github_url,
    normalize_name,
    normalize_phone,
)
from candidate_transformer.core.confidence import confidence_for


NULL_LIKE_VALUES = {"", "null", "none", "n/a", "na", "-"}


COLUMN_ALIASES = {
    "candidate_ref": [
        "candidate_ref",
        "candidate_id",
        "external_id",
        "applicant_id",
        "profile_id",
    ],
    "full_name": ["name", "full_name", "candidate_name"],
    "emails": ["email", "emails", "primary_email"],
    "phones": ["phone", "phones", "mobile", "phone_number"],
    "experience.company": ["current_company", "company", "employer"],
    "experience.title": ["title", "current_title", "job_title", "role"],
    "links.github": ["github", "github_url", "github_profile"],
    "application.applied_at": [
        "applied_at",
        "application_date",
        "applied_date",
        "submitted_at",
        "submission_date",
        "application_timestamp",
        "created_at",
    ],
    "application.id": [
        "application_id",
        "application_ref",
        "submission_id",
        "application_number",
    ],
}


def parse_recruiter_csv(
    csv_path: str | Path,
    *,
    source_id: str | None = None,
    default_phone_region: str | None = None,
) -> AdapterResult:
    """
    Parse a recruiter CSV export into observations.

    This does not deduplicate candidates yet.
    It only turns each non-empty cell into evidence.

    Filesystem failures are reported as adapter errors instead of escaping.
    """

    path = Path(csv_path)
    # A basename is not unique within one ingestion run. The source ID feeds
    # every CSV row's record ID, so default to the canonical path to prevent
    # same-named files in different directories from sharing record IDs.
    source_id = source_id or str(path.resolve())
    result = AdapterResult()

    try:
        if not path.exists():
            result.errors.append(f"CSV file does not exist: {path}")
            return result

        if path.is_dir():
            result.errors.append(f"CSV path is a directory, not a file: {path}")
            return result

        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            if not reader.fieldnames:
                result.warnings.append(f"CSV file has no header row: {path}")
                return result

            header_lookup = _build_header_lookup(reader.fieldnames)

            for row_number, row in enumerate(reader, start=2):
                record_id = f"recruiter_csv:{source_id}:row={row_number}"
                _parse_row(
                    row=row,
                    row_number=row_number,
                    record_id=record_id,
                    source_id=source_id,
                    header_lookup=header_lookup,
                    default_phone_region=default_phone_region,
                    result=result,
                )

    except csv.Error as exc:
        result.errors.append(f"Could not parse CSV file {path}: {exc}")
    except UnicodeDecodeError as exc:
        result.errors.append(f"Could not decode CSV file {path}: {exc}")
    except OSError as exc:
        result.errors.append(f"Could not read CSV file {path}: {exc}")

    return result


def _parse_row(
    *,
    row: dict[str, str],
    row_number: int,
    record_id: str,
    source_id: str,
    header_lookup: dict[str, str],
    default_phone_region: str | None,
    result: AdapterResult,
) -> None:
    # candidate_ref
    candidate_ref_cell = _get_cell(row, header_lookup, COLUMN_ALIASES["candidate_ref"])
    if candidate_ref_cell is not None:
        raw_value, column = candidate_ref_cell
        normalized = normalize_candidate_ref(raw_value)

        if normalized is not None:
            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="candidate_ref",
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_candidate_ref",
                    confidence=confidence_for(
                        "recruiter_csv",
                        "explicit_candidate_ref",
                    ),
                )
            )

    # full_name
    name_cell = _get_cell(row, header_lookup, COLUMN_ALIASES["full_name"])
    if name_cell is not None:
        raw_value, column = name_cell
        normalized = normalize_name(raw_value)
        if normalized is not None:
            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="full_name",
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_name",
                    confidence=confidence_for("recruiter_csv", "explicit_name"), # could be recruiter typed or wrong name
                )
            )

    # emails
    email_cell = _get_cell(row, header_lookup, COLUMN_ALIASES["emails"])
    if email_cell is not None:
        raw_value, column = email_cell
        for raw_email in _split_multi_value(raw_value):
            normalized = normalize_email(raw_email)
            if normalized is None:
                result.warnings.append(
                    f"Invalid email at row={row_number}, column={column}: {raw_email!r}"
                )
                continue

            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="emails",
                    raw_value=raw_email,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_email",
                    confidence=confidence_for("recruiter_csv", "explicit_email"), # could be recruiter typed or wrong email
                )
            )

    # Application identity/time are evidence used to distinguish repeated
    # applications and resolve competing CSV emails. They are not candidate
    # profile fields.
    application_ref_cell = _get_cell(
        row,
        header_lookup,
        COLUMN_ALIASES["application.id"],
    )
    if application_ref_cell is not None:
        raw_value, column = application_ref_cell
        normalized = normalize_candidate_ref(raw_value)
        if normalized is not None:
            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="application.id",
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_application_ref",
                    confidence=confidence_for(
                        "recruiter_csv",
                        "explicit_application_ref",
                    ),
                )
            )

    application_time_cell = _get_cell(
        row,
        header_lookup,
        COLUMN_ALIASES["application.applied_at"],
    )
    if application_time_cell is not None:
        raw_value, column = application_time_cell
        normalized = normalize_application_time(raw_value)
        if normalized is None:
            result.warnings.append(
                f"Invalid application time at row={row_number}, "
                f"column={column}: {raw_value!r}"
            )
        else:
            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="application.applied_at",
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_application_time",
                    confidence=confidence_for(
                        "recruiter_csv",
                        "explicit_application_time",
                    ),
                )
            )

    # phones
    phone_cell = _get_cell(row, header_lookup, COLUMN_ALIASES["phones"])
    if phone_cell is not None:
        raw_value, column = phone_cell
        for raw_phone in _split_multi_value(raw_value):
            normalized = normalize_phone(raw_phone, default_region=default_phone_region)
            if normalized is None:
                if default_phone_region is None and not raw_phone.lstrip().startswith("+"):
                    result.warnings.append(
                        f"Local phone requires an explicit region at row={row_number}, "
                        f"column={column}: {raw_phone!r}"
                    )
                else:
                    result.warnings.append(
                        f"Invalid phone at row={row_number}, "
                        f"column={column}: {raw_phone!r}"
                    )
                continue

            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="phones",
                    raw_value=raw_phone,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_phone",
                    confidence=confidence_for("recruiter_csv", "explicit_phone"), # could be recruiter typed, wrong phone, people change numbers
                )
            )

    # current company
    company_cell = _get_cell(row, header_lookup, COLUMN_ALIASES["experience.company"])
    if company_cell is not None:
        raw_value, column = company_cell
        normalized = normalize_company(raw_value)
        if normalized is not None:
            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="experience.company",
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_company",
                    confidence=confidence_for("recruiter_csv", "explicit_company_or_title"), # company could've changed
                )
            )

    # current title
    title_cell = _get_cell(row, header_lookup, COLUMN_ALIASES["experience.title"])
    if title_cell is not None:
        raw_value, column = title_cell
        normalized = normalize_name(raw_value)
        if normalized is not None:
            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="experience.title",
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_text",
                    confidence=confidence_for("recruiter_csv", "explicit_company_or_title"), # SDE I -> SDE II
                )
            )

    # GitHub URL
    github_cell = _get_cell(row, header_lookup, COLUMN_ALIASES["links.github"])
    if github_cell is not None:
        raw_value, column = github_cell
        normalized = normalize_github_url(raw_value)
        if normalized is None:
            result.warnings.append(
                f"Invalid GitHub URL at row={row_number}, column={column}: {raw_value!r}"
            )
        else:
            result.observations.append(
                _make_observation(
                    record_id=record_id,
                    field_path="links.github",
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_id=source_id,
                    row_number=row_number,
                    column=column,
                    method=f"csv_column:{column} -> normalize_github_url",
                    confidence=confidence_for("recruiter_csv", "explicit_url"),
                )
            )


def _make_observation(
    *,
    record_id: str,
    field_path: str,
    raw_value: str,
    normalized_value: str,
    source_id: str,
    row_number: int,
    column: str,
    method: str,
    confidence: float,
) -> Observation:
    return Observation(
        record_id=record_id,
        field_path=field_path,
        raw_value=raw_value,
        normalized_value=normalized_value,
        source=SourceRef(
            source_type="recruiter_csv",
            source_id=source_id,
            locator=f"row={row_number},column={column}",
        ),
        method=method,
        confidence=confidence,
    )


def _build_header_lookup(fieldnames: list[str]) -> dict[str, str]:
    """
    Maps normalized header names to the original CSV header.

    Example:
      "Current Company" -> "current_company" internally,
      but we keep the original column name for provenance.
    """

    lookup = {}

    for fieldname in fieldnames:
        normalized = _normalize_header(fieldname)
        if normalized:
            lookup[normalized] = fieldname

    return lookup


def _normalize_header(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _get_cell(
    row: dict[str, str],
    header_lookup: dict[str, str],
    aliases: list[str],
) -> tuple[str, str] | None:
    for alias in aliases:
        normalized_alias = _normalize_header(alias)
        column = header_lookup.get(normalized_alias)

        if column is None:
            continue

        value = _clean_cell(row.get(column))

        if value is not None:
            return value, column

    return None


def _clean_cell(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    if cleaned.lower() in NULL_LIKE_VALUES:
        return None

    return cleaned


def _split_multi_value(value: str) -> list[str]:
    """
    Split cells like:
      "a@example.com; b@example.com"
      "a@example.com, b@example.com"
    """

    parts = re.split(r"[;,]", value)
    return [part.strip() for part in parts if part.strip()]
