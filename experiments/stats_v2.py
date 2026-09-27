"""Correct paired statistics for protocol V2 localization experiments.

Binary hit indicators use exact McNemar tests. Continuous paired ranking
metrics use SciPy's tie-aware Wilcoxon signed-rank test. Effect size is the
matched-pairs rank-biserial correlation, and method-delta confidence intervals
resample repositories as clusters.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Hashable, Sequence

from scipy.stats import binomtest, rankdata, wilcoxon


def bootstrap_ci(xs: Sequence[float], n_boot: int = 10000, alpha: float = 0.05,
                 seed: int = 42) -> tuple[float, float]:
    """Percentile bootstrap CI for a single descriptive mean."""
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
    means.sort()
    return _percentile_bounds(means, alpha)


def cluster_bootstrap_delta(
    diffs: Sequence[float], clusters: Sequence[Hashable], n_boot: int = 10000,
    alpha: float = 0.05, seed: int = 42,
) -> tuple[float, float]:
    """CI for a paired mean delta, resampling repository clusters."""
    if not diffs or len(diffs) != len(clusters):
        return (0.0, 0.0)
    by_cluster: dict[Hashable, list[float]] = {}
    for diff, cluster in zip(diffs, clusters):
        by_cluster.setdefault(cluster, []).append(diff)
    keys = sorted(by_cluster, key=str)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_boot):
        sampled: list[float] = []
        for _ in keys:
            sampled.extend(by_cluster[keys[rng.randrange(len(keys))]])
        means.append(sum(sampled) / len(sampled))
    means.sort()
    return _percentile_bounds(means, alpha)


def _percentile_bounds(values: Sequence[float], alpha: float) -> tuple[float, float]:
    n = len(values)
    lo = values[int((alpha / 2) * n)]
    hi = values[min(n - 1, int((1 - alpha / 2) * n))]
    return (lo, hi)


def rank_biserial(a: Sequence[float], b: Sequence[float]) -> float:
    """Matched-pairs rank-biserial correlation for method minus reference."""
    diffs = [x - y for x, y in zip(a, b) if abs(x - y) > 1e-12]
    if not diffs:
        return 0.0
    ranks = rankdata([abs(diff) for diff in diffs], method="average")
    w_plus = sum(rank for rank, diff in zip(ranks, diffs) if diff > 0)
    w_minus = sum(rank for rank, diff in zip(ranks, diffs) if diff < 0)
    return float((w_plus - w_minus) / (w_plus + w_minus))


def exact_mcnemar(a: Sequence[float], b: Sequence[float]) -> tuple[float, int]:
    """Two-sided exact McNemar test via discordant-pair binomial test."""
    gains = sum(int(x == 1 and y == 0) for x, y in zip(a, b))
    losses = sum(int(x == 0 and y == 1) for x, y in zip(a, b))
    discordant = gains + losses
    if discordant == 0:
        return 1.0, 0
    return float(binomtest(gains, discordant, 0.5).pvalue), discordant


def paired_test(a: Sequence[float], b: Sequence[float], metric: str) -> tuple[float, str, int]:
    if metric.startswith("hit@") or metric.startswith("all_hit@"):
        p, n_discordant = exact_mcnemar(a, b)
        return p, "exact_mcnemar", n_discordant
    diffs = [x - y for x, y in zip(a, b)]
    if not any(abs(diff) > 1e-12 for diff in diffs):
        return 1.0, "wilcoxon", 0
    result = wilcoxon(a, b, zero_method="wilcox", correction=False,
                      alternative="two-sided", method="auto")
    return float(result.pvalue), "wilcoxon", sum(abs(diff) > 1e-12 for diff in diffs)


def cluster_level_test(a: Sequence[float], b: Sequence[float],
                       clusters: Sequence[Hashable]) -> tuple[float, int]:
    """Wilcoxon test over repository-level mean outcomes.

    Instance-level paired tests are useful diagnostics, but benchmark instances
    from the same repository are dependent. This repository-level test is the
    primary inferential result.
    """
    grouped: dict[Hashable, tuple[list[float], list[float]]] = {}
    for method_value, ref_value, cluster in zip(a, b, clusters):
        method_values, ref_values = grouped.setdefault(cluster, ([], []))
        method_values.append(method_value)
        ref_values.append(ref_value)
    method_means = [sum(grouped[key][0]) / len(grouped[key][0]) for key in sorted(grouped, key=str)]
    ref_means = [sum(grouped[key][1]) / len(grouped[key][1]) for key in sorted(grouped, key=str)]
    diffs = [x - y for x, y in zip(method_means, ref_means)]
    informative = sum(abs(diff) > 1e-12 for diff in diffs)
    if informative == 0:
        return 1.0, 0
    result = wilcoxon(method_means, ref_means, zero_method="wilcox", correction=False,
                      alternative="two-sided", method="auto")
    return float(result.pvalue), informative


def holm_correct(pvals: list[float]) -> list[float]:
    """Holm step-down family-wise error correction."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    out = [0.0] * len(pvals)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(pvals) - rank) * pvals[i])
        out[i] = min(1.0, running)
    return out


