# Query-field provenance across localization benchmark families

**Question.** Is a post-solution query a property of issue-localization benchmarks, or of a particular derivative conversion?

**Answer.** It is a property of the derivative conversion. Every SWE-bench family examined separates the issue text (query) from the solution (patch/test_patch), whereas the MTEB reranking task packages top-level PR text as its query.

| dataset | revision | query field | solution fields | query provenance |
|---|---|---|---|---|
| `SWE-bench/SWE-bench` | `c6fe717fd7a4` | `problem_statement` | `patch`, `test_patch` | PRE_SOLUTION_ISSUE_TEXT |
| `princeton-nlp/SWE-bench_Verified` | `c104f840cc67` | `problem_statement` | `patch`, `test_patch` | PRE_SOLUTION_ISSUE_TEXT |
| `SWE-bench/SWE-bench_Multilingual` | `846e647b9f33` | `problem_statement` | `patch`, `test_patch` | PRE_SOLUTION_ISSUE_TEXT |
| `mteb/MultiSWEbenchRR` | `f80517681e98` | `text` | — | MIXED |

**Caveat.** This audit classifies the *query field's provenance from the released schema*. It is not a text-level leak audit of the SWE-bench families; the solution-leakage question for those benchmarks is a different measurement, addressed by Aleithan et al. (2024) and by OpenAI (2026).
