# Repeated applications

Two applications with the same email merge into one candidate. Expected: `application_count: 2` and `repeated_distinct_applications`.

```bash
python -m candidate_transformer --manifest sample_dataset/01_repeated/manifest.json --config sample_dataset/01_repeated/config.json
```
