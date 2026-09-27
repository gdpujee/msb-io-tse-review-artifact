"""Statistical analysis for paired per-instance results.

Choices (and why):
* paired Wilcoxon signed-rank -- each instance is evaluated by every method, so
  observations are paired; we do not assume normality of the per-instance diffs.
* bootstrap 95% CI -- distribution-free, reported alongside every mean.
* Cliff's delta -- non-parametric effect size that is interpretable for
  bounded metrics such as hit@K (a percentage-point difference alone is not).
* Holm correction -- we compare several methods against a reference.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Sequence


def bootstrap_ci(xs: Sequence[float], n_boot: int = 10000, alpha: float = 0.05,
                 seed: int = 42) -> tuple[float, float]:
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += xs[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi)


def wilcoxon_paired(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Return (p_value_two_sided, cliff_delta) using a normal approximation.

    Implemented locally to avoid adding scipy as a dependency; ties are handled
    by dropping zero differences (standard practice).
    """
    diffs = [x - y for x, y in zip(a, b) if abs(x - y) > 1e-12]
    n = len(diffs)
    if n == 0:
        return 1.0, 0.0
    ranks = _rank_abs(diffs)
    w_plus = sum(r for r, d in zip(ranks, diffs) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, diffs) if d < 0)
    w = min(w_plus, w_minus)
    mu = n * (n + 1) / 4
    sigma = (n * (n + 1) * (2 * n + 1) / 24) ** 0.5
    z = (w - mu) / sigma if sigma else 0.0
    p = _norm_sf2(abs(z))
    # Cliff's delta from rank sums
    delta = (w_plus - w_minus) / (n * (n + 1) / 2) if n else 0.0
    return p, delta


def _rank_abs(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: abs(xs[i]))
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abs(xs[order[j + 1]]) == abs(xs[order[i]]):
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _norm_sf2(z: float) -> float:
    """2 * (1 - Phi(z)) via Abramowitz-Stegun 7.1.26."""
    import math
    if z < 0:
        z = -z
    t = 1.0 / (1.0 + 0.2316419 * z)
    d = 0.3989422804014327 * math.exp(-z * z / 2.0)
    p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 +
        t * (-1.821255978 + t * 1.330274429))))
    return p


def holm_correct(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    out = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = (m - rank) * pvals[i]
        running = max(running, val)
        out[i] = min(1.0, running)
    return out


def cliffs_delta_magnitude(d: float) -> str:
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    if ad < 0.33:
        return "small"
    if ad < 0.474:
        return "medium"
    return "large"


def compare_methods(rows: list[dict], metric: str, ref: str, others: list[str],
                    group_by: str | None = None) -> list[dict]:
    """Paired comparison of `others` against `ref` on `metric`."""
    out = []
    keys = sorted({r[group_by] for r in rows}) if group_by else [None]
    for g in keys:
        sub = [r for r in rows if (group_by is None or r[group_by] == g)]
        ref_rows = {(r["instance_id"], r.get("lang")): r[metric] for r in sub if r["method"] == ref}
        pvals, methods = [], []
        pairs = []
        for m in others:
            m_rows = {(r["instance_id"], r.get("lang")): r[metric] for r in sub if r["method"] == m}
            common = sorted(set(ref_rows) & set(m_rows))
            if len(common) < 2:
                continue
            a = [m_rows[k] for k in common]
            b = [ref_rows[k] for k in common]
            p, d = wilcoxon_paired(a, b)
            pairs.append((m, a, b, p, d, len(common)))
            pvals.append(p)
            methods.append(m)
        if not pvals:
            continue
        adj = holm_correct(pvals)
        for (m, a, b, p, d, n), pa in zip(pairs, adj):
            ci_a = bootstrap_ci(a)
            ci_b = bootstrap_ci(b)
            out.append({
                "group": g, "metric": metric, "reference": ref, "method": m,
                "n_paired": n,
                "mean_ref": round(sum(b) / len(b), 4),
                "mean_method": round(sum(a) / len(a), 4),
                "delta": round(sum(a) / len(a) - sum(b) / len(b), 4),
                "ci_ref": [round(ci_b[0], 4), round(ci_b[1], 4)],
                "ci_method": [round(ci_a[0], 4), round(ci_a[1], 4)],
                "p_raw": round(p, 6), "p_holm": round(pa, 6),
                "cliffs_delta": round(d, 4),
                "effect": cliffs_delta_magnitude(d),
                "significant": pa < 0.05,
            })
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("--metric", default="mrr")
    ap.add_argument("--ref", default="bm25")
    ap.add_argument("--others", nargs="*", default=["bm25_path_anchor"])
    ap.add_argument("--group-by", default="lang")
    args = ap.parse_args()
    rows = [json.loads(l) for l in args.results.open()]
    res = compare_methods(rows, args.metric, args.ref, args.others, args.group_by)
    print(json.dumps(res, indent=2, ensure_ascii=False))
