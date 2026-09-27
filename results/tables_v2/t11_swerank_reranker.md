# SweRankEmbed-Small reranking baseline

BM25 retrieves 50 files; the pinned 137M SweRankEmbed-Small model reranks only that head.
Documents use the official 512-token setting. The BM25 tail remains unchanged.

| language | method | n | Hit@1 | Hit@10 | MRR | AP | mean seconds |
|---|---|---:|---:|---:|---:|---:|---:|
| c | bm25 | 128 | 0.2266 | 0.6172 | 0.3448 | 0.2295 | 0.163 |
| c | bm25_swerank_rerank50 | 128 | 0.2266 | 0.6641 | 0.3779 | 0.2474 | 2.003 |
| cpp | bm25 | 129 | 0.4961 | 0.9147 | 0.6486 | 0.4856 | 0.052 |
| cpp | bm25_swerank_rerank50 | 129 | 0.3023 | 0.7752 | 0.4455 | 0.3110 | 1.678 |
| go | bm25 | 428 | 0.4650 | 0.8972 | 0.6044 | 0.4811 | 0.111 |
| go | bm25_swerank_rerank50 | 428 | 0.5350 | 0.9136 | 0.6730 | 0.5314 | 1.176 |
| java | bm25 | 128 | 0.3359 | 0.7812 | 0.4795 | 0.3588 | 0.226 |
| java | bm25_swerank_rerank50 | 128 | 0.3828 | 0.7188 | 0.5052 | 0.3504 | 1.923 |
| js | bm25 | 84 | 0.3810 | 0.7976 | 0.5269 | 0.4247 | 0.019 |
| js | bm25_swerank_rerank50 | 84 | 0.4881 | 0.8333 | 0.6085 | 0.4833 | 0.895 |
| kotlin | bm25 | 105 | 0.4000 | 0.6857 | 0.5005 | 0.3773 | 0.211 |
| kotlin | bm25_swerank_rerank50 | 105 | 0.4286 | 0.7238 | 0.5412 | 0.4226 | 2.428 |
| python | bm25 | 500 | 0.4360 | 0.8340 | 0.5604 | 0.5398 | 0.476 |
| python | bm25_swerank_rerank50 | 500 | 0.4420 | 0.8360 | 0.5750 | 0.5517 | 2.289 |
| rust | bm25 | 239 | 0.3933 | 0.8452 | 0.5478 | 0.3913 | 0.114 |
| rust | bm25_swerank_rerank50 | 239 | 0.3096 | 0.7531 | 0.4484 | 0.3045 | 1.471 |
| ts | bm25 | 50 | 0.1400 | 0.4800 | 0.2467 | 0.2219 | 0.111 |
| ts | bm25_swerank_rerank50 | 50 | 0.3600 | 0.6600 | 0.4472 | 0.3636 | 2.589 |
| ALL | bm25 | 1791 | 0.4065 | 0.8169 | 0.5405 | 0.4431 | 0.223 |
| ALL | bm25_swerank_rerank50 | 1791 | 0.4160 | 0.8068 | 0.5491 | 0.4443 | 1.775 |

## Paired comparison (all instances)

| metric | delta | repository-cluster 95% CI | p_repo | p_repo_Holm | rank-biserial |
|---|---:|---|---:|---:|---:|
| hit@1 | +0.0095 | [-0.0431, 0.0545] | 0.988094 | 0.988094 | +0.0253 |
| hit@10 | -0.0101 | [-0.0562, 0.0266] | 0.953741 | 0.953741 | -0.0552 |
| mrr | +0.0086 | [-0.0455, 0.0526] | 0.939891 | 0.939891 | +0.0266 |
| ap | +0.0012 | [-0.0417, 0.0353] | 0.775263 | 0.775263 | -0.0007 |

## Cue strata

| stratum | n | BM25 Hit@1 | SweRank Hit@1 | delta |
|---|---:|---:|---:|---:|
| gold-path cue absent | 1478 | 0.3904 | 0.4005 | +0.0101 |
| gold-path cue present | 313 | 0.4824 | 0.4888 | +0.0064 |
