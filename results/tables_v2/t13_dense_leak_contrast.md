# The dense reranker under the superseded query rule

Control = the released issue-only rule; treatment = the superseded rule.
Both arms use `bm25_swerank_rerank50` with model revision
`745d2a06103a66d3cfa600aa52fc0d3523010daa`, candidate_k = 50,
max_seq_length = 512. Delta is treatment minus
control, paired by instance.

| stratum | metric | n | issue-only | superseded | delta | repository-cluster 95% CI | p | rank-biserial |
|---|---|---:|---:|---:|---:|---|---:|---:|
| all | hit@1 | 1791 | 0.4160 | 0.4712 | +0.0553 | [0.0259, 0.0843] | 0.00212977 | +0.3913 |
| all | hit@10 | 1791 | 0.8068 | 0.8532 | +0.0463 | [0.0259, 0.0774] | 4.09996e-05 | +0.6434 |
| all | mrr | 1791 | 0.5491 | 0.5985 | +0.0494 | [0.026, 0.0766] | 0.000994184 | +0.3403 |
| all | ap | 1791 | 0.4443 | 0.4864 | +0.0420 | [0.0213, 0.064] | 0.000463049 | +0.3469 |
| non_python | hit@1 | 1291 | 0.4059 | 0.4857 | +0.0798 | [0.0542, 0.1114] | 0.00099372 | +0.4498 |
| non_python | hit@10 | 1291 | 0.7955 | 0.8567 | +0.0612 | [0.0334, 0.099] | 8.72613e-05 | +0.6752 |
| non_python | mrr | 1291 | 0.5391 | 0.6089 | +0.0697 | [0.0461, 0.1029] | 0.000271226 | +0.3901 |
| non_python | ap | 1291 | 0.4028 | 0.4625 | +0.0597 | [0.0404, 0.0867] | 6.8218e-05 | +0.4031 |
| python | hit@1 | 500 | 0.4420 | 0.4340 | -0.0080 | [-0.0193, 0.0086] | 0.4375 | -0.1667 |
| python | hit@10 | 500 | 0.8360 | 0.8440 | +0.0080 | [0.0, 0.0176] | 0.25 | +0.3333 |
| python | mrr | 500 | 0.5750 | 0.5718 | -0.0032 | [-0.0107, 0.0068] | 0.577148 | +0.0070 |
| python | ap | 500 | 0.5517 | 0.5480 | -0.0037 | [-0.0099, 0.0041] | 0.240234 | -0.0427 |

## Difference-in-differences against BM25 (Hit@1)

Per instance: (dense superseded - dense issue-only) - (BM25 superseded - BM25 issue-only).

| stratum | n | clusters | mean DiD | 95% CI | p | rank-biserial | instances up | instances down |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| all | 1791 | 57 | +0.0408 | [0.008, 0.0728] | 0.000177068 | +0.2070 | 204 | 136 |
| non_python | 1291 | 45 | +0.0581 | [0.0172, 0.0974] | 6.30878e-05 | +0.2295 | 193 | 122 |
| python | 500 | 12 | -0.0040 | [-0.0166, 0.0154] | 0.705457 | -0.0769 | 11 | 14 |

