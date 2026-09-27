# MTEB MultiSWEbenchRR query provenance audit

- Status: **VERIFIED**
- MTEB queries: **1688**
- Local source rows available for exact matching: **1791**
- PR-only exact matches: **954**
- Issue-only exact matches: **457**
- Exact matches to both: **0**
- Unmatched (not classified): **277**

## Exact matches by source language

Each public query is counted at most once per language, even when duplicate local rows match it.

| language | PR-only | issue-only | both |
|---|---:|---:|---:|
| c | 107 | 0 | 0 |
| cpp | 40 | 0 | 0 |
| go | 414 | 0 | 0 |
| java | 94 | 0 | 0 |
| js | 56 | 0 | 0 |
| python | 0 | 457 | 0 |
| rust | 194 | 0 | 0 |
| ts | 49 | 0 | 0 |

Classification uses exact normalized text only. Therefore, it establishes provenance for matches
without speculating about unmatched queries. A PR-only match is post-solution text and is not a
valid issue-only localization input.
