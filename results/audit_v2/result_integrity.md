# Protocol V2 Result Integrity

- Status: **VERIFIED**
- Rows: 14328
- Instances: 1791
- Languages: 9
- Repositories: 57
- Errors: 0

## Independently recomputed matched deltas

| Contrast | Hit@1 | Hit@10 | MRR |
|---|---:|---:|---:|
| bm25_path-minus-bm25 | +0.0034 | +0.0006 | +0.0025 |
| anchor_path_only-minus-bm25 | +0.0302 | +0.0089 | +0.0268 |
| anchor_symbol_only-minus-bm25 | -0.0436 | -0.0201 | -0.0339 |
| bm25_graph-minus-bm25 | -0.1608 | -0.1189 | -0.1501 |
| bm25_anchor_graph-minus-bm25_anchor | -0.0681 | -0.0491 | -0.0660 |
| anchor_path_graph-minus-anchor_path_only | -0.1251 | -0.0893 | -0.1179 |

## Explicit gold-path cue stratification

| Cue | n | Hit@1 delta | Hit@10 delta | MRR delta |
|---|---:|---:|---:|---:|
| absent | 1478 | -0.0142 | -0.0101 | -0.0111 |
| present | 313 | +0.2396 | +0.0990 | +0.2056 |
