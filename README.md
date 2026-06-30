# Multi-Source Candidate Data Transformer

A Python CLI that merges recruiter CSV and recruiter-note data into validated candidate profiles. It supports canonical output and runtime-configured output projection.

## Setup

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

From the repository root, generate the default canonical output:

```bash
python -m candidate_transformer \
  --manifest sample_dataset/01_repeated/manifest.json \
  --output out/default.json
```

Generate custom-config output:

```bash
python -m candidate_transformer \
  --manifest sample_dataset/01_repeated/manifest.json \
  --config sample_dataset/01_repeated/config.json \
  --output out/candidates.json
```

The generated examples are committed at:

- [`out/default.json`](out/default.json)
- [`out/candidates.json`](out/candidates.json)

## Test

```bash
python -m pytest -q
```

Run all eight end-to-end golden cases:

```bash
./run_demo_cases.sh
```

## Other inputs

Inputs can also be passed directly without a manifest:

```bash
python -m candidate_transformer \
  --csv path/to/applications.csv \
  --note path/to/notes.txt \
  --config config/projection.json
```

Use `python -m candidate_transformer --help` for all options. GitHub enrichment is optional; enable it with `--enrich-github` and optionally set `GITHUB_TOKEN`.

The required one-page technical design is available at [`docs/SnehilChatterjee_snehil.chatterjee@oracle.com_Eightfold.pdf`](docs/SnehilChatterjee_snehil.chatterjee@oracle.com_Eightfold.pdf).
