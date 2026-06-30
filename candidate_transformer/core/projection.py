from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping


MISSING = object()

SUPPORTED_MISSING_POLICIES = {"null", "omit", "error"}

PATH_PART_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d*)\])?$")


@dataclass
class ProjectionResult:
    output: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def project_candidate(candidate: Any, config: Mapping[str, Any]) -> ProjectionResult:
    """
    Project a CanonicalCandidate into a caller-requested output shape.

    Supported input paths:
      full_name
      emails[0]
      phones[0]
      skills[].name
      links.github
      experience[].company

    Supported output paths:
      name
      email
      contact.email
      profile.github
    """

    result = ProjectionResult(output={})

    root = _to_jsonable(candidate.to_dict() if hasattr(candidate, "to_dict") else candidate)

    fields = config.get("fields")
    if not isinstance(fields, list):
        result.errors.append("config.fields must be a list")
        return result

    global_on_missing = config.get("on_missing", "null")
    if global_on_missing not in SUPPORTED_MISSING_POLICIES:
        result.errors.append(
            f"config.on_missing must be one of {sorted(SUPPORTED_MISSING_POLICIES)}"
        )
        return result

    for index, field_spec in enumerate(fields):
        if not isinstance(field_spec, Mapping):
            result.errors.append(f"config.fields[{index}] must be an object")
            continue

        _project_one_field(
            root=root,
            field_spec=field_spec,
            index=index,
            global_on_missing=global_on_missing,
            result=result,
        )

    if config.get("include_confidence", False):
        result.output["overall_confidence"] = root.get("overall_confidence")

    if config.get("include_provenance", False):
        result.output["provenance"] = root.get("provenance", [])

    return result


def _project_one_field(
    *,
    root: dict[str, Any],
    field_spec: Mapping[str, Any],
    index: int,
    global_on_missing: str,
    result: ProjectionResult,
) -> None:
    output_path = field_spec.get("path")
    from_path = field_spec.get("from", output_path)
    expected_type = field_spec.get("type", "any")
    required = bool(field_spec.get("required", False))
    on_missing = field_spec.get("on_missing", global_on_missing)

    if not isinstance(output_path, str) or not output_path:
        result.errors.append(f"config.fields[{index}].path must be a non-empty string")
        return

    if not isinstance(from_path, str) or not from_path:
        result.errors.append(f"config.fields[{index}].from must be a non-empty string")
        return

    if on_missing not in SUPPORTED_MISSING_POLICIES:
        result.errors.append(
            f"config.fields[{index}].on_missing must be one of "
            f"{sorted(SUPPORTED_MISSING_POLICIES)}"
        )
        return

    try:
        value = _read_path(root, from_path)
    except ValueError as exc:
        result.errors.append(f"Invalid input path for {output_path!r}: {exc}")
        return

    if value is MISSING or value is None:
        if required:
            result.errors.append(
                f"Required field {output_path!r} is missing from {from_path!r}"
            )
            return

        if on_missing == "omit":
            return

        if on_missing == "error":
            result.errors.append(f"Field {output_path!r} is missing from {from_path!r}")
            return

        value = None

    value = _to_jsonable(value)

    type_error = _type_error(value, expected_type)
    if type_error is not None:
        result.errors.append(f"Field {output_path!r}: {type_error}")
        return

    try:
        _write_path(result.output, output_path, value)
    except ValueError as exc:
        result.errors.append(f"Invalid output path {output_path!r}: {exc}")


def _read_path(root: Any, path: str) -> Any:
    parts = path.split(".")

    if any(not part for part in parts):
        raise ValueError(f"bad path syntax: {path!r}")

    return _read_parts(root, parts)


def _read_parts(current: Any, parts: list[str]) -> Any:
    if not parts:
        return current

    name, selector = _parse_path_part(parts[0])
    child = _get_member(current, name)

    if child is MISSING:
        return MISSING

    rest = parts[1:]

    if selector is None:
        return _read_parts(child, rest)

    if selector == "all":
        if not isinstance(child, (list, tuple)):
            return MISSING

        values: list[Any] = []

        for item in child:
            item_value = _read_parts(item, rest)

            if item_value is MISSING:
                continue

            if isinstance(item_value, list):
                values.extend(item_value)
            else:
                values.append(item_value)

        return values

    if not isinstance(child, (list, tuple)):
        return MISSING

    if selector < 0 or selector >= len(child):
        return MISSING

    return _read_parts(child[selector], rest)


def _parse_path_part(part: str) -> tuple[str, int | str | None]:
    match = PATH_PART_RE.match(part)

    if not match:
        raise ValueError(f"bad path part: {part!r}")

    name = match.group(1)
    selector_text = match.group(2)

    if selector_text is None:
        return name, None

    if selector_text == "":
        return name, "all"

    return name, int(selector_text)


def _get_member(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, MISSING)

    if is_dataclass(value):
        return getattr(value, name, MISSING)

    return MISSING


def _write_path(output: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")

    if any(not part for part in parts):
        raise ValueError(f"bad path syntax: {path!r}")

    for part in parts:
        if "[" in part or "]" in part:
            raise ValueError("output paths do not support array syntax yet")

    current = output

    for part in parts[:-1]:
        existing = current.get(part)

        if existing is None:
            existing = {}
            current[part] = existing

        if not isinstance(existing, dict):
            raise ValueError(f"cannot write nested field under non-object path {part!r}")

        current = existing

    current[parts[-1]] = value


def _type_error(value: Any, expected_type: str) -> str | None:
    if value is None:
        return None

    if expected_type == "any":
        return None

    if expected_type == "string":
        if isinstance(value, str):
            return None
        return f"expected string, got {type(value).__name__}"

    if expected_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return None
        return f"expected number, got {type(value).__name__}"

    if expected_type == "boolean":
        if isinstance(value, bool):
            return None
        return f"expected boolean, got {type(value).__name__}"

    if expected_type == "object":
        if isinstance(value, dict):
            return None
        return f"expected object, got {type(value).__name__}"

    if expected_type == "array":
        if isinstance(value, list):
            return None
        return f"expected array, got {type(value).__name__}"

    if expected_type == "string[]":
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return None
        return "expected string[]"

    return f"unsupported expected type {expected_type!r}"


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))

    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}

    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]

    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]

    return value