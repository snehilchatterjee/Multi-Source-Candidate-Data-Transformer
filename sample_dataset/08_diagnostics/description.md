# Warnings and errors

One malformed candidate is excluded while the valid candidate survives. Expected: `partial_success` with warnings and an error.

```bash
python -m candidate_transformer --manifest sample_dataset/08_diagnostics/manifest.json --config sample_dataset/08_diagnostics/config.json --allow-partial
```
