from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from candidate_transformer.pipeline import PipelineResult, run_candidate_pipeline


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

    result = run_candidate_pipeline(
        csv_paths=args.csv,
        note_paths=args.note,
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
    if not path.exists():
        raise ValueError(f"Config file does not exist: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON config {path}: {exc}") from exc

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


if __name__ == "__main__":
    raise SystemExit(main())