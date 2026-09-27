#!/usr/bin/env python3
"""RQ7: does the query rule change *which* configuration wins, or only by how much?

Section 5.7 measures the cost of the leak as a score difference on a single
baseline.  A reader who takes a published *comparison* at face value cares about a
different question: if the leak is present, does the ordering of configurations
change?  A uniform score shift would leave every comparative conclusion intact; a
configuration-dependent shift would not.

Both arms already exist, so this is a re-reading of released results rather than
a new experiment: the same 8 configurations on the same 1,791 instances, scored
once under the issue-only rule (``results/raw_v2``) and once under the
superseded rule (``results/contrast_leaky_v1``).  Nothing is re-run.

What is reported
----------------
1. per-configuration means under both rules, with a repository-clustered
   interval for the shift;
2. the two orderings, and their agreement (Spearman rho, Kendall tau) with a
   repository-cluster bootstrap interval for rho;
3. every pair whose difference changes sign, with the paired interval under both
   rules, so a flip between two indistinguishable configurations is not read as
   a reversal;
4. the mechanism check: whether the leaked query mentions the gold file path
   more often, which is what a configuration exploiting identifier overlap would
   need in order to gain.

Guards
------
The two arms must cover the same ``(method, instance_id)`` key set and each must
carry its own protocol identifier; a mismatch aborts rather than averaging
across rules.  Rank agreement over 8 configurations is coarse (tau moves in
steps of 1/28), which is stated in the output rather than left implicit.
"""
from __future__ import annotations

import glob
import itertools
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from stats_v2 import cluster_bootstrap_delta, compare_methods  # noqa: E402

CONTROL_DIR = ROOT / "results" / "raw_v2"
TREAT_DIR = ROOT / "results" / "contrast_leaky_v1"
CONTROL_PROTOCOL = "issue_only_v2"
TREAT_PROTOCOL = "legacy_mixed_v1"
OUT_MD = ROOT / "results" / "tables_v2" / "t14_leak_ranking.md"
OUT_JSON = ROOT / "results" / "tables_v2" / "t14_leak_ranking.json"

METHODS = [
    "bm25", "bm25_path", "anchor_path_only", "anchor_symbol_only",
    "bm25_anchor", "bm25_graph", "bm25_anchor_graph", "anchor_path_graph",
]
METRICS = ("hit@1", "mrr")
N_BOOT = 10000
SEED = 42


def load(directory: Path, protocol: str) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for path in sorted(glob.glob(str(directory / "main_*.jsonl"))):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("query_protocol") != protocol:
                raise SystemExit(
                    f"{Path(path).name}: expected {protocol!r}, "
                    f"found {row.get('query_protocol')!r}")
            if row["method"] in METHODS:
                out[(row["method"], row["instance_id"])] = row
    return out


def cluster_of(row: dict) -> tuple:
    return (row.get("lang"), row["repo"])


def spearman(rank_a: dict, rank_b: dict) -> float:
    n = len(rank_a)
    d2 = sum((rank_a[m] - rank_b[m]) ** 2 for m in rank_a)
    return 1 - 6 * d2 / (n * (n * n - 1))


def kendall(rank_a: dict, rank_b: dict) -> tuple[float, int, int]:
    concordant = discordant = 0
    for x, y in itertools.combinations(sorted(rank_a), 2):
        same = (rank_a[x] < rank_a[y]) == (rank_b[x] < rank_b[y])
        concordant += same
        discordant += not same
    return (concordant - discordant) / (concordant + discordant), concordant, discordant


