#!/usr/bin/env python3
"""Analyse the leaked-query contrast (RQ6): what is the leak worth?

Reads the treatment arm produced by ``run_leak_contrast.py`` and the released
control arm, pairs them instance by instance, and reports the difference under
the same statistics used everywhere else in the paper.

Before reporting anything, this script re-establishes that the two arms are
comparable, because the whole claim rests on the manipulation being singular:

* the instance sets must be identical;
* the control rows must carry ``issue_only_v2`` and the treatment rows
  ``legacy_mixed_v1``, so neither file is a leftover of the other;
* every treatment row's ``query_sha256`` must equal the audited hash of the
  superseded query for that instance -- the row was scored on the query that
  ``audit_query_leakage.py`` proved byte-exact, not on an approximation;
* every control row's ``query_sha256`` must equal the hash of the released
  issue-only query for that instance.

The strata are the point of the design.  The superseded rule differs from the
released one in two different ways, and only one of them adds post-solution
information:

  non_python (n=1,291)  the treatment query adds the pull-request title, and for
                        most instances the pull-request body.  This is the leak.
  python     (n=500)    the pull-request fields are the literal string
                        "placeholder", so the treatment query is the *same issue
                        text repeated* under a synthetic "Issue #0 body:"
                        header.  No post-solution information is added.  This is
                        the information-matched control: if it moved as much as
                        the non-Python stratum, the effect would be explained by
                        query length rather than by leakage.

Outputs ``results/tables_v2/t12_leak_contrast.{md,json}``.
"""
from __future__ import annotations

import glob
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

import audit_query_leakage as aql  # noqa: E402
import dataset  # noqa: E402
from stats_v2 import compare_methods  # noqa: E402

CONTROL_DIR = ROOT / "results" / "raw_v2"
TREAT_DIR = ROOT / "results" / "contrast_leaky_v1"
OUT = ROOT / "results" / "tables_v2" / "t12_leak_contrast.md"
CONTROL_PROTOCOL = "issue_only_v2"
TREATMENT_PROTOCOL = "legacy_mixed_v1"
METHODS = ["bm25", "bm25_path", "anchor_path_only", "anchor_symbol_only",
           "bm25_anchor", "bm25_graph", "bm25_anchor_graph", "anchor_path_graph"]
METRICS = ["hit@1", "hit@10", "mrr", "ap"]


def load(dirname: Path, protocol: str) -> tuple[list[dict], dict]:
    out, markers = [], {}
    for path in sorted(glob.glob(str(dirname / "main_*.jsonl"))):
        for line in open(path):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("query_protocol") != protocol:
                raise RuntimeError(f"{path}: row carries {row.get('query_protocol')}")
            out.append(row)
        marker = Path(str(path) + ".done")
        if marker.exists():
            doc = json.loads(marker.read_text())
            if doc.get("query_protocol") != protocol:
                raise RuntimeError(f"{marker}: marker protocol {doc.get('query_protocol')}")
            markers[Path(path).stem] = doc
    if not out:
        raise RuntimeError(f"no rows under {dirname} for protocol {protocol}")
    return out, markers


