# Query-level leakage: MSB-IO issue-only materialization

- Status: **VERIFIED**
- Instances: 1791
- Query contains the PR title verbatim: 35 (2.0%)
- Query contains the PR body verbatim: 0 (0.0%)

Attribution of the title matches:

- named after a linked issue (`issue_title`): 29
- quotes the reporter's wording (`issue_proposal`): 2
- sits on a pull-request reference line (`pr_reference`, residual leakage): 4
- unexplained: 0

| lang | instances | PR title | PR body | issue_title | issue_proposal | pr_reference | unexplained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c | 128 | 2 | 0 | 2 | 0 | 0 | 0 |
| cpp | 129 | 4 | 0 | 4 | 0 | 0 | 0 |
| go | 428 | 18 | 0 | 16 | 2 | 0 | 0 |
| java | 128 | 3 | 0 | 3 | 0 | 0 | 0 |
| js | 84 | 4 | 0 | 1 | 0 | 3 | 0 |
| kotlin | 105 | 0 | 0 | 0 | 0 | 0 | 0 |
| python | 500 | 0 | 0 | 0 | 0 | 0 | 0 |
| rust | 239 | 4 | 0 | 3 | 0 | 1 | 0 |
| ts | 50 | 0 | 0 | 0 | 0 | 0 | 0 |

A residual PR-title match is acceptable when it is attributable to pre-solution text: the PR is named after a linked issue (issue_title) or quotes the reporter's own wording (issue_proposal). A match on a line that references a pull request (pr_reference) is upstream issue-body contamination -- the issue field was edited after the fix -- and is reported as residual leakage rather than hidden. Anything else aborts.
