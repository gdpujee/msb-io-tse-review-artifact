# MSB-IO: an issue-only localization benchmark

1791 instances over 57 repositories and 9 languages, re-queried so that no query contains post-solution text.

## Why this exists

Multi-SWE-bench stores several text fields per instance. Some predate the
solution (`problem_statement`, `resolved_issues[].title/body`); others are
written after it (the top-level `title`, `body`, `hints`, `hints_text`).
The MTEB reranking task `MultiSWEbenchRR` uses the top-level text as its
query, so 56.5% of its published queries exactly reproduce pull-request
text that postdates the fix. MSB-IO applies the opposite rule: a query is
built only from pre-solution text, and every query is published with its
SHA-256 so the rule is checkable without trusting the builder.

## What is in the package

| file | contents |
| --- | --- |
| `msb_io.jsonl` | one row per instance: query text, query hash, query source, gold labels, candidate-accounting fields |
| `field_availability.csv` | per-language provenance and label accounting |
| `MANIFEST.sha256` | SHA-256 of every file in this directory |

## Query provenance

The rule is uniform but the available field is not: only Python instances
carry a usable `problem_statement` (500 of 1791 instances); the
other 1291 instances fall back to linked-issue title and body. Any
comparison across languages therefore compares differently sourced text,
and `field_availability.csv` records which is which.

## What this is not

* It is not a redistribution of repository source. The package holds
  queries, labels, and hashes only; obtain source from each upstream
  repository at the recorded `base_sha`.
* It is not a claim that the upstream benchmark is unusable. It is the same
  instance set under a different, stated query rule.
* It is not a leaderboard. Numbers computed on it are only comparable to
  others computed on it under the same protocol identifiers.

## Protocol identifiers

| identifier | value |
| --- | --- |
| query | `issue_only_v2` |
| candidates | `component_aware_test_filter_v6` |
| metrics | `full_precision_metrics_v1` |

Dataset revision: `56ff018c04a38e27ada1e9d0a6d5839a51f88f0d`.