def main() -> None:
    control, _ = load(CONTROL_DIR, CONTROL_PROTOCOL)
    treat, treat_markers = load(TREAT_DIR, TREATMENT_PROTOCOL)
    if not treat_markers:
        raise RuntimeError("treatment arm has no completion markers")

    control = [r for r in control if r["method"] in METHODS]
    treat = [r for r in treat if r["method"] in METHODS]
    if not control or not treat:
        raise RuntimeError("an arm is empty after filtering to the shared method set")

    def key(row: dict) -> tuple[str, str, str]:
        return (row["lang"], row["instance_id"], row["method"])

    ck = {key(r) for r in control}
    tk = {key(r) for r in treat}
    if ck != tk:
        raise RuntimeError(f"arms differ: {len(ck - tk)} control-only, {len(tk - ck)} treatment-only")

    # ---- provenance: every row was scored on the query we audited ----------
    audited = json.loads(aql.LEGACY_HASHES.read_text(encoding="utf-8"))
    released = {i.instance_id: hashlib.sha256(i.query.encode()).hexdigest()
                for i in dataset.load_all()}
    checked_t = checked_c = 0
    for row in treat:
        want = audited.get(row["instance_id"])
        if want is None:
            raise RuntimeError(f"{row['instance_id']} absent from the audited hash set")
        if row.get("query_sha256") != want:
            raise RuntimeError(f"{row['instance_id']}: treatment row is not the audited query")
        checked_t += 1
    for row in control:
        want = released.get(row["instance_id"])
        if want is None or row.get("query_sha256") != want:
            raise RuntimeError(f"{row['instance_id']}: control row is not the released query")
        checked_c += 1

    # ---- the premise of the strata, measured rather than assumed -----------
    corpus = aql.load_raw_corpus()
    instances = {i.instance_id: i for i in dataset.load_all()}
    py_repeat = py_pr_text = nonpy_pr_text = nonpy_total = 0
    py_placeholder = 0
    for iid, inst in instances.items():
        row = corpus[iid]["row"]
        v1 = aql.legacy_query(row)
        if inst.lang == "python":
            # the treatment query must be the issue text repeated, with no PR text
            if v1 == inst.query + "\n\n" + "Issue #0 body: " + inst.query:
                py_repeat += 1
            title = (row.get("title") or "").strip()
            body = (row.get("body") or "").strip()
            # The section states that the Python rows hold the literal string
            # "placeholder" in both fields.  That is a claim about the data, so
            # it is counted here rather than inferred from the equality above.
            if title == "placeholder" and body == "placeholder":
                py_placeholder += 1
            placeholder = {"placeholder", "none", "n/a", ""}
            if (title.lower() not in placeholder and title in v1) or \
               (body.lower() not in placeholder and body in v1):
                py_pr_text += 1
        else:
            nonpy_total += 1
            title = (row.get("title") or "").strip()
            if title and title in v1:
                nonpy_pr_text += 1

    # ---- paired comparisons, per method and per stratum -------------------
    combined: list[dict] = []
    for row in control:
        combined.append({**row, "arm_method": row["method"], "method": "control",
                         "stratum": "python" if row["lang"] == "python" else "non_python"})
    for row in treat:
        combined.append({**row, "arm_method": row["method"], "method": "treatment",
                         "stratum": "python" if row["lang"] == "python" else "non_python"})

    results: list[dict] = []
    for method in METHODS:
        for stratum in ("all", "python", "non_python"):
            sub = [r for r in combined if r["arm_method"] == method
                   and (stratum == "all" or r["stratum"] == stratum)]
            for metric in METRICS:
                for item in compare_methods(sub, metric, "control", ["treatment"]):
                    results.append({**item, "arm_method": method, "stratum": stratum})

    # ---- per-language detail for the headline method ---------------------
    per_language: list[dict] = []
    for lang in sorted({r["lang"] for r in combined}):
        sub = [r for r in combined if r["lang"] == lang and r["arm_method"] == "bm25"]
        item = compare_methods(sub, "hit@1", "control", ["treatment"])[0]
        per_language.append({"lang": lang, **item})

    # ---- render -----------------------------------------------------------
    lines = ["# What the leaked query is worth (RQ6)", "",
             "Treatment = the superseded query rule, control = the released issue-only",
             "rule. Both arms were produced by the same pipeline over the same indexes,",
             "candidate protocol, method configurations, and metrics; only the query",
             "differs. Delta is treatment minus control.", ""]
    for method in METHODS:
        rows_here = [r for r in results if r["arm_method"] == method]
        if not rows_here:
            continue
        lines += [f"## {method}", "",
                  "| stratum | metric | n | control | treatment | delta | "
                  "repository-cluster 95% CI | p_repo_Holm | rank-biserial |",
                  "|---|---|---:|---:|---:|---:|---|---:|---:|"]
        for stratum in ("all", "python", "non_python"):
            for item in rows_here:
                if item["stratum"] != stratum:
                    continue
                lines.append(
                    f"| {stratum} | {item['metric']} | {item['n_paired']} | "
                    f"{item['mean_ref']:.4f} | {item['mean_method']:.4f} | "
                    f"{item['delta']:+.4f} | {item['delta_cluster_bootstrap_95ci']} | "
                    f"{item['p_cluster_holm']:.6g} | {item['rank_biserial']:+.4f} |")
        lines.append("")
    lines += ["## bm25 Hit@1 by language", "",
              "| language | n | control | treatment | delta | CI | p_repo_Holm |",
              "|---|---:|---:|---:|---:|---|---:|"]
    for item in per_language:
        lines.append(
            f"| {item['lang']} | {item['n_paired']} | {item['mean_ref']:.4f} | "
            f"{item['mean_method']:.4f} | {item['delta']:+.4f} | "
            f"{item['delta_cluster_bootstrap_95ci']} | {item['p_cluster_holm']:.6g} |")
    lines.append("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.with_suffix(".json").write_text(json.dumps({
        "protocols": {"control": CONTROL_PROTOCOL, "treatment": TREATMENT_PROTOCOL},
        "rows": {"control": len(control), "treatment": len(treat)},
        "query_hashes_checked": {"treatment": checked_t, "control": checked_c},
        "premise": {
            "python_instances": sum(1 for i in instances.values() if i.lang == "python"),
            "python_treatment_is_repeated_issue_text": py_repeat,
            "python_treatment_contains_pr_text": py_pr_text,
            "python_pr_fields_are_placeholder_literal": py_placeholder,
            "non_python_instances": nonpy_total,
            "non_python_treatment_contains_pr_title": nonpy_pr_text,
        },
        "comparisons": results,
        "bm25_hit1_by_language": per_language,
    }, indent=2) + "\n")
    print(OUT)
    for item in per_language:
        print(f"  {item['lang']:8s} n={item['n_paired']:5d} "
              f"control={item['mean_ref']:.4f} treatment={item['mean_method']:.4f} "
              f"delta={item['delta']:+.4f}")


if __name__ == "__main__":
    main()
