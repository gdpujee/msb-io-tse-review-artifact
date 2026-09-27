# Query-level solution leakage

Both protocols are measured on the same instances against the upstream pull-request text, so the two rows are directly comparable. A PR-body match is any 40-character window of the body occurring in the query; every match is attributed, and the attribution columns are counts of matches.

| protocol | instances | PR title | PR body | title: issue_title | title: issue_proposal | title: pr_reference | title: unexplained | body: issue_text | body: pr_reference | body: unexplained |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| issue_only | 1791 | 35 (2.0%) | 119 (6.6%) | 29 | 2 | 4 | 0 | 119 | 0 | 0 |
| legacy_mixed | 1791 | 1291 (72.1%) | 989 (55.2%) | 49 | 6 | 0 | 1236 | 5 | 1 | 983 |

## issue_only: per language

| lang | instances | PR title | PR body | title: issue_title | title: issue_proposal | title: pr_reference | title: unexplained | body: issue_text | body: pr_reference | body: unexplained |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c | 128 | 2 | 16 | 2 | 0 | 0 | 0 | 16 | 0 | 0 |
| cpp | 129 | 4 | 6 | 4 | 0 | 0 | 0 | 6 | 0 | 0 |
| go | 428 | 18 | 35 | 16 | 2 | 0 | 0 | 35 | 0 | 0 |
| java | 128 | 3 | 19 | 3 | 0 | 0 | 0 | 19 | 0 | 0 |
| js | 84 | 4 | 10 | 1 | 0 | 3 | 0 | 10 | 0 | 0 |
| kotlin | 105 | 0 | 15 | 0 | 0 | 0 | 0 | 15 | 0 | 0 |
| python | 500 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| rust | 239 | 4 | 17 | 3 | 0 | 1 | 0 | 17 | 0 | 0 |
| ts | 50 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

## legacy_mixed: per language

| lang | instances | PR title | PR body | title: issue_title | title: issue_proposal | title: pr_reference | title: unexplained | body: issue_text | body: pr_reference | body: unexplained |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c | 128 | 128 | 110 | 3 | 0 | 0 | 125 | 0 | 0 | 110 |
| cpp | 129 | 129 | 111 | 6 | 0 | 0 | 123 | 0 | 0 | 111 |
| go | 428 | 428 | 344 | 24 | 2 | 0 | 402 | 3 | 1 | 340 |
| java | 128 | 128 | 82 | 4 | 0 | 0 | 124 | 0 | 0 | 82 |
| js | 84 | 84 | 35 | 4 | 3 | 0 | 77 | 0 | 0 | 35 |
| kotlin | 105 | 105 | 87 | 3 | 0 | 0 | 102 | 0 | 0 | 87 |
| python | 500 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| rust | 239 | 239 | 199 | 5 | 1 | 0 | 233 | 2 | 0 | 197 |
| ts | 50 | 50 | 21 | 0 | 0 | 0 | 50 | 0 | 0 | 21 |

A residual overlap with the pull request is acceptable when it is attributable to pre-solution text. For the title: the PR is named after a linked issue (issue_title) or quotes the reporter's own wording (issue_proposal). For a body span: the span occurs in the pre-solution issue text (issue_text), which is what a pull-request body quoting the report looks like. A match on a line naming the instance's own pull request (pr_reference) is upstream issue-body contamination -- the issue field was edited after the fix -- and is reported as residual leakage rather than hidden. The rule is narrow by design: a reference to some other pull request is not counted, so the residual is a lower bound. An unattributable match of either kind fails the released protocol.
