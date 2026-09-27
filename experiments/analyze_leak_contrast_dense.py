#!/usr/bin/env python3
"""Analyse the dense treatment arm: is the leak worth more to a neural reranker?

``analyze_leak_contrast.py`` measures what the superseded query rule is worth to
eight sparse and structural configurations.  This script answers the follow-up
question for the one method most likely to consume the leaked material, because
that material is natural language: the pull-request title and body.

Three things are reported, and they are not the same thing:

1. the paired effect of the query rule *on the dense method* — the same
   comparison the lexical analysis performs, with the same statistics;
2. the difference-in-differences against BM25, i.e. whether the dense method's
   sensitivity to the query rule exceeds the lexical baseline's.  This is the
   only claim that bears on pre-registered prediction P4, and it is computed
   per instance and clustered by repository rather than compared as two
   separately estimated numbers;
3. the structural caveat that makes (1) an upper bound relative to the lexical
   arm: the dense method reranks BM25's top-50, so its treatment arm changes the
   candidate head as well as the text used to rerank it.

Before reporting anything it re-establishes comparability: identical instance
sets, the expected protocol identifier on each arm, matching model and
configuration revisions, and a per-row query hash equal to the audited hash for
that arm.

Outputs ``results/tables_v2/t13_dense_leak_contrast.{md,json}``.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

import audit_query_leakage as aql  # noqa: E402
import dataset  # noqa: E402
from stats_v2 import (cluster_bootstrap_delta, compare_methods, paired_test,  # noqa: E402
                      rank_biserial)

CONTROL = ROOT / "results" / "raw_v2" / "swerank_all.jsonl"
TREATMENT = ROOT / "results" / "contrast_leaky_dense_v1" / "swerank_all.jsonl"
OUT = ROOT / "results" / "tables_v2" / "t13_dense_leak_contrast.md"
CONTROL_PROTOCOL = "issue_only_v2"
TREATMENT_PROTOCOL = "legacy_mixed_v1"
METRICS = ("hit@1", "hit@10", "mrr", "ap")


def load(path: Path, protocol: str) -> tuple[list[dict], dict]:
    if not path.exists():
        raise SystemExit(f"missing arm: {path}")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"empty arm: {path}")
    bad = {row.get("query_protocol") for row in rows} - {protocol}
    if bad:
        raise SystemExit(f"{path} carries unexpected protocols: {sorted(bad)}")
    marker = path.with_name(path.name + ".done")
    if not marker.exists():
        raise SystemExit(f"arm is not marked complete: {marker}")
    return rows, json.loads(marker.read_text())


def index(rows: list[dict]) -> dict:
    return {(row["lang"], row["instance_id"]): row for row in rows}


def lexical_arm(directory: Path, protocol: str) -> list[dict]:
    """The BM25 rows of a lexical arm, keyed by instance."""
    import glob
    rows: list[dict] = []
    for path in sorted(glob.glob(str(directory / "main_*.jsonl"))):
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("query_protocol") != protocol:
                raise SystemExit(f"{path}: row carries {row.get('query_protocol')}")
            if row.get("method") == "bm25":
                rows.append(row)
    if not rows:
        raise SystemExit(f"no bm25 rows under {directory} for {protocol}")
    return rows


def main() -> None:
    control, control_done = load(CONTROL, CONTROL_PROTOCOL)
    treat, treat_done = load(TREATMENT, TREATMENT_PROTOCOL)

    # ---- comparability, before anything is reported ----------------------
    for key in ("method", "model_id", "model_revision", "remote_code_revision",
                "candidate_k", "max_seq_length", "candidate_protocol",
                "metric_protocol"):
        if control_done.get(key) != treat_done.get(key):
            raise SystemExit(f"arms differ on {key}: "
                             f"{control_done.get(key)!r} vs {treat_done.get(key)!r}")
    for key in ("cap", "limit"):
        if control_done.get(key) or treat_done.get(key):
            raise SystemExit(f"an arm was {key}ed")

    ck = {(row["lang"], row["instance_id"]) for row in control}
    tk = {(row["lang"], row["instance_id"]) for row in treat}
    if ck != tk:
        raise SystemExit(f"arms do not pair: {len(ck - tk)} control-only, "
                         f"{len(tk - ck)} treatment-only")

    audited = json.loads(aql.LEGACY_HASHES.read_text(encoding="utf-8"))
    released = {inst.instance_id: hashlib.sha256(inst.query.encode()).hexdigest()
                for inst in dataset.load_all()}
    for row in treat:
        if row.get("query_sha256") != audited.get(row["instance_id"]):
            raise SystemExit(f"{row['instance_id']}: treatment row is not the audited query")
    for row in control:
        if row.get("query_sha256") != released.get(row["instance_id"]):
            raise SystemExit(f"{row['instance_id']}: control row is not the released query")

    def stratum_of(lang: str) -> str:
        return "python" if lang == "python" else "non_python"

    combined: list[dict] = []
    for row in control:
        combined.append({**row, "method": "control", "stratum": stratum_of(row["lang"])})
    for row in treat:
        combined.append({**row, "method": "treatment", "stratum": stratum_of(row["lang"])})

    results: list[dict] = []
    for stratum in ("all", "non_python", "python"):
        sub = [row for row in combined
               if stratum == "all" or row["stratum"] == stratum]
        for metric in METRICS:
            for item in compare_methods(sub, metric, "control", ["treatment"]):
                results.append({**item, "stratum": stratum})

    # ---- difference-in-differences against BM25 --------------------------
    # The two arms of each method are paired on the same instances, so the
    # per-instance DiD is well defined and can be tested directly rather than
    # by subtracting two independently estimated means.  The lexical arms are
    # read from their own row files: the released contrast table holds only
    # aggregates, and a DiD needs the instances.
    bm25_ctrl = index(lexical_arm(ROOT / "results" / "raw_v2", CONTROL_PROTOCOL))
    bm25_treat = index(lexical_arm(ROOT / "results" / "contrast_leaky_v1",
                                   TREATMENT_PROTOCOL))
    dense_ctrl = {(row["lang"], row["instance_id"]): row for row in control}
    dense_treat = {(row["lang"], row["instance_id"]): row for row in treat}

    did: list[dict] = []
    for stratum in ("all", "non_python", "python"):
        values, clusters = [], []
        for key in sorted(dense_ctrl):
            if stratum != "all" and stratum_of(key[0]) != stratum:
                continue
            if key not in bm25_ctrl or key not in bm25_treat:
                raise SystemExit(f"BM25 lexical arm is missing {key}")
            dense_gain = dense_treat[key]["hit@1"] - dense_ctrl[key]["hit@1"]
            bm25_gain = bm25_treat[key]["hit@1"] - bm25_ctrl[key]["hit@1"]
            values.append(dense_gain - bm25_gain)
            clusters.append((key[0], dense_ctrl[key]["repo"]))
        if not values:
            continue
        p_value, test, n_informative = paired_test(values, [0.0] * len(values), "mrr")
        ci = cluster_bootstrap_delta(values, clusters)
        did.append({
            "stratum": stratum, "n_paired": len(values),
            "n_clusters": len(set(clusters)),
            "mean_did": round(sum(values) / len(values), 4),
            "ci": [round(ci[0], 4), round(ci[1], 4)],
            "p": p_value, "test": test, "n_test_informative": n_informative,
            "rank_biserial": round(rank_biserial(values, [0.0] * len(values)), 4),
            "n_positive": sum(1 for value in values if value > 1e-12),
            "n_negative": sum(1 for value in values if value < -1e-12),
        })

    # ---- render ----------------------------------------------------------
    lines = ["# The dense reranker under the superseded query rule", "",
             f"Control = the released issue-only rule; treatment = the superseded rule.",
             f"Both arms use `{control_done['method']}` with model revision",
             f"`{control_done['model_revision']}`, candidate_k = {control_done['candidate_k']},",
             f"max_seq_length = {control_done['max_seq_length']}. Delta is treatment minus",
             "control, paired by instance.", "",
             "| stratum | metric | n | issue-only | superseded | delta | "
             "repository-cluster 95% CI | p | rank-biserial |",
             "|---|---|---:|---:|---:|---:|---|---:|---:|"]
    for stratum in ("all", "non_python", "python"):
        for item in results:
            if item["stratum"] != stratum:
                continue
            lines.append(
                f"| {stratum} | {item['metric']} | {item['n_paired']} | "
                f"{item['mean_ref']:.4f} | {item['mean_method']:.4f} | "
                f"{item['delta']:+.4f} | {item['delta_cluster_bootstrap_95ci']} | "
                f"{item['p_cluster_holm']:.6g} | {item['rank_biserial']:+.4f} |")
    lines += ["", "## Difference-in-differences against BM25 (Hit@1)", "",
              "Per instance: (dense superseded - dense issue-only) - "
              "(BM25 superseded - BM25 issue-only).", "",
              "| stratum | n | clusters | mean DiD | 95% CI | p | rank-biserial | "
              "instances up | instances down |",
              "|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for item in did:
        lines.append(
            f"| {item['stratum']} | {item['n_paired']} | {item['n_clusters']} | "
            f"{item['mean_did']:+.4f} | {item['ci']} | {item['p']:.6g} | "
            f"{item['rank_biserial']:+.4f} | {item['n_positive']} | {item['n_negative']} |")
    lines.append("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.with_suffix(".json").write_text(json.dumps({
        "protocols": {"control": CONTROL_PROTOCOL, "treatment": TREATMENT_PROTOCOL},
        "rows": {"control": len(control), "treatment": len(treat)},
        "configuration": {key: control_done.get(key) for key in
                          ("method", "model_id", "model_revision",
                           "remote_code_revision", "candidate_k", "max_seq_length",
                           "candidate_protocol", "metric_protocol")},
        "comparisons": results,
        "difference_in_differences": did,
    }, indent=2) + "\n")
    print(OUT)
    for item in results:
        if item["metric"] == "hit@1":
            print(f"  {item['stratum']:11s} n={item['n_paired']:5d} "
                  f"{item['mean_ref']:.4f} -> {item['mean_method']:.4f} "
                  f"({item['delta']:+.4f}) p={item['p_cluster_holm']:.4g}")
    for item in did:
        print(f"  DiD {item['stratum']:11s} {item['mean_did']:+.4f} "
              f"CI {item['ci']} p={item['p']:.4g}")


if __name__ == "__main__":
    main()
