"""File-level localization metrics.

Definitions (kept explicit because RQ4 studies how much the definition matters):
  gold          = files modified by fix_patch (optionally excluding test files)
  candidates    = all indexed files (optionally excluding test files)
  unreachable   = gold files that do not exist in the index (e.g. files added by
                  the fix). These can never be retrieved; we COUNT them rather
                  than silently pretend they are retrievable.
  hit@K         = 1 if at least one (reachable) gold file appears in top-K
  recall@K      = |topK ∩ gold| / |gold_reachable|
  precision@K   = |topK ∩ gold| / K
  mrr           = 1 / rank of the first gold file (0 if none in the ranked list)
  ap            = average precision over the full ranked list
"""
from __future__ import annotations

from dataclasses import dataclass

METRIC_PROTOCOL = "full_precision_metrics_v1"


@dataclass
class Metrics:
    hit_at: dict[int, int]
    recall_at: dict[int, float]
    precision_at: dict[int, float]
    mrr: float
    ap: float
    n_gold: int
    n_gold_reachable: int
    n_unreachable: int
    n_candidates: int

    def as_row(self, prefix: str = "") -> dict:
        row = {f"{prefix}hit@{k}": v for k, v in self.hit_at.items()}
        # Raw artifacts retain full floating-point precision.  Rounding here
        # used to create artificial ties before Wilcoxon tests (especially for
        # low reciprocal ranks); presentation layers round only after all
        # statistics have been computed.
        row.update({f"{prefix}recall@{k}": v for k, v in self.recall_at.items()})
        row.update({f"{prefix}prec@{k}": v for k, v in self.precision_at.items()})
        row[f"{prefix}mrr"] = self.mrr
        row[f"{prefix}ap"] = self.ap
        row[f"{prefix}n_gold"] = self.n_gold
        row[f"{prefix}n_gold_reachable"] = self.n_gold_reachable
        row[f"{prefix}n_unreachable"] = self.n_unreachable
        row[f"{prefix}n_candidates"] = self.n_candidates
        return row


def evaluate_ranking(ranked: list[str], gold: set[str], ks=(1, 3, 5, 10, 20, 50)) -> Metrics:
    """`ranked` is the full ranked candidate list (best first)."""
    reachable = set(gold)
    gold_reachable = {g for g in gold}
    hit, recall, prec = {}, {}, {}
    for k in ks:
        top = ranked[:k]
        n_hit = sum(1 for f in top if f in reachable)
        hit[k] = 1 if n_hit > 0 else 0
        recall[k] = n_hit / max(1, len(gold_reachable))
        prec[k] = n_hit / k
    mrr = 0.0
    ap = 0.0
    n_found = 0
    for i, f in enumerate(ranked, 1):
        if f in reachable:
            if mrr == 0.0:
                mrr = 1.0 / i
            n_found += 1
            ap += n_found / i
    ap = ap / max(1, len(gold_reachable))
    return Metrics(hit_at=hit, recall_at=recall, precision_at=prec, mrr=mrr, ap=ap,
                   n_gold=len(gold), n_gold_reachable=len(gold_reachable),
                   n_unreachable=0, n_candidates=len(ranked))


def aggregate(rows: list[Metrics]) -> dict:
    n = len(rows)
    if n == 0:
        return {}
    out: dict = {"n": n}
    for k in rows[0].hit_at:
        out[f"hit@{k}"] = round(sum(r.hit_at[k] for r in rows) / n, 4)
        out[f"recall@{k}"] = round(sum(r.recall_at[k] for r in rows) / n, 4)
        out[f"prec@{k}"] = round(sum(r.precision_at[k] for r in rows) / n, 4)
    out["mrr"] = round(sum(r.mrr for r in rows) / n, 4)
    out["map"] = round(sum(r.ap for r in rows) / n, 4)
    out["n_unreachable"] = sum(r.n_unreachable for r in rows)
    out["avg_candidates"] = round(sum(r.n_candidates for r in rows) / n, 1)
    return out