def effect_magnitude(effect: float) -> str:
    """Conventional absolute thresholds for rank-biserial correlation."""
    value = abs(effect)
    if value < 0.10:
        return "negligible"
    if value < 0.30:
        return "small"
    if value < 0.50:
        return "medium"
    return "large"


def compare_methods(rows: list[dict], metric: str, ref: str, others: list[str],
                    group_by: str | None = None) -> list[dict]:
    """Paired comparisons with repository-clustered delta confidence intervals."""
    out: list[dict] = []
    groups = sorted({row[group_by] for row in rows}) if group_by else [None]
    for group in groups:
        sub = [row for row in rows if group_by is None or row[group_by] == group]
        ref_rows = {(row["instance_id"], row.get("lang")): row for row in sub
                    if row["method"] == ref}
        comparisons = []
        for method in others:
            method_rows = {(row["instance_id"], row.get("lang")): row for row in sub
                           if row["method"] == method}
            common = sorted(set(ref_rows) & set(method_rows))
            if len(common) < 2:
                continue
            a = [method_rows[key][metric] for key in common]
            b = [ref_rows[key][metric] for key in common]
            clusters = [(method_rows[key].get("lang"), method_rows[key]["repo"])
                        for key in common]
            p_value, test, n_test = paired_test(a, b, metric)
            cluster_p, n_cluster_informative = cluster_level_test(a, b, clusters)
            effect = rank_biserial(a, b)
            diffs = [x - y for x, y in zip(a, b)]
            delta_ci = cluster_bootstrap_delta(diffs, clusters)
            comparisons.append((method, a, b, p_value, test, n_test, effect,
                                delta_ci, len(set(clusters)), cluster_p,
                                n_cluster_informative))
        adjusted = holm_correct([item[9] for item in comparisons])
        for item, p_holm in zip(comparisons, adjusted):
            (method, a, b, p_value, test, n_test, effect, delta_ci, n_clusters,
             cluster_p, n_cluster_informative) = item
            delta = sum(x - y for x, y in zip(a, b)) / len(a)
            out.append({
                "group": group, "metric": metric, "reference": ref, "method": method,
                "n_paired": len(a), "n_clusters": n_clusters,
                "n_test_informative": n_test, "test": test,
                "n_cluster_informative": n_cluster_informative,
                "mean_ref": round(sum(b) / len(b), 4),
                "mean_method": round(sum(a) / len(a), 4),
                "delta": round(delta, 4),
                "delta_cluster_bootstrap_95ci": [round(delta_ci[0], 4), round(delta_ci[1], 4)],
                "p_instance": p_value,
                "p_cluster": cluster_p,
                "p_cluster_holm": p_holm,
                "rank_biserial": round(effect, 4),
                "effect": effect_magnitude(effect),
                "significant": p_holm < 0.05,
            })
    return out


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--metric", default="mrr")
    parser.add_argument("--ref", default="bm25")
    parser.add_argument("--others", nargs="*", default=["anchor_path_only"])
    parser.add_argument("--group-by", default="lang")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.results.open() if line.strip()]
    result = compare_methods(rows, args.metric, args.ref, args.others, args.group_by)
    print(json.dumps(result, indent=2, ensure_ascii=False))
