# RQ7 - does the query rule change which configuration wins?

Both arms: 8 configurations x 1,791 instances (57 repository clusters). Control = `issue_only_v2`, treatment = `legacy_mixed_v1`.

| Configuration | Hit@1 issue-only | Hit@1 superseded | Δ Hit@1 | 95% CI | MRR issue-only | MRR superseded | Δ MRR |
|---|---:|---:|---:|---|---:|---:|---:|
| anchor_path_only | 0.4366 | 0.4511 | +0.0145 | [-0.0041, +0.0345] | 0.5673 | 0.5845 | +0.0171 |
| bm25_path | 0.4098 | 0.4260 | +0.0162 | [-0.0027, +0.0357] | 0.5431 | 0.5607 | +0.0177 |
| bm25 | 0.4065 | 0.4210 | +0.0145 | [-0.0043, +0.0338] | 0.5405 | 0.5574 | +0.0169 |
| bm25_anchor | 0.4003 | 0.4243 | +0.0240 | [+0.0027, +0.0448] | 0.5392 | 0.5625 | +0.0233 |
| anchor_symbol_only | 0.3629 | 0.3836 | +0.0207 | [+0.0000, +0.0431] | 0.5067 | 0.5277 | +0.0211 |
| bm25_anchor_graph | 0.3322 | 0.3439 | +0.0117 | [-0.0075, +0.0276] | 0.4731 | 0.4888 | +0.0157 |
| anchor_path_graph | 0.3116 | 0.3272 | +0.0156 | [-0.0117, +0.0375] | 0.4495 | 0.4627 | +0.0133 |
| bm25_graph | 0.2457 | 0.2535 | +0.0078 | [-0.0145, +0.0247] | 0.3905 | 0.3967 | +0.0062 |

## Ordering by hit@1

- issue-only: anchor_path_only > bm25_path > bm25 > bm25_anchor > anchor_symbol_only > bm25_anchor_graph > anchor_path_graph > bm25_graph
- superseded: anchor_path_only > bm25_path > bm25_anchor > bm25 > anchor_symbol_only > bm25_anchor_graph > anchor_path_graph > bm25_graph
- Spearman rho = 0.9762 (95% CI [0.9048, 1.0000]), Kendall tau = 0.9286, 27 concordant / 1 discordant of 28 pairs
- leader unchanged: True; positions that moved: bm25, bm25_anchor

## Ordering by mrr

- issue-only: anchor_path_only > bm25_path > bm25 > bm25_anchor > anchor_symbol_only > bm25_anchor_graph > anchor_path_graph > bm25_graph
- superseded: anchor_path_only > bm25_anchor > bm25_path > bm25 > anchor_symbol_only > bm25_anchor_graph > anchor_path_graph > bm25_graph
- Spearman rho = 0.9286 (95% CI [0.9286, 1.0000]), Kendall tau = 0.8571, 26 concordant / 2 discordant of 28 pairs
- leader unchanged: True; positions that moved: bm25, bm25_path, bm25_anchor

## Pairs whose difference changes sign

- hit@1: bm25 favoured under issue-only (+0.0061, p = 0.147) and bm25_anchor under superseded (-0.0034, p = 0.461); superseded-rule interval [-0.0327, +0.0536]
- mrr: bm25 favoured under issue-only (+0.0013, p = 0.061) and bm25_anchor under superseded (-0.0051, p = 0.157); superseded-rule interval [-0.0274, +0.0506]
- mrr: bm25_path favoured under issue-only (+0.0039, p = 0.154) and bm25_anchor under superseded (-0.0018, p = 0.216); superseded-rule interval [-0.0304, +0.0467]

## Mechanism

Share of instances whose query mentions the gold file path, by stratum.
The Python stratum's treatment query is the issue text repeated and holds no post-solution text, so any rise there would indicate a length artefact rather than a leak effect.

| Stratum | n | issue-only | superseded | Δ |
|---|---:|---:|---:|---:|
| all | 1,791 | 0.1748 | 0.1982 | +0.0235 |
| python | 500 | 0.2440 | 0.2440 | +0.0000 |
| non_python | 1,291 | 0.1479 | 0.1805 | +0.0325 |

