#!/usr/bin/env python3
"""Analyze the completed SweRankEmbed reranking baseline against BM25."""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from dataset import TEST_FILTER_PROTOCOL  # noqa: E402
from evaluate import METRIC_PROTOCOL  # noqa: E402
from stats_v2 import compare_methods  # noqa: E402

DENSE = ROOT / "results" / "raw_v2" / "swerank_all.jsonl"
DONE = DENSE.with_name(DENSE.name + ".done")
OUT = ROOT / "results" / "tables_v2" / "t11_swerank_reranker.md"
METHOD = "bm25_swerank_rerank50"


def mean(rows: list[dict], key: str) -> float:
    return sum(row[key] for row in rows) / len(rows)


def main() -> None:
    if not DONE.exists():
        raise RuntimeError("dense run has no completion marker")
    done = json.loads(DONE.read_text())
    dense = [json.loads(line) for line in DENSE.open() if line.strip()]
    if len(dense) != done["rows"] or len(dense) != 1791:
        raise RuntimeError(f"incomplete dense result: {len(dense)}")
    ids = {(row["lang"], row["instance_id"]) for row in dense}
    if len(ids) != len(dense):
        raise RuntimeError("duplicate dense instances")
    if any(row["method"] != METHOD or row["query_protocol"] != "issue_only_v2" or
           row.get("candidate_protocol") != TEST_FILTER_PROTOCOL or
           row.get("metric_protocol") != METRIC_PROTOCOL for row in dense):
        raise RuntimeError("dense protocol/config mismatch")

    bm25 = []
    for filename in glob.glob(str(ROOT / "results" / "raw_v2" / "main_*.jsonl")):
        for line in open(filename):
            row = json.loads(line)
            if row["method"] == "bm25" and (row["lang"], row["instance_id"]) in ids:
                bm25.append(row)
    if len(bm25) != len(dense):
        raise RuntimeError(f"BM25 join mismatch: {len(bm25)}")

    rows = bm25 + dense
    comparisons = []
    for metric in ("hit@1", "hit@10", "mrr", "ap"):
        comparisons.extend(compare_methods(rows, metric, "bm25", [METHOD]))

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["lang"], row["method"])].append(row)
        groups[("ALL", row["method"])].append(row)
    lines = ["# SweRankEmbed-Small reranking baseline", "",
             "BM25 retrieves 50 files; the pinned 137M SweRankEmbed-Small model reranks only that head.",
             "Documents use the official 512-token setting. The BM25 tail remains unchanged.", "",
             "| language | method | n | Hit@1 | Hit@10 | MRR | AP | mean seconds |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    lang_order = ["c", "cpp", "go", "java", "js", "kotlin", "python", "rust", "ts", "ALL"]
    for lang in lang_order:
        for method in ("bm25", METHOD):
            subset = groups[(lang, method)]
            lines.append(f"| {lang} | {method} | {len(subset)} | {mean(subset, 'hit@1'):.4f} | "
                         f"{mean(subset, 'hit@10'):.4f} | {mean(subset, 'mrr'):.4f} | "
                         f"{mean(subset, 'ap'):.4f} | {mean(subset, 'secs'):.3f} |")
    lines.extend(["", "## Paired comparison (all instances)", "",
                  "| metric | delta | repository-cluster 95% CI | p_repo | p_repo_Holm | rank-biserial |",
                  "|---|---:|---|---:|---:|---:|"])
    for item in comparisons:
        lines.append(f"| {item['metric']} | {item['delta']:+.4f} | "
                     f"{item['delta_cluster_bootstrap_95ci']} | {item['p_cluster']:.6g} | "
                     f"{item['p_cluster_holm']:.6g} | "
                     f"{item['rank_biserial']:+.4f} |")
    lines.extend(["", "## Cue strata", "",
                  "| stratum | n | BM25 Hit@1 | SweRank Hit@1 | delta |",
                  "|---|---:|---:|---:|---:|"])
    dense_by_id = {(row["lang"], row["instance_id"]): row for row in dense}
    bm25_by_id = {(row["lang"], row["instance_id"]): row for row in bm25}
    cue_rows = []
    for cue in (False, True):
        selected = [iid for iid, row in bm25_by_id.items() if row["query_mentions_gold_path"] == cue]
        base = [bm25_by_id[iid] for iid in selected]
        model = [dense_by_id[iid] for iid in selected]
        cue_rows.append({
            "stratum": "present" if cue else "absent",
            "n": len(selected),
            "bm25_hit1": mean(base, "hit@1"),
            "model_hit1": mean(model, "hit@1"),
            "delta": mean(model, "hit@1") - mean(base, "hit@1"),
        })
        lines.append(f"| gold-path cue {cue_rows[-1]['stratum']} | {len(selected)} | "
                     f"{mean(base, 'hit@1'):.4f} | {mean(model, 'hit@1'):.4f} | "
                     f"{mean(model, 'hit@1') - mean(base, 'hit@1'):+.4f} |")

    # Per-language panel, plus the sign test the manuscript quotes.  The
    # per-language means are descriptive (two panels have 2-5 repositories), so
    # the count of directions is reported as a count and the test is exact.
    per_language = []
    for lang in lang_order:
        if lang == "ALL":
            continue
        base, model = groups[(lang, "bm25")], groups[(lang, METHOD)]
        per_language.append({
            "lang": lang, "n": len(base),
            "bm25_hit1": mean(base, "hit@1"), "model_hit1": mean(model, "hit@1"),
            "bm25_hit10": mean(base, "hit@10"), "model_hit10": mean(model, "hit@10"),
            "bm25_mrr": mean(base, "mrr"), "model_mrr": mean(model, "mrr"),
            "bm25_secs": mean(base, "secs"), "model_secs": mean(model, "secs"),
        })
    up = sum(1 for r in per_language if r["model_hit1"] > r["bm25_hit1"])
    down = sum(1 for r in per_language if r["model_hit1"] < r["bm25_hit1"])
    tied = len(per_language) - up - down
    sign_test_p = float(binomtest(min(up, down), up + down, 0.5).pvalue)
    all_base, all_model = groups[("ALL", "bm25")], groups[("ALL", METHOD)]

    OUT.write_text("\n".join(lines) + "\n")
    OUT.with_suffix(".json").write_text(json.dumps({
        "done": done, "comparisons": comparisons,
        "per_language": per_language,
        "cue_strata": cue_rows,
        "sign_test": {"languages": len(per_language), "up": up, "down": down,
                      "tied": tied, "p_two_sided_exact": sign_test_p},
        "aggregate": {
            "n": len(all_base),
            "bm25": {k: mean(all_base, k) for k in ("hit@1", "hit@10", "hit@50", "mrr", "ap", "secs")},
            "model": {k: mean(all_model, k) for k in ("hit@1", "hit@10", "hit@50", "mrr", "ap", "secs")},
        },
    }, indent=2) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
