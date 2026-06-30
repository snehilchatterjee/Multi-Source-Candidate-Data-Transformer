from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from jsonschema import Draft202012Validator


NULLABLE_STRING = {"type": ["string", "null"]}
CONFIDENCE = {"type": "number", "minimum": 0.0, "maximum": 1.0}
STRING_ARRAY = {
    "type": "array",
    "items": {"type": "string"},
    "uniqueItems": True,
}
RESOLUTION_STATUS = {
    "type": "string",
    "enum": ["resolved", "ambiguous", "unstructured_only", "missing"],
}


CANONICAL_CANDIDATE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://candidate-transformer.local/schema/canonical-candidate.json",
    "title": "CanonicalCandidate",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "candidate_id",
        "full_name",
        "emails",
        "phones",
        "location",
        "links",
        "headline",
        "years_experience",
        "skills",
        "experience",
        "education",
        "provenance",
        "overall_confidence",
        "primary_email",
        "secondary_emails",
        "email_details",
        "email_resolution_status",
        "email_selection_reason",
        "email_confidence",
        "primary_phone",
        "secondary_phones",
        "phone_details",
        "phone_resolution_status",
        "phone_selection_reason",
        "phone_confidence",
    ],
    "properties": {
        "candidate_id": {"type": "string", "minLength": 1},
        "full_name": NULLABLE_STRING,
        "emails": STRING_ARRAY,
        "phones": STRING_ARRAY,
        "location": {"$ref": "#/$defs/location"},
        "links": {"$ref": "#/$defs/links"},
        "headline": NULLABLE_STRING,
        "years_experience": {
            "type": ["number", "null"],
            "minimum": 0.0,
        },
        "skills": {
            "type": "array",
            "items": {"$ref": "#/$defs/skill"},
        },
        "experience": {
            "type": "array",
            "items": {"$ref": "#/$defs/experience"},
        },
        "education": {
            "type": "array",
            "items": {"$ref": "#/$defs/education"},
        },
        "provenance": {
            "type": "array",
            "items": {"$ref": "#/$defs/provenance"},
        },
        "overall_confidence": CONFIDENCE,
        "primary_email": NULLABLE_STRING,
        "secondary_emails": STRING_ARRAY,
        "email_details": {
            "type": "array",
            "items": {"$ref": "#/$defs/contact_detail"},
        },
        "email_resolution_status": RESOLUTION_STATUS,
        "email_selection_reason": NULLABLE_STRING,
        "email_confidence": CONFIDENCE,
        "primary_phone": NULLABLE_STRING,
        "secondary_phones": STRING_ARRAY,
        "phone_details": {
            "type": "array",
            "items": {"$ref": "#/$defs/contact_detail"},
        },
        "phone_resolution_status": RESOLUTION_STATUS,
        "phone_selection_reason": NULLABLE_STRING,
        "phone_confidence": CONFIDENCE,
    },
    "$defs": {
        "location": {
            "type": "object",
            "additionalProperties": False,
            "required": ["city", "region", "country"],
            "properties": {
                "city": NULLABLE_STRING,
                "region": NULLABLE_STRING,
                "country": NULLABLE_STRING,
            },
        },
        "links": {
            "type": "object",
            "additionalProperties": False,
            "required": ["linkedin", "github", "portfolio", "other"],
            "properties": {
                "linkedin": NULLABLE_STRING,
                "github": NULLABLE_STRING,
                "portfolio": NULLABLE_STRING,
                "other": STRING_ARRAY,
            },
        },
        "skill": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "confidence", "sources"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "confidence": CONFIDENCE,
                "sources": STRING_ARRAY,
            },
        },
        "experience": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "company",
                "title",
                "start",
                "end",
                "summary",
                "confidence",
                "sources",
            ],
            "properties": {
                "company": NULLABLE_STRING,
                "title": NULLABLE_STRING,
                "start": NULLABLE_STRING,
                "end": NULLABLE_STRING,
                "summary": NULLABLE_STRING,
                "confidence": CONFIDENCE,
                "sources": STRING_ARRAY,
            },
        },
        "education": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "institution",
                "degree",
                "field",
                "end_year",
                "confidence",
                "sources",
            ],
            "properties": {
                "institution": NULLABLE_STRING,
                "degree": NULLABLE_STRING,
                "field": NULLABLE_STRING,
                "end_year": {"type": ["integer", "null"]},
                "confidence": CONFIDENCE,
                "sources": STRING_ARRAY,
            },
        },
        "provenance": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "field_path",
                "value",
                "source_type",
                "source_id",
                "locator",
                "method",
                "confidence",
            ],
            "properties": {
                "field_path": {"type": "string", "minLength": 1},
                "value": {"type": "string"},
                "source_type": {"type": "string", "minLength": 1},
                "source_id": {"type": "string", "minLength": 1},
                "locator": NULLABLE_STRING,
                "method": {"type": "string", "minLength": 1},
                "confidence": CONFIDENCE,
            },
        },
        "contact_detail": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "value",
                "confidence",
                "sources",
                "latest_application_at",
                "distinct_application_count",
                "corroborating_notes_count",
            ],
            "properties": {
                "value": {"type": "string", "minLength": 1},
                "confidence": CONFIDENCE,
                "sources": STRING_ARRAY,
                "latest_application_at": NULLABLE_STRING,
                "distinct_application_count": {
                    "type": "integer",
                    "minimum": 0,
                },
                "corroborating_notes_count": {
                    "type": "integer",
                    "minimum": 0,
                },
            },
        },
    },
}


Draft202012Validator.check_schema(CANONICAL_CANDIDATE_SCHEMA)
_CANONICAL_VALIDATOR = Draft202012Validator(CANONICAL_CANDIDATE_SCHEMA)


def validate_canonical_candidate(candidate: Any) -> list[str]:
    """Return deterministic JSON-Schema violations for one candidate."""

    payload = _to_json_value(candidate)
    violations = sorted(
        _CANONICAL_VALIDATOR.iter_errors(payload),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )

    return [
        f"{_format_json_path(error.absolute_path)}: {error.message}"
        for error in violations
    ]


def _to_json_value(value: Any) -> Any:
    if is_dataclass(value):
        return _to_json_value(asdict(value))

    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_json_value(item) for item in value]

    return value


def _format_json_path(path: Any) -> str:
    output = "$"

    for part in path:
        if isinstance(part, int):
            output += f"[{part}]"
        else:
            output += f".{part}"

    return output
