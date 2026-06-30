from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from candidate_transformer.pipeline import PipelineResult, run_candidate_pipeline
from candidate_transformer.core.normalize import normalize_candidate_ref


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    projection_config: dict[str, Any] | None = None

    if args.config is not None:
        try:
            projection_config = _read_json_file(Path(args.config))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    
    csv_paths = list(args.csv)
    note_paths = list(args.note)
    note_candidate_refs: dict[str, str] = {}

    if args.manifest is not None:
        try:
            (
                manifest_csv_paths,
                manifest_note_paths,
                manifest_note_candidate_refs,
            ) = _read_ingestion_manifest(Path(args.manifest))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        csv_paths.extend(manifest_csv_paths)
        note_paths.extend(manifest_note_paths)
        note_candidate_refs.update(manifest_note_candidate_refs)

    result = run_candidate_pipeline(
        csv_paths=csv_paths,
        note_paths=note_paths,
        note_candidate_refs=note_candidate_refs,
        projection_config=projection_config,
        default_phone_region=args.default_phone_region,
    )

    _print_warnings_and_errors(result)

    if result.errors and not args.allow_partial:
        return 1

    payload = _make_output_payload(result)

    try:
        _write_output(payload, args.output)
    except OSError as exc:
        print(f"ERROR: Could not write output: {exc}", file=sys.stderr)
        return 1

    if result.errors and args.allow_partial and payload["candidate_count"] == 0:
        return 1

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="candidate-transformer",
        description="Build canonical candidate profiles from recruiter CSVs and notes.",
    )

    parser.add_argument(
        "--csv",
        action="append",
        default=[],
        help="Path to a recruiter CSV file. Can be provided multiple times.",
    )

    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Path to a recruiter notes .txt file. Can be provided multiple times.",
    )

    parser.add_argument(
        "--config",
        help="Path to a projection config JSON file. If omitted, canonical candidates are output.",
    )

    parser.add_argument(
        "--output",
        help="Path to write output JSON. If omitted, JSON is printed to stdout.",
    )
    
    parser.add_argument(
        "--manifest",
        help=(
            "Path to ingestion manifest JSON. "
            "Supports csv files and notes with candidate_ref mappings."
        ),
    )

    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "Write valid candidates even if some candidates have errors. "
            "The output JSON will include an errors field and status='partial_success'."
        ),
    )

    parser.add_argument(
        "--default-phone-region",
        default="IN",
        help="Default phone region for local phone numbers. Default: IN.",
    )

    return parser


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            raise ValueError(f"Config file does not exist: {path}")

        if path.is_dir():
            raise ValueError(f"Config path is a directory, not a file: {path}")

        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)

    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON config {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read config file {path}: {exc}") from exc

    if not isinstance(value, dict):
        raise ValueError(f"Config file must contain a JSON object: {path}")

    return value


def _make_output_payload(result: PipelineResult) -> dict[str, Any]:
    if result.projected_outputs is not None:
        candidates = list(result.projected_outputs)
        output_kind = "projected"
    else:
        candidates = [
            candidate.to_dict()
            for candidate in result.canonical_candidates
        ]
        output_kind = "canonical"

    candidate_count = len(candidates)

    if result.errors and candidate_count > 0:
        status = "partial_success"
    elif result.errors:
        status = "failed"
    else:
        status = "success"

    return {
        "status": status,
        "kind": output_kind,
        "candidate_count": candidate_count,
        "candidates": candidates,
        "warnings": result.warnings,
        "errors": result.errors,
    }


def _write_output(payload: dict[str, Any], output_path: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)

    if output_path is None:
        print(text)
        return

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")


def _print_warnings_and_errors(result: PipelineResult) -> None:
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)

def _read_ingestion_manifest(path: Path) -> tuple[list[Path], list[Path], dict[str, str]]:
    manifest = _read_json_file(path)
    base_dir = path.parent

    csv_paths = _manifest_paths(
        manifest.get("csv", []),
        base_dir=base_dir,
        field_name="csv",
    )

    note_paths: list[Path] = []
    note_candidate_refs: dict[str, str] = {}

    notes_value = manifest.get("notes", [])

    if not isinstance(notes_value, list):
        raise ValueError("Manifest field 'notes' must be a list")

    for index, entry in enumerate(notes_value):
        if isinstance(entry, str):
            note_path = _resolve_manifest_path(entry, base_dir)
            note_paths.append(note_path)
            continue

        if not isinstance(entry, dict):
            raise ValueError(f"Manifest notes[{index}] must be a string or object")

        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError(f"Manifest notes[{index}].path must be a non-empty string")

        note_path = _resolve_manifest_path(raw_path, base_dir)
        note_paths.append(note_path)

        raw_candidate_ref = entry.get("candidate_ref")
        if raw_candidate_ref is not None:
            candidate_ref = normalize_candidate_ref(str(raw_candidate_ref))

            if candidate_ref is None:
                raise ValueError(
                    f"Manifest notes[{index}].candidate_ref must be non-empty"
                )

            note_candidate_refs[str(note_path)] = candidate_ref
            note_candidate_refs[note_path.name] = candidate_ref

    return csv_paths, note_paths, note_candidate_refs


def _manifest_paths(
    value: Any,
    *,
    base_dir: Path,
    field_name: str,
) -> list[Path]:
    if not isinstance(value, list):
        raise ValueError(f"Manifest field {field_name!r} must be a list")

    paths: list[Path] = []

    for index, entry in enumerate(value):
        if isinstance(entry, str):
            paths.append(_resolve_manifest_path(entry, base_dir))
            continue

        if isinstance(entry, dict):
            raw_path = entry.get("path")

            if not isinstance(raw_path, str) or not raw_path:
                raise ValueError(
                    f"Manifest {field_name}[{index}].path must be a non-empty string"
                )

            paths.append(_resolve_manifest_path(raw_path, base_dir))
            continue

        raise ValueError(f"Manifest {field_name}[{index}] must be a string or object")

    return paths


def _resolve_manifest_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path)

    if path.is_absolute():
        return path

    return base_dir / path


if __name__ == "__main__":
    raise SystemExit(main())