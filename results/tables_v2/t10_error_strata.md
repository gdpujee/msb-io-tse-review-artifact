# Error analysis by task characteristics

All strata are defined from method-invariant instance attributes. Deltas are paired within stratum.

| stratum | n | BM25 Hit@1 | path-anchor ΔHit@1 | graph ΔHit@1 | BM25 Hit@10 | BM25 MRR |
|---|---:|---:|---:|---:|---:|---:|
| query tokens Q1 (min–89) | 448 | 0.4308 | +0.0201 | -0.1451 | 0.8549 | 0.5665 |
| query tokens Q2 (90–155) | 453 | 0.4040 | +0.0132 | -0.1236 | 0.8433 | 0.5548 |
| query tokens Q3 (156–269) | 443 | 0.4086 | +0.0564 | -0.2032 | 0.8194 | 0.5394 |
| query tokens Q4 (270–max) | 447 | 0.3826 | +0.0313 | -0.1723 | 0.7494 | 0.5012 |
| candidate files Q1 (min–146) | 454 | 0.4405 | +0.0198 | -0.1101 | 0.8943 | 0.5925 |
| candidate files Q2 (147–264) | 447 | 0.3826 | +0.0134 | -0.1723 | 0.7673 | 0.5090 |
| candidate files Q3 (265–509) | 442 | 0.4005 | +0.0520 | -0.2240 | 0.8054 | 0.5297 |
| candidate files Q4 (510–max) | 448 | 0.4018 | +0.0357 | -0.1384 | 0.7991 | 0.5300 |
| gold files = 1 | 953 | 0.4260 | +0.0262 | -0.2361 | 0.8153 | 0.5510 |
| gold files = 2 | 351 | 0.3647 | +0.0256 | -0.1140 | 0.7806 | 0.5006 |
| gold files >= 3 | 487 | 0.3984 | +0.0411 | -0.0472 | 0.8460 | 0.5488 |
| explicit gold-path cue absent | 1478 | 0.3904 | -0.0142 | -0.1482 | 0.8051 | 0.5240 |
| explicit gold-path cue present | 313 | 0.4824 | +0.2396 | -0.2204 | 0.8722 | 0.6186 |
| query source = resolved_issues | 1291 | 0.3950 | +0.0325 | -0.1448 | 0.8102 | 0.5329 |
| query source = problem_statement | 500 | 0.4360 | +0.0240 | -0.2020 | 0.8340 | 0.5604 |
