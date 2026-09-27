#!/usr/bin/env bash
# Full, uncapped Protocol V2 evaluation. One output per language is resumable.
set -euo pipefail

cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUT_DIR="../results/raw_v2"
LOG_DIR="../results/logs_v2"
METHODS=(bm25 bm25_path anchor_path_only anchor_symbol_only bm25_anchor bm25_graph bm25_anchor_graph anchor_path_graph)
mkdir -p "$OUT_DIR" "$LOG_DIR"

for lang in c cpp go java js kotlin python rust ts; do
  out="$OUT_DIR/main_${lang}.jsonl"
  done_file="$out.done"
  if [[ -f "$done_file" ]] && "$PYTHON_BIN" - "$done_file" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
expected = {
    "bm25", "bm25_path", "anchor_path_only", "anchor_symbol_only",
    "bm25_anchor", "bm25_graph", "bm25_anchor_graph", "anchor_path_graph",
}
assert doc.get("query_protocol") == "issue_only_v2"
assert doc.get("candidate_protocol") == "component_aware_test_filter_v6"
# metric_protocol must be checked too: it was added to evaluate.py after the first
# six languages had already been produced, so a guard that ignores it will silently
# skip files computed by an older metric implementation and mix two metric
# definitions inside one result set.  See FAILURES F017.
assert doc.get("metric_protocol") == "full_precision_metrics_v1"
assert set(doc.get("methods", [])) == expected
assert doc.get("cap") == 0
PY
  then
    echo "=== $lang: verified V2 result exists; skipping ==="
    continue
  fi
  echo "=== $lang: starting $(date -Iseconds) ==="
  "$PYTHON_BIN" -u run_experiment.py --langs "$lang" --methods "${METHODS[@]}" \
    --out "$out" 2>&1 | tee "$LOG_DIR/main_${lang}.log"
  echo "=== $lang: finished $(date -Iseconds) ==="
done
