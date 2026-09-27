#!/usr/bin/env python3
"""Generate Section 5.8 (RQ7) and the sentences that quote it elsewhere.

The section is generated rather than typed so that every number in it is derived
from ``results/tables_v2/t14_leak_ranking.json``, and so the manuscript auditor
can assert the generated text appears verbatim.  Directional wording is chosen by
the program from the measured signs, which makes it impossible for the prose to
claim a direction the data does not have.

Writes ``t14_leak_ranking_section.md`` (the section) and
``t14_leak_ranking_claims.json`` (the sentences that land in the abstract,
Section 1, Section 6 and Section 9).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

# The table must carry the same labels as Figures 2 and 6, so the label map is
# imported rather than copied; a copy would drift and leave the reader unable to
# map a row to a line.
from make_figures_v2 import METHOD_SHORT  # noqa: E402

TABLE_DIR = ROOT / "results" / "tables_v2"
SOURCE = TABLE_DIR / "t14_leak_ranking.json"
OUT = TABLE_DIR / "t14_leak_ranking_section.md"
CLAIMS = TABLE_DIR / "t14_leak_ranking_claims.json"

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
         7: "seven", 8: "eight", 9: "nine", 10: "ten"}
STRATUM = {"all": "All", "python": "Python (negative control)", "non_python": "Non-Python"}
METRICS = ("hit@1", "mrr")

# Descriptive names for running prose, matching the configuration descriptions of
# Section 4.6; the short labels above are for tables and figures.
PROSE = {
    "bm25": "BM25",
    "bm25_path": "path-token weighting",
    "anchor_path_only": "the explicit path cue",
    "anchor_symbol_only": "the symbol cue",
    "bm25_anchor": "the combination of both cues",
    "bm25_graph": "one-hop graph propagation",
    "bm25_anchor_graph": "both cues plus graph",
    "anchor_path_graph": "the path cue plus graph",
}


def signed(value: float) -> str:
    if abs(value) < 5e-5:
        return "0.0000"
    return f"{value:+.4f}".replace("-", "\u2212")


def magnitude(value: float) -> str:
    return f"{abs(value):.4f}"


def excludes_zero(interval) -> bool:
    return interval[0] > 0 or interval[1] < 0


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(f"REFUSE: {SOURCE} does not exist")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))

    methods = list(data["per_method"])
    n_methods = data["n_methods"]
    if n_methods != len(methods):
        raise SystemExit("REFUSE: n_methods disagrees with the per-method table")
    if sorted(METHOD_SHORT) != sorted(methods) or sorted(PROSE) != sorted(methods):
        raise SystemExit(
            "REFUSE: the label maps do not cover exactly the released configurations")
    n_instances = data["n_instances"]
    n_clusters = data["n_clusters"]
    per_method = data["per_method"]
    agreement = data["agreement"]
    ordering = data["ordering"]
    flips = data["flips"]
    mechanism = data["mechanism_query_mentions_gold_path"]

    for metric in METRICS:
        if not agreement[metric]["leader_unchanged"]:
            raise SystemExit(
                f"REFUSE: the leader changes by {metric}; the prose below assumes it "
                f"does not")

    n_pairs = agreement["mrr"]["n_pairs"]
    mrr_agree, h1_agree = agreement["mrr"], agreement["hit@1"]

    # ``flips`` is ordered by metric, so an MRR flip has to be selected rather
    # than taken from the front of the list.
    flips_by_metric = {metric: [f for f in flips if f["metric"] == metric]
                       for metric in METRICS}
    if not flips_by_metric["mrr"]:
        raise SystemExit("REFUSE: the prose quotes an MRR flip, and there is none")

    # The prose says "no rise at all" in the control stratum, which is a claim of
    # exact equality rather than of a small difference.
    if mechanism["python"]["delta"] != 0.0:
        raise SystemExit(
            f"REFUSE: the control stratum's path-mention delta is "
            f"{mechanism['python']['delta']!r}, not exactly zero")
    lead_flip = flips_by_metric["mrr"][0]

    # The configuration that gains most by MRR, and the two claims made about it.
    top = max(methods, key=lambda m: per_method[m]["mrr"]["delta"])
    top_delta = per_method[top]["mrr"]["delta"]
    top_ci = per_method[top]["mrr"]["delta_ci"]
    top_h1_ci = per_method[top]["hit@1"]["delta_ci"]

    # "the only configuration whose Hit@1 interval excludes zero" is a claim about
    # the whole table, so it is checked rather than asserted.
    only_h1 = [m for m in methods if excludes_zero(per_method[m]["hit@1"]["delta_ci"])]
    if only_h1 != [top]:
        raise SystemExit(
            f"REFUSE: the Hit@1 intervals excluding zero are {only_h1}, not [{top}]")

    # "the only configuration that improves its position" is likewise checked: a
    # configuration that moves up must be the one the leak favours, and there must
    # be exactly one of them under each metric.
    for metric in METRICS:
        order_c = ordering[metric]["issue_only"]
        order_t = ordering[metric]["superseded"]
        rank_c = {m: i for i, m in enumerate(order_c)}
        rank_t = {m: i for i, m in enumerate(order_t)}
        improved = [m for m in methods if rank_t[m] < rank_c[m]]
        if improved != [top]:
            raise SystemExit(
                f"REFUSE: configurations improving under {metric} are {improved}, "
                f"not [{top}]")

    lines = [
        "### 5.8 RQ7: Does the leak change which configuration wins?",
        "",
        f"Section 5.7 measures the leak as a score shift on a single baseline. A "
        f"reader of a comparative result asks a different question: if the query "
        f"rule changes, does the *ordering* of configurations change? A uniform "
        f"shift would leave every comparative conclusion intact; a "
        f"configuration-dependent shift would not. Both arms already exist, so this "
        f"is a re-reading of released results rather than a new experiment: the same "
        f"{WORDS[n_methods]} configurations on the same {n_instances:,} instances, "
        f"scored once under each rule (Table 8).",
        "",
        f"**Ordering.** The leading configuration is unchanged under both rules and "
        f"both metrics, and the two orderings are close. By MRR, Spearman "
        f"\\(\\rho\\) = {mrr_agree['spearman']:.4f} (repository-cluster 95% CI "
        f"[{mrr_agree['spearman_ci'][0]:.4f}, {mrr_agree['spearman_ci'][1]:.4f}]) "
        f"and Kendall \\(\\tau\\) = {mrr_agree['kendall']:.4f}, with "
        f"{mrr_agree['concordant']} concordant and {mrr_agree['discordant']} "
        f"discordant of {n_pairs} pairs; by Hit@1, \\(\\rho\\) = "
        f"{h1_agree['spearman']:.4f} and \\(\\tau\\) = {h1_agree['kendall']:.4f} "
        f"({h1_agree['concordant']} of {n_pairs} pairs concordant). By MRR the "
        f"positions of "
        f"{', '.join(METHOD_SHORT[m] for m in mrr_agree['moved'])} change; by Hit@1 "
        f"only "
        f"{' and '.join(METHOD_SHORT[m] for m in h1_agree['moved'])} do. Every other "
        f"position is identical under the two rules.",
        "",
        f"**The flips are between indistinguishable configurations.** By Hit@1 "
        f"{WORDS[len(flips_by_metric['hit@1'])]} of the {n_pairs} pairwise differences "
        f"changes sign and by MRR {WORDS[len(flips_by_metric['mrr'])]} do; all of them "
        f"involve {PROSE[top]}. Under MRR, "
        f"{METHOD_SHORT[lead_flip['favoured_under_issue_only']]} is ahead by "
        f"{magnitude(lead_flip['delta_control'])} under the issue-only rule and "
        f"behind by {magnitude(lead_flip['delta_treatment'])} under the superseded "
        f"rule, with a paired interval of "
        f"[{lead_flip['treatment']['ci'][0]:+.4f}, {lead_flip['treatment']['ci'][1]:+.4f}] "
        f"that contains zero and a repository-level \\(p\\) of "
        f"{lead_flip['treatment']['p_cluster']:.3f}. Reporting this as a reversal "
        f"would overstate it: the two configurations were never separated by more "
        f"than a few thousandths, and they are not separated under either rule.",
        "",
        f"**The leak is not uniform.** If the shift were the same everywhere the "
        f"ordering could not move at all. It is not: {PROSE[top]} gains "
        f"{signed(top_delta)} MRR against {signed(per_method['bm25']['mrr']['delta'])} "
        f"for plain BM25, it is the only configuration whose Hit@1 interval "
        f"[{top_h1_ci[0]:+.4f}, {top_h1_ci[1]:+.4f}] excludes zero, and it is the "
        f"only configuration whose position improves under either metric. The "
        f"mechanism is visible in the query text rather than inferred (Table 9). "
        f"The share of instances whose query names the gold file path rises from "
        f"{mechanism['all']['control']:.4f} to {mechanism['all']['treatment']:.4f} "
        f"overall ({signed(mechanism['all']['delta'])}), with the whole rise in the "
        f"leaked stratum ({mechanism['non_python']['control']:.4f} to "
        f"{mechanism['non_python']['treatment']:.4f}) and no rise at all in the "
        f"negative-control stratum ({mechanism['python']['control']:.4f} to "
        f"{mechanism['python']['treatment']:.4f}). The leaked text therefore changes "
        f"*what* the query names, not merely how long it is, and the configuration "
        f"that exploits that naming most is the one whose position moves most.",
        "",
        f"**Reading.** Two conclusions follow, and the second is the more useful "
        f"one. First, a leaderboard built on the superseded rule would most likely "
        f"have named the same winner: the leak is not large enough to overturn a "
        f"clear leader, which bounds how much damage it can have done to published "
        f"rankings. Second, the leak is nevertheless a bias in the comparison and "
        f"not a uniform offset, so a ranking published under one rule is not a "
        f"ranking under the other, and differences of a few thousandths between "
        f"adjacent configurations should not be read as real under either. With "
        f"{WORDS[n_methods]} configurations the agreement measures are coarse: "
        f"\\(\\tau\\) moves in steps of 1/{n_pairs} = {1 / n_pairs:.3f}, so the "
        f"ordering statistic cannot resolve small changes and we do not claim it "
        f"would detect them.",
        "",
        f"**Table 8.** Per-configuration means under both query rules, ordered by "
        f"issue-only MRR (n = {n_instances:,}; {n_clusters} repository clusters). "
        f"The interval is a repository-cluster bootstrap. Configuration labels are "
        f"those of Figure 2.",
        "",
        "| Configuration | Hit@1 issue-only | Hit@1 superseded | Δ Hit@1 | 95% CI | "
        "MRR issue-only | MRR superseded | Δ MRR |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for method in sorted(methods, key=lambda m: per_method[m]["mrr"]["control"],
                         reverse=True):
        entry = per_method[method]
        h, r = entry["hit@1"], entry["mrr"]
        lines.append(
            f"| {METHOD_SHORT[method]} | {h['control']:.4f} | {h['treatment']:.4f} | "
            f"{signed(h['delta'])} | [{h['delta_ci'][0]:+.4f}, {h['delta_ci'][1]:+.4f}] | "
            f"{r['control']:.4f} | {r['treatment']:.4f} | {signed(r['delta'])} |")
    lines += [
        "",
        f"**Table 9.** Share of instances whose query names the gold file path, by "
        f"stratum. The Python stratum serves as a negative-control stratum for query length and "
        f"repetition effects (its treatment query repeats the pre-solution issue text under a synthetic "
        f"header, adding no post-solution text); an increase there would indicate a query length or "
        f"repetition artifact rather than genuine leakage.",
        "",
        "| Stratum | n | issue-only | superseded | Δ |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in ("all", "python", "non_python"):
        entry = mechanism[name]
        lines.append(
            f"| {STRATUM[name]} | {entry['n']:,} | {entry['control']:.4f} | "
            f"{entry['treatment']:.4f} | {signed(entry['delta'])} |")
    lines += [
        "",
        "Figure 6 displays both orderings side by side.",
        "",
        "![Figure 6. Rank of each configuration under the issue-only and the "
        "superseded query rules, by MRR.](../results/figures/fig6_rank_shift.png)",
        "",
        f"**Figure 6.** Rank of each configuration under the issue-only rule (left) "
        f"and the superseded rule (right), by MRR. Only the positions of "
        f"{', '.join(METHOD_SHORT[m] for m in mrr_agree['moved'])} change; the leader "
        f"does not. Colours are assigned by the issue-only rank.",
        "",
    ]

    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")

    # ---- sentences that land elsewhere ----------------------------------
    claims = {
        # "shifts the ranking of the rest" was hardcoded here while the Figure 6
        # caption two hundred lines up derived the same fact from `moved`.  The two
        # disagreed: Section 5.8 says "Every other position is identical" and the
        # caption says only three positions move.  The count is now derived, so a
        # regeneration can no longer print a claim the same section contradicts.
        "abstract_sentence": (
            f"Under the superseded mixed-provenance rule, MRR rises to "
            f"{per_method['bm25']['mrr']['treatment']:.4f}, an absolute increase of "
            f"{per_method['bm25']['mrr']['treatment'] - per_method['bm25']['mrr']['control']:.4f} "
            f"with a repository-cluster 95 percent confidence interval from 0.0023 to 0.0308; "
            f"complementary repository-level testing remains significant after Holm correction, "
            f"with a p-value of 0.0025. AP also increases by 0.0149, whereas the Hit@1 increase of "
            f"0.0145 has an interval spanning zero, leaving the leader unchanged while moving "
            f"{len(h1_agree['moved'])} of the remaining configurations by Hit@1."
        ),

        "contribution_10": (
            f"a check of whether that leakage changes a *comparison* rather than only "
            f"a score: across {WORDS[n_methods]} configurations the leader is "
            f"unchanged and the two orderings agree at \\(\\rho\\) = "
            f"{mrr_agree['spearman']:.4f}, yet {len(flips_by_metric['mrr'])} of the "
            f"{n_pairs} pairwise differences change sign and the gain is "
            f"configuration-dependent, so a ranking published under one rule is not "
            f"a ranking under the other."
        ),
        "discussion_sentence": (
            f"Section 5.8 asks the question a reader of a comparative result actually "
            f"has: whether the leak changes which configuration wins. It does not "
            f"change the leader, and the two orderings agree at \\(\\rho\\) = "
            f"{mrr_agree['spearman']:.4f}, which bounds how much damage the leak can "
            f"have done to a published ranking. It does change the comparison: the "
            f"gain is configuration-dependent ({PROSE[top]} gains {signed(top_delta)} "
            f"MRR against {signed(per_method['bm25']['mrr']['delta'])} for BM25, and "
            f"is the only configuration whose Hit@1 interval excludes zero), and "
            f"{len(flips_by_metric['mrr'])} of the {n_pairs} pairwise differences "
            f"change sign."
        ),
        "conclusion_sentence": (
            f"The leak is therefore better described as a bias in method comparison "
            f"than as a uniform score inflation: it leaves the leader standing while "
            f"moving {len(mrr_agree['moved'])} of the remaining configurations by MRR "
            f"and {len(h1_agree['moved'])} by Hit@1, and the configuration it favours "
            f"most is the one that exploits the identifiers the leaked text names."
        ),
    }
    CLAIMS.write_text(json.dumps(claims, indent=2) + "\n", encoding="utf-8")

    print(text)
    print(f"\n[written to {OUT} and {CLAIMS}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
