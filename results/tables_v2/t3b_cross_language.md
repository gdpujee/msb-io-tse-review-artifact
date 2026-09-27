| metric | method | n_langs | n_nonzero | n_positive | n_negative | n_ties | sign_test_p | mean_lang_delta | per_language |
|---|---|---|---|---|---|---|---|---|---|
| hit@1 | anchor_path_graph | 9 | 9 | 3 | 6 | 0 | 0.5078 | -0.0529 | c:-0.094; cpp:+0.016; go:-0.206; java:+0.016; js:-0.024; kotlin:+0.038; python:-0.102; rust:-0.100; ts:-0.020 |
| hit@1 | anchor_path_only | 9 | 9 | 9 | 0 | 0 | 0.0039 | 0.035 | c:+0.047; cpp:+0.023; go:+0.016; java:+0.109; js:+0.012; kotlin:+0.038; python:+0.024; rust:+0.025; ts:+0.020 |
| hit@1 | anchor_symbol_only | 9 | 8 | 4 | 4 | 1 | 1.0 | -0.027 | c:-0.047; cpp:-0.023; go:-0.110; java:+0.016; js:+0.012; kotlin:+0.000; python:+0.002; rust:-0.113; ts:+0.020 |
| hit@1 | bm25_anchor | 9 | 9 | 7 | 2 | 0 | 0.1797 | 0.0127 | c:+0.008; cpp:+0.039; go:-0.077; java:+0.070; js:+0.024; kotlin:+0.038; python:+0.036; rust:-0.084; ts:+0.060 |
| hit@1 | bm25_anchor_graph | 9 | 9 | 3 | 6 | 0 | 0.5078 | -0.0453 | c:-0.078; cpp:+0.008; go:-0.124; java:-0.023; js:+0.024; kotlin:+0.038; python:-0.082; rust:-0.130; ts:-0.040 |
| hit@1 | bm25_graph | 9 | 8 | 0 | 8 | 1 | 0.0078 | -0.1127 | c:-0.164; cpp:-0.078; go:-0.243; java:-0.102; js:-0.024; kotlin:+0.000; python:-0.202; rust:-0.142; ts:-0.060 |
| hit@1 | bm25_path | 9 | 7 | 6 | 1 | 2 | 0.125 | 0.0035 | c:-0.008; cpp:+0.000; go:+0.002; java:+0.008; js:+0.012; kotlin:+0.010; python:+0.004; rust:+0.004; ts:+0.000 |
| hit@10 | anchor_path_graph | 9 | 8 | 2 | 6 | 1 | 0.2891 | -0.0662 | c:-0.133; cpp:+0.008; go:-0.121; java:-0.047; js:+0.000; kotlin:+0.019; python:-0.054; rust:-0.167; ts:-0.100 |
| hit@10 | anchor_path_only | 9 | 7 | 6 | 1 | 2 | 0.125 | 0.0161 | c:+0.062; cpp:+0.016; go:+0.005; java:+0.047; js:+0.000; kotlin:+0.019; python:-0.012; rust:+0.008; ts:+0.000 |
| hit@10 | anchor_symbol_only | 9 | 7 | 2 | 5 | 2 | 0.4531 | -0.0116 | c:-0.016; cpp:+0.016; go:-0.021; java:-0.039; js:+0.024; kotlin:+0.000; python:-0.030; rust:-0.038; ts:+0.000 |
| hit@10 | bm25_anchor | 9 | 8 | 4 | 4 | 1 | 1.0 | 0.0054 | c:+0.055; cpp:+0.031; go:-0.012; java:-0.031; js:+0.012; kotlin:+0.019; python:-0.004; rust:-0.021; ts:+0.000 |
| hit@10 | bm25_anchor_graph | 9 | 9 | 2 | 7 | 0 | 0.1797 | -0.0446 | c:-0.102; cpp:+0.008; go:-0.096; java:-0.031; js:-0.012; kotlin:+0.019; python:-0.016; rust:-0.092; ts:-0.080 |
| hit@10 | bm25_graph | 9 | 8 | 1 | 7 | 1 | 0.0703 | -0.1093 | c:-0.242; cpp:-0.016; go:-0.145; java:-0.164; js:+0.012; kotlin:+0.000; python:-0.084; rust:-0.205; ts:-0.140 |
| hit@10 | bm25_path | 9 | 3 | 2 | 1 | 6 | 1.0 | 0.0015 | c:+0.000; cpp:+0.000; go:+0.000; java:+0.008; js:+0.000; kotlin:+0.010; python:+0.000; rust:-0.004; ts:+0.000 |
| mrr | anchor_path_graph | 9 | 9 | 1 | 8 | 0 | 0.0391 | -0.0592 | c:-0.105; cpp:-0.015; go:-0.178; java:-0.000; js:-0.029; kotlin:+0.031; python:-0.084; rust:-0.119; ts:-0.032 |
| mrr | anchor_path_only | 9 | 9 | 9 | 0 | 0 | 0.0039 | 0.0318 | c:+0.058; cpp:+0.032; go:+0.014; java:+0.086; js:+0.009; kotlin:+0.031; python:+0.019; rust:+0.022; ts:+0.016 |
| mrr | anchor_symbol_only | 9 | 8 | 4 | 4 | 1 | 1.0 | -0.019 | c:-0.040; cpp:-0.002; go:-0.095; java:+0.020; js:+0.015; kotlin:+0.000; python:+0.010; rust:-0.103; ts:+0.025 |
| mrr | bm25_anchor | 9 | 9 | 7 | 2 | 0 | 0.1797 | 0.014 | c:+0.023; cpp:+0.046; go:-0.068; java:+0.053; js:+0.021; kotlin:+0.031; python:+0.042; rust:-0.074; ts:+0.052 |
| mrr | bm25_anchor_graph | 9 | 9 | 1 | 8 | 0 | 0.0391 | -0.0483 | c:-0.093; cpp:-0.001; go:-0.117; java:-0.033; js:-0.004; kotlin:+0.031; python:-0.049; rust:-0.129; ts:-0.039 |
| mrr | bm25_graph | 9 | 8 | 0 | 8 | 1 | 0.0078 | -0.1136 | c:-0.190; cpp:-0.083; go:-0.213; java:-0.121; js:-0.028; kotlin:+0.000; python:-0.168; rust:-0.159; ts:-0.061 |
| mrr | bm25_path | 9 | 9 | 8 | 1 | 0 | 0.0391 | 0.0025 | c:-0.004; cpp:+0.000; go:+0.002; java:+0.004; js:+0.008; kotlin:+0.007; python:+0.004; rust:+0.002; ts:+0.000 |
