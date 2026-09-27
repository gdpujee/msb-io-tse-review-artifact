# Query-level leakage: V1 materialization superseded

- Status: **FAILED**
- Instances: 1791
- Query contains the PR title verbatim: 1291 (72.1%)
- Query contains the PR body verbatim: 85 (4.7%)

Attribution of the title matches:

- named after a linked issue (`issue_title`): 49
- quotes the reporter's wording (`issue_proposal`): 6
- sits on a pull-request reference line (`pr_reference`, residual leakage): 41
- unexplained: 1195

| lang | instances | PR title | PR body | issue_title | issue_proposal | pr_reference | unexplained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c | 128 | 128 | 16 | 3 | 0 | 1 | 124 |
| cpp | 129 | 129 | 9 | 6 | 0 | 1 | 122 |
| go | 428 | 428 | 35 | 24 | 2 | 7 | 395 |
| java | 128 | 128 | 9 | 4 | 0 | 27 | 97 |
| js | 84 | 84 | 4 | 4 | 3 | 3 | 74 |
| kotlin | 105 | 105 | 7 | 3 | 0 | 0 | 102 |
| python | 500 | 0 | 0 | 0 | 0 | 0 | 0 |
| rust | 239 | 239 | 5 | 5 | 1 | 2 | 231 |
| ts | 50 | 50 | 0 | 0 | 0 | 0 | 50 |

A residual PR-title match is acceptable when it is attributable to pre-solution text: the PR is named after a linked issue (issue_title) or quotes the reporter's own wording (issue_proposal). A match on a line that references a pull request (pr_reference) is upstream issue-body contamination -- the issue field was edited after the fix -- and is reported as residual leakage rather than hidden. Anything else aborts.
