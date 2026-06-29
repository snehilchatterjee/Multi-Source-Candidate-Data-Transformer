# MVP

Structured:
  Recruiter CSV export

Unstructured-ish:
  GitHub profile URL
  Recruiter notes .txt


## Recruiter CSV export
Challenges we can think about handling:

1. Duplicate rows:
    - Literal duplicate row (eliminate) [maybe the applied twice]
    - Same email, different missing fields (union)
    - Same email, conflicting fields:
        - Merge because email and phone are strong identifiers.
        - Keep both company/title observations.
        - Pick current_company/title (like maybe later ocurring row if rows are sorted by time)
        - Record conflict in provenance or warnings.
    - Same name, different email:
        - If phone matches, merge.
        - If GitHub/LinkedIn matches, merge.
        


[All of this fill come under Entity Resolution, Field Resolution, Conflict Resolution]


### ER:
1. AI:
    - Embedding based
    - LLM (less likely because might not be cost effective) (?)
    - Named Entity Recognition: Can be important for free text or resume parsing [VVI]
2. Deterministic:
    - Soundex: classification based on sound of word (Kathy McKarthy = Kathy Mccarthy) [maybe take mail as source of truth here]
    - Fuzzy matching


## Evidence from data:

### CSV evidence format:
```
[
  {
    "field": "full_name",
    "raw_value": "Alex Chen",
    "normalized_value": "Alex Chen",
    "source": "recruiter_csv:candidates.csv#row=1,column=name",
    "method": "csv_column:name",
    "confidence": 0.95
  },
  {
    "field": "emails",
    "raw_value": "ALEX.CHEN@example.com",
    "normalized_value": "alex.chen@example.com",
    "source": "recruiter_csv:candidates.csv#row=1,column=email",
    "method": "csv_column:email -> normalize_email",
    "confidence": 0.95
  },
  {
    "field": "phones",
    "raw_value": "9876543210",
    "normalized_value": "+919876543210",
    "source": "recruiter_csv:candidates.csv#row=1,column=phone",
    "method": "csv_column:phone -> normalize_phone_e164",
    "confidence": 0.9
  }
]
```

## Output config