def main() -> int:
    control = load(CONTROL_DIR, CONTROL_PROTOCOL)
    treat = load(TREAT_DIR, TREAT_PROTOCOL)
    if set(control) != set(treat):
        raise SystemExit(
            f"arms do not pair: {len(set(control) - set(treat))} control-only, "
            f"{len(set(treat) - set(control))} treatment-only")
    instances = sorted({key[1] for key in control})
    clusters = {key[1]: cluster_of(control[key]) for key in control}
    n_clusters = len(set(clusters.values()))
    print(f"paired rows: {len(control):,} across {len(METHODS)} configurations "
          f"and {len(instances):,} instances in {n_clusters} repository clusters")

    # ---- 1. per-configuration means and shifts ---------------------------
    per_method = {}
    for method in METHODS:
        entry = {"n": 0}
        for metric in METRICS:
            base = [control[(method, i)][metric] for i in instances]
            shift = [treat[(method, i)][metric] for i in instances]
            diffs = [t - b for t, b in zip(shift, base)]
            keys = [clusters[i] for i in instances]
            lo, hi = cluster_bootstrap_delta(diffs, keys, n_boot=N_BOOT, seed=SEED)
            entry[metric] = {
                "control": statistics.fmean(base),
                "treatment": statistics.fmean(shift),
                "delta": statistics.fmean(diffs),
                "delta_ci": [lo, hi],
            }
            entry["n"] = len(base)
        per_method[method] = entry

    # ---- 2. the two orderings and their agreement -------------------------
    ordering: dict[str, dict] = {}
    agreement: dict[str, dict] = {}
    for metric in METRICS:
        order_c = sorted(METHODS, key=lambda m: per_method[m][metric]["control"],
                         reverse=True)
        order_t = sorted(METHODS, key=lambda m: per_method[m][metric]["treatment"],
                         reverse=True)
        rank_c = {m: i for i, m in enumerate(order_c)}
        rank_t = {m: i for i, m in enumerate(order_t)}
        rho = spearman(rank_c, rank_t)
        tau, concordant, discordant = kendall(rank_c, rank_t)

        # repository-cluster bootstrap interval for rho: resample clusters,
        # recompute both orderings on the resampled instances, recompute rho.
        # Vectorised, because 10,000 draws x 16 method means is not something to
        # do in a Python loop.
        import numpy as np

        by_cluster: dict[tuple, list[int]] = {}
        for position, iid in enumerate(instances):
            by_cluster.setdefault(clusters[iid], []).append(position)
        cluster_keys = sorted(by_cluster, key=str)
        cluster_slices = [np.asarray(by_cluster[key], dtype=np.int64)
                          for key in cluster_keys]
        matrices = {
            arm: np.asarray([[rows[(method, iid)][metric] for iid in instances]
                             for method in METHODS], dtype=np.float64)
            for arm, rows in (("control", control), ("treatment", treat))
        }
        rng = np.random.default_rng(SEED)
        draws = rng.integers(0, len(cluster_keys), size=(N_BOOT, len(cluster_keys)))
        rhos = np.empty(N_BOOT, dtype=np.float64)
        for b in range(N_BOOT):
            picked = np.concatenate([cluster_slices[c] for c in draws[b]])
            ranks = {}
            for arm in ("control", "treatment"):
                means = matrices[arm][:, picked].mean(axis=1)
                order = np.argsort(-means, kind="stable")
                ranks[arm] = {METHODS[m]: r for r, m in enumerate(order)}
            rhos[b] = spearman(ranks["control"], ranks["treatment"])
        rhos.sort()
        lo = float(rhos[int(0.025 * N_BOOT)])
        hi = float(rhos[max(int(0.975 * N_BOOT) - 1, 0)])

        ordering[metric] = {"issue_only": order_c, "superseded": order_t}
        agreement[metric] = {
            "spearman": rho, "spearman_ci": [lo, hi],
            "kendall": tau, "concordant": concordant, "discordant": discordant,
            "n_pairs": concordant + discordant,
            "leader_unchanged": order_c[0] == order_t[0],
            "moved": [m for m in METHODS if rank_c[m] != rank_t[m]],
        }

    # ---- 3. pairs whose difference changes sign ---------------------------
    flips = []
    for metric in METRICS:
        for x, y in itertools.combinations(METHODS, 2):
            d_c = per_method[x][metric]["control"] - per_method[y][metric]["control"]
            d_t = per_method[x][metric]["treatment"] - per_method[y][metric]["treatment"]
            if d_c * d_t < 0:
                lower, upper = (x, y) if d_c < 0 else (y, x)
                detail = {"metric": metric, "favoured_under_issue_only": upper,
                          "favoured_under_superseded": lower,
                          "delta_control": d_c, "delta_treatment": d_t}
                for arm, rows in (("control", control), ("treatment", treat)):
                    item = compare_methods(
                        list(rows.values()), metric, upper, [lower])[0]
                    detail[arm] = {
                        "delta": item["delta"],
                        "ci": item["delta_cluster_bootstrap_95ci"],
                        "p_cluster": item["p_cluster"],
                        "n_clusters": item["n_clusters"],
                    }
                flips.append(detail)

    # ---- 4. mechanism: does the leaked query name the gold path? ----------
    # Stratified by language, because the Python stratum's treatment query is the
    # issue text repeated with no post-solution text at all: if the path-mention
    # rise were an artefact of query length it would show up there too.
    mechanism = {}
    strata = {
        "all": lambda row: True,
        "python": lambda row: row.get("lang") == "python",
        "non_python": lambda row: row.get("lang") != "python",
    }
    for name, keep in strata.items():
        ids = [i for i in instances if keep(control[("bm25", i)])]
        entry = {"n": len(ids)}
        for arm, rows in (("control", control), ("treatment", treat)):
            flags = [1 if rows[("bm25", i)].get("query_mentions_gold_path") else 0
                     for i in ids]
            entry[arm] = statistics.fmean(flags)
        entry["delta"] = entry["treatment"] - entry["control"]
        mechanism[name] = entry

    # ---- write ------------------------------------------------------------
    payload = {
        "control_protocol": CONTROL_PROTOCOL,
        "treatment_protocol": TREAT_PROTOCOL,
        "n_instances": len(instances),
        "n_methods": len(METHODS),
        "n_clusters": n_clusters,
        "per_method": per_method,
        "ordering": ordering,
        "agreement": agreement,
        "flips": flips,
        "mechanism_query_mentions_gold_path": mechanism,
        "notes": [
            "Rank agreement over 8 configurations is coarse: Kendall tau moves in "
            "steps of 1/28 = 0.036.",
            "The ordering is computed from the same instances under both rules, so "
            "the only difference is the query text.",
            "A flipped pair is reported with its paired interval under both rules so "
            "that a flip between indistinguishable configurations is not read as a "
            "reversal of a real difference.",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# RQ7 - does the query rule change which configuration wins?",
        "",
        f"Both arms: {len(METHODS)} configurations x {len(instances):,} instances "
        f"({n_clusters} repository clusters). Control = `{CONTROL_PROTOCOL}`, "
        f"treatment = `{TREAT_PROTOCOL}`.",
        "",
        "| Configuration | Hit@1 issue-only | Hit@1 superseded | Δ Hit@1 | 95% CI | MRR issue-only | MRR superseded | Δ MRR |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for method in sorted(METHODS, key=lambda m: per_method[m]["mrr"]["control"],
                         reverse=True):
        e = per_method[method]
        h, r = e["hit@1"], e["mrr"]
        lines.append(
            f"| {method} | {h['control']:.4f} | {h['treatment']:.4f} | "
            f"{h['delta']:+.4f} | [{h['delta_ci'][0]:+.4f}, {h['delta_ci'][1]:+.4f}] | "
            f"{r['control']:.4f} | {r['treatment']:.4f} | {r['delta']:+.4f} |")
    lines.append("")
    for metric in METRICS:
        a = agreement[metric]
        lines += [
            f"## Ordering by {metric}",
            "",
            f"- issue-only: {' > '.join(ordering[metric]['issue_only'])}",
            f"- superseded: {' > '.join(ordering[metric]['superseded'])}",
            f"- Spearman rho = {a['spearman']:.4f} (95% CI "
            f"[{a['spearman_ci'][0]:.4f}, {a['spearman_ci'][1]:.4f}]), "
            f"Kendall tau = {a['kendall']:.4f}, "
            f"{a['concordant']} concordant / {a['discordant']} discordant of "
            f"{a['n_pairs']} pairs",
            f"- leader unchanged: {a['leader_unchanged']}; "
            f"positions that moved: {', '.join(a['moved']) or 'none'}",
            "",
        ]
    lines += ["## Pairs whose difference changes sign", ""]
    if not flips:
        lines.append("None.")
    for f in flips:
        lines.append(
            f"- {f['metric']}: {f['favoured_under_issue_only']} favoured under "
            f"issue-only ({f['delta_control']:+.4f}, p = {f['control']['p_cluster']:.3f}) "
            f"and {f['favoured_under_superseded']} under superseded "
            f"({f['delta_treatment']:+.4f}, p = {f['treatment']['p_cluster']:.3f}); "
            f"superseded-rule interval "
            f"[{f['treatment']['ci'][0]:+.4f}, {f['treatment']['ci'][1]:+.4f}]")
    lines += [
        "",
        "## Mechanism",
        "",
        "Share of instances whose query mentions the gold file path, by stratum.",
        "The Python stratum's treatment query is the issue text repeated and holds "
        "no post-solution text, so any rise there would indicate a length artefact "
        "rather than a leak effect.",
        "",
        "| Stratum | n | issue-only | superseded | Δ |",
        "|---|---:|---:|---:|---:|",
    ] + [
        f"| {name} | {mechanism[name]['n']:,} | {mechanism[name]['control']:.4f} | "
        f"{mechanism[name]['treatment']:.4f} | {mechanism[name]['delta']:+.4f} |"
        for name in ("all", "python", "non_python")
    ] + [""]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[written to {OUT_MD} and {OUT_JSON}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
