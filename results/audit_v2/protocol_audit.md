# Protocol V2 Audit

- Status: **VERIFIED**
- Query protocol: `issue_only_v2`
- Instances: 1791
- Repositories: 57
- Empty queries: 0
- Duplicate language/instance IDs: 0

| Language | Instances | Repositories | Query source | Gold-path cue n (%) | Index files |
|---|---:|---:|---|---:|---:|
| c | 128 | 3 | resolved_issues=128 | 25 (19.5%) | 128 |
| cpp | 129 | 5 | resolved_issues=129 | 51 (39.5%) | 129 |
| go | 428 | 3 | resolved_issues=428 | 42 (9.8%) | 428 |
| java | 128 | 9 | resolved_issues=128 | 34 (26.6%) | 128 |
| js | 84 | 5 | resolved_issues=84 | 4 (4.8%) | 84 |
| kotlin | 105 | 8 | resolved_issues=105 | 11 (10.5%) | 105 |
| python | 500 | 12 | problem_statement=500 | 122 (24.4%) | 500 |
| rust | 239 | 10 | resolved_issues=239 | 22 (9.2%) | 239 |
| ts | 50 | 2 | resolved_issues=50 | 2 (4.0%) | 50 |

Top-level PR title/body and hint fields are forbidden by construction and tested in
`tests/test_protocol_v2.py`. Existing repository indexes contain legacy V1 query text,
but the V2 runner replaces it from the raw dataset and refuses missing or empty V2 queries.

The JSON companion contains SHA-256 checksums for every raw dataset file.
