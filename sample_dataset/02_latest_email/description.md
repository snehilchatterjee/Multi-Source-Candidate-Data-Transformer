# Latest email wins

Two applications have different emails. Expected: the latest email becomes primary and the old one remains secondary.

```bash
python -m candidate_transformer --manifest sample_dataset/02_latest_email/manifest.json --config sample_dataset/02_latest_email/config.json
```
