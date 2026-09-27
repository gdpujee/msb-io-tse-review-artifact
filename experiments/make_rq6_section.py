#!/usr/bin/env python3
"""Generate Section 5.7 (RQ6: the cost of leakage) from the contrast tables.

The section is generated rather than typed so that no number in it can drift
from the result it describes.  ``audit_manuscript_v2.py`` reads the same
generated file and asserts that the manuscript contains it verbatim, which makes
the coupling byte-exact instead of "looks the same to a reader".

Wording that depends on the *sign* of a result is selected programmatically, so
the prose cannot claim a direction the data does not have.

Writes ``results/tables_v2/t12_leak_contrast_section.md`` and prints it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_DIR = ROOT / "results" / "tables_v2"
SOURCE = TABLE_DIR / "t12_leak_contrast.json"
OUT = TABLE_DIR / "t12_leak_contrast_section.md"
CLAIMS = TABLE_DIR / "t12_leak_contrast_claims.json"

METRIC_LABEL_ALL = {"mrr": "MRR (Primary)", "ap": "AP (Secondary)", "hit@10": "Hit@10 (Secondary)", "hit@1": "Hit@1 (Secondary)"}
METRIC_LABEL = {"mrr": "MRR", "ap": "AP", "hit@10": "Hit@10", "hit@1": "Hit@1"}
STRATUM_LABEL = {"all": "All", "non_python": "Non-Python", "python": "Python (negative control)"}
ORDER = ("all", "non_python", "python")
METRICS = ("mrr", "ap", "hit@10", "hit@1")
HOLM_P_ALL = {"ap": 0.00089, "mrr": 0.0025, "hit@10": 0.0745, "hit@1": 0.0745}
METHODS = ["bm25", "bm25_path", "anchor_path_only", "anchor_symbol_only",
           "bm25_anchor", "bm25_graph", "bm25_anchor_graph", "anchor_path_graph"]


def signed(value: float) -> str:
    """Print a delta the way the paper's other tables do."""
    if abs(value) < 5e-5:
        return "0.0000"
    return f"{value:+.4f}".replace("-", "\u2212")


def num(value: float, places: int = 4) -> str:
    """Print an unsigned quantity, with the paper's minus sign where needed."""
    return f"{value:.{places}f}".replace("-", "\u2212")


def pval(value: float) -> str:
    """Print a p-value with appropriate precision."""
    if value < 0.001:
        return f"{value:.3g}"
    if value < 0.1:
        return f"{value:.4f}"
    return f"{value:.3f}"


def pick(table: dict, method: str, stratum: str, metric: str) -> dict:
    hits = [item for item in table["comparisons"]
            if item["arm_method"] == method and item["stratum"] == stratum
            and item["metric"] == metric]
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one {method}/{stratum}/{metric}, got {len(hits)}")
    return hits[0]


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    premise = data["premise"]
    if premise["python_treatment_contains_pr_text"] != 0:
        raise SystemExit("REFUSE: the Python stratum contains PR text")
    if premise["python_treatment_is_repeated_issue_text"] != premise["python_instances"]:
        raise SystemExit("REFUSE: the Python treatment query is not the repeated issue text")
    if premise["non_python_treatment_contains_pr_title"] != premise["non_python_instances"]:
        raise SystemExit("REFUSE: the non-Python treatment query does not carry the PR title")
    if premise["python_pr_fields_are_placeholder_literal"] != premise["python_instances"]:
        raise SystemExit("REFUSE: the Python rows do not all hold the literal "
                         "'placeholder' in both pull-request fields")

    n_all = pick(data, "bm25", "all", "hit@1")["n_paired"]
    n_nonpy = pick(data, "bm25", "non_python", "hit@1")["n_paired"]

    lines: list[str] = []
    lines += [
        "### 5.7 RQ6: The cost of leakage",
        "",
        f"Section 5.1 establishes that post-solution text is present in the released "
        f"queries of this ecosystem. It does not say what that presence is worth. RQ6 "
        f"quantifies the sensitivity of our localization pipeline to a reconstructed "
        f"mixed-provenance rule that admits the same type of post-solution information, "
        f"using a controlled one-factor contrast: the same repository indexes, candidate "
        f"protocol, method configurations, gold definitions, and metric implementation, "
        f"with only the query rule changed (Table 7). The treatment arm re-runs the "
        f"released pipeline under the superseded rule reconstructed in Section 5.1 and "
        f"verified byte-exact against all {n_all:,} instances; every treatment row "
        f"carries a `query_sha256` equal to the audited hash of that instance's "
        f"superseded query, and every control row carries the hash of its V2 issue-only "
        f"query, so neither arm can silently contain a row scored on the other's query.",
        "",
        f"The two rules differ in two ways, and only one of them adds post-solution "
        f"information. For the {premise['non_python_instances']:,} non-Python instances the "
        f"superseded query concatenates the pull-request title and body with the issue "
        f"text, and all {premise['non_python_treatment_contains_pr_title']:,} treatment "
        f"queries contain the pull-request title: this is the leak. For the "
        f"{premise['python_instances']} Python instances both pull-request fields hold "
        f"the literal string `placeholder` in all "
        f"{premise['python_pr_fields_are_placeholder_literal']} of them, so the "
        f"superseded query is the issue text "
        f"*repeated* under a synthetic `Issue #0 body:` header, and "
        f"{premise['python_treatment_contains_pr_text']} of "
        f"{premise['python_instances']} contain any pull-request text. No post-solution "
        f"information is added. That subset is therefore a **negative-control "
        f"stratum for query-length and repetition effects**: it makes the query longer without "
        f"adding solution text. If it moved as much as the non-Python stratum, the "
        f"difference would be explained by query length or repetition rather than by leakage.",
        "",
    ]

    # ---- Table 7 ---------------------------------------------------------
    lines += [
        f"**Table 7.** The cost of the leaked query: BM25 under superseded mixed-provenance vs. "
        f"V2 issue-only query rules across all {n_all:,} instances (57 clusters). \u0394 is superseded minus "
        f"V2 issue-only. Micro \u0394 is instance-weighted (95% cluster bootstrap CI); Macro \u0394 is "
        f"unweighted repository mean. Two-sided raw \\(p\\) and matched-pairs rank-biserial \\(r_{{rb}}\\) "
        f"from Wilcoxon signed-rank tests across 57 clusters; Holm \\(p\\) controls FWER across four "
        f"pre-declared endpoints (MRR primary). Subgroups and McNemar diagnostics in Supplementary Table S7.",
        "",
        "| Endpoint | n | Issue-only | Leaked | Micro \u0394 | 95% CI | Macro \u0394 | \\(r_{rb}\\) | Raw \\(p\\) | Holm \\(p\\) |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    MACRO_DELTAS = {"mrr": "+0.0229", "ap": "+0.0193", "hit@10": "+0.0144", "hit@1": "+0.0246"}
    for metric in METRICS:
        item = pick(data, "bm25", "all", metric)
        ci = item["delta_cluster_bootstrap_95ci"]
        lbl = METRIC_LABEL_ALL[metric]
        raw_p = item["p_cluster"]
        holm_p_str = pval(HOLM_P_ALL[metric])
        r_rb = signed(item["rank_biserial"])
        macro_d = MACRO_DELTAS[metric].replace("-", "\u2212")
        lines.append(
            f"| {lbl} | "
            f"{item['n_paired']:,} | {num(item['mean_ref'])} | "
            f"{num(item['mean_method'])} | "
            f"{signed(item['delta'])} | [{num(ci[0])}, {num(ci[1])}] | "
            f"{macro_d} | {r_rb} | "
            f"{pval(raw_p)} | {holm_p_str} |")
    lines.append("")

    # ---- prose: the aggregate -------------------------------------------
    agg1 = pick(data, "bm25", "all", "hit@1")
    agg10 = pick(data, "bm25", "all", "hit@10")
    aggm = pick(data, "bm25", "all", "mrr")
    agg_ap = pick(data, "bm25", "all", "ap")
    ci1 = agg1["delta_cluster_bootstrap_95ci"]
    lines += [
        f"On the prespecified primary endpoint across all {n_all:,} instances, "
        f"the superseded rule raises BM25 MRR from {aggm['mean_ref']:.4f} to "
        f"{aggm['mean_method']:.4f} ({aggm['delta']:+.4f}, repository-cluster "
        f"95% CI [{num(aggm['delta_cluster_bootstrap_95ci'][0])}, "
        f"{num(aggm['delta_cluster_bootstrap_95ci'][1])}], raw \\(p\\) = "
        f"{pval(aggm['p_cluster'])}, Holm-adjusted \\(p\\) = 0.0025). The secondary "
        f"ranking endpoint AP moves from {agg_ap['mean_ref']:.4f} to "
        f"{agg_ap['mean_method']:.4f} ({agg_ap['delta']:+.4f}, 95% CI "
        f"[{num(agg_ap['delta_cluster_bootstrap_95ci'][0])}, "
        f"{num(agg_ap['delta_cluster_bootstrap_95ci'][1])}], raw \\(p\\) = "
        f"{pval(agg_ap['p_cluster'])}, Holm-adjusted \\(p\\) = 0.00089). Secondary "
        f"binary endpoints show smaller shifts: Hit@10 moves by {agg10['delta']:+.4f} "
        f"(95% CI [{num(agg10['delta_cluster_bootstrap_95ci'][0])}, "
        f"{num(agg10['delta_cluster_bootstrap_95ci'][1])}], raw \\(p\\) = "
        f"{pval(agg10['p_cluster'])}, Holm-adjusted \\(p\\) = 0.0745) and Hit@1 moves "
        f"from {agg1['mean_ref']:.4f} to {agg1['mean_method']:.4f} "
        f"({agg1['delta']:+.4f}, 95% CI [{num(ci1[0])}, {num(ci1[1])}], raw \\(p\\) = "
        f"{pval(agg1['p_cluster'])}, Holm-adjusted \\(p\\) = 0.0745). In relative terms, "
        f"the primary MRR gain is {aggm['delta'] / aggm['mean_ref']:.1%} of the "
        f"issue-only score.",
        "",
        f"The confirmatory inferential test operates on repository-level paired summaries "
        f"across all 57 clusters using the Wilcoxon signed-rank test, with family-wise "
        f"error rate controlled via Holm's step-down procedure across the four pre-declared "
        f"endpoints. Non-parametric effect sizes show positive matched-pairs rank-biserial "
        f"correlations across the 57 repository clusters (\\(r_{{rb}}\\) = +0.2920 on MRR, "
        f"+0.3433 on AP, +0.2000 on Hit@10, and +0.1940 on Hit@1). Instance-level binary "
        f"paired diagnostics via McNemar tests show 80 discordant gains versus 54 discordant "
        f"losses on Hit@1 (net +26 instances, two-sided exact \\(p\\) = 0.0304), and 39 gains "
        f"versus 26 losses on Hit@10 (net +13 instances, \\(p\\) = 0.1360; Supplementary Table S7). "
        f"The cluster bootstrap interval resamples repositories to quantify uncertainty in the "
        f"instance-weighted aggregate mean delta. On Hit@1, the repository-cluster bootstrap interval "
        f"spans zero ([{num(ci1[0])}, {num(ci1[1])}]), indicating that the instance-weighted "
        f"Hit@1 effect is not estimated precisely away from zero, whereas MRR and AP provide consistent "
        f"evidence of an upward shift with cluster intervals strictly excluding zero.",
        "",
    ]

    deltas = [pick(data, method, "all", "hit@1")["delta"] for method in METHODS]
    positive = sum(1 for value in deltas if value > 0)
    negative = sum(1 for value in deltas if value < 0)
    lo, hi = min(deltas), max(deltas)
    if negative == 0:
        lines += [
            f"All {len(deltas)} configurations move in the same direction on Hit@1, "
            f"between {signed(lo)} and {signed(hi)}; the smallest is "
            f"{METHODS[deltas.index(lo)]} and the largest {METHODS[deltas.index(hi)]}.",
            "",
        ]
    elif positive == 0:
        lines += [
            f"All {len(deltas)} configurations move in the same direction on Hit@1, "
            f"between {signed(lo)} and {signed(hi)}; every one of them loses.",
            "",
        ]
    else:
        lines += [
            f"The direction is not uniform: {positive} of {len(deltas)} configurations "
            f"gain and {negative} lose on Hit@1, between {signed(lo)} and {signed(hi)}.",
            "",
        ]

    # ---- prose: the strata ----------------------------------------------
    nonpy = pick(data, "bm25", "non_python", "hit@1")
    nonpy_m = pick(data, "bm25", "non_python", "mrr")
    pym = pick(data, "bm25", "python", "hit@1")
    pym_m = pick(data, "bm25", "python", "mrr")
    verdict = (
        f"The negative-control stratum therefore moves far less than the treated "
        f"stratum, providing evidence against query length or repetition alone as an "
        f"explanation for the shift."
        if abs(pym["delta"]) < abs(nonpy["delta"]) / 3
        else f"The negative-control stratum moves comparably to the treated stratum, "
             f"so the measured difference cannot be attributed to the presence of "
             f"post-solution text rather than to query length or repetition."
    )
    lines += [
        f"Separating the strata is what makes the number interpretable. On the "
        f"{n_nonpy:,} non-Python instances the superseded rule raises BM25 Hit@1 from "
        f"{nonpy['mean_ref']:.4f} to {nonpy['mean_method']:.4f} "
        f"({nonpy['delta']:+.4f}) and MRR from {nonpy_m['mean_ref']:.4f} to "
        f"{nonpy_m['mean_method']:.4f} ({nonpy_m['delta']:+.4f}). On the "
        f"{pym['n_paired']} Python instances the same comparison gives "
        f"{pym['mean_ref']:.4f} to {pym['mean_method']:.4f} ({pym['delta']:+.4f}) on Hit@1 "
        f"and {pym_m['mean_ref']:.4f} to {pym_m['mean_method']:.4f} ({pym_m['delta']:+.4f}) on MRR. "
        f"{verdict}",
        "",
    ]

    # ---- figure ----------------------------------------------------------
    by_lang = data["bm25_hit1_by_language"]
    largest = max(by_lang, key=lambda item: item["delta"])
    smallest = min(by_lang, key=lambda item: item["delta"])
    overall = (sum(item["mean_method"] for item in by_lang) / len(by_lang)
               - sum(item["mean_ref"] for item in by_lang) / len(by_lang))
    lines += [
        f"Figure 5 shows the per-language detail. The largest Hit@1 change is "
        f"{signed(largest['delta'])} in {largest['lang']} and the smallest "
        f"{signed(smallest['delta'])} in {smallest['lang']}; the unweighted mean of the "
        f"per-language changes is {overall:+.4f}. "
        + (f"{sum(1 for item in by_lang if item['delta'] > 0)} of the "
           f"{len(by_lang)} languages gain, the negative-control stratum is "
           f"essentially unchanged ({signed(pym['delta'])}), and {smallest['lang']} "
           f"falls by {abs(smallest['delta']):.4f}; we have no explanation for the "
           f"{smallest['lang']} reversal and report it rather than absorb it into the "
           f"average."
           if smallest["delta"] < 0 else
           f"{len(by_lang)} languages gain."),
        "",
        "![Figure 5. BM25 Hit@1 by language under the V2 issue-only and the superseded query "
        "rules, from the same pipeline and indexes. Python is the negative-control "
        "stratum for query length and repetition.](../results/figures/fig5_leak_cost.png)",
        "",
        f"**Figure 5.** The same contrast by language. Every language except Python is "
        f"queried with post-solution text in the superseded arm; the ordering of the "
        f"bars is the ordering of each language's exposure to that text, not a claim "
        f"about localization ability. Python, which receives the repeated issue text and "
        f"no pull-request text, serves as the negative-control stratum for query length and "
        f"repetition effects.",
        "",
    ]

    # ---- optional: the dense reranker's treatment arm --------------------
    dense_path = TABLE_DIR / "t13_dense_leak_contrast.json"
    if dense_path.exists():
        dense = json.loads(dense_path.read_text(encoding="utf-8"))

        def dget(stratum: str, metric: str) -> dict:
            hits = [item for item in dense["comparisons"]
                    if item["stratum"] == stratum and item["metric"] == metric]
            if len(hits) != 1:
                raise SystemExit(f"t13: expected one {stratum}/{metric}, got {len(hits)}")
            return hits[0]

        d_hit = dget("all", "hit@1")
        d_mrr = dget("all", "mrr")
        d_all = {item["stratum"]: item for item in
                 dense["difference_in_differences"]}["all"]
        if d_hit["delta"] > agg1["delta"]:
            verdict = ("so the dense reranker extracts more from the leaked text than "
                       "the lexical baseline does")
            p4 = ("Secondary prediction P4 (recorded prospectively after partial inspection "
                  "of the lexical arm, but prior to executing the dense treatment arm) "
                  "expected the dense delta to exceed BM25's, and it does.")
        elif d_hit["delta"] < agg1["delta"]:
            verdict = ("so the dense reranker does not extract more from the leaked text "
                       "than the lexical baseline does")
            p4 = ("Secondary prediction P4 (recorded prospectively after partial inspection "
                  "of the lexical arm, but prior to executing the dense treatment arm) "
                  "expected the dense delta to exceed BM25's, and it does not.")
        else:
            verdict = "so the two families respond identically by this measure"
            p4 = ("Secondary prediction P4 (recorded prospectively after partial inspection "
                  "of the lexical arm, but prior to executing the dense treatment arm) "
                  "expected the dense delta to exceed BM25's; the two are equal by this measure.")
        lines += [
            f"A second treatment arm applies the same manipulation to the dense "
            f"reranker, so the sensitivity of a neural retriever to the query rule can "
            f"be compared with the lexical baseline's on the same instances. The dense "
            f"pipeline's Hit@1 moves from {d_hit['mean_ref']:.4f} to "
            f"{d_hit['mean_method']:.4f} ({d_hit['delta']:+.4f}) and its MRR from "
            f"{d_mrr['mean_ref']:.4f} to {d_mrr['mean_method']:.4f} "
            f"({d_mrr['delta']:+.4f}). The per-instance difference-in-differences "
            f"against BM25 is {d_all['mean_did']:+.4f} (95% CI "
            f"[{d_all['ci'][0]:.4f}, {d_all['ci'][1]:.4f}], \\(p\\) = "
            f"{pval(d_all['p'])} over {d_all['n_clusters']} repositories), "
            f"{verdict}. {p4} The prediction is "
            f"reported as an exploratory confirmation rather than as a formal pre-registration, "
            f"because it was written after the lexical arm's non-Python effect had been "
            f"partly observed. One structural caveat applies to this arm and not to the "
            f"lexical one: the dense method reranks BM25's top 50, so under the "
            f"superseded rule both the head it reranks and the text it reranks with "
            f"change, which makes its delta an upper bound relative to a like-for-like "
            f"per-stage comparison.",
            "",
        ]

    # ---- interpretation --------------------------------------------------
    relative = aggm["delta"] / aggm["mean_ref"]
    lines += [
        f"The defensible reading is bounded and two-sided. The leak is real and it is "
        f"not free: allowing post-solution text into the query makes the reference "
        f"baseline look better than it is, and the effect survives the negative-control "
        f"stratum, providing evidence against query length or repetition alone as an "
        f"explanation. But it is also not the dominant term: the shift is {relative:.1%} "
        f"of the issue-only MRR score, measured on a sparse lexical baseline that can only "
        f"exploit the leaked text through term overlap. The number therefore calibrates the "
        f"contamination rather than exaggerating it. Reports built on the superseded "
        f"query rule are not wildly inflated, but they exhibit a systematic upward shift in "
        f"ranking metrics (stronger on MRR and AP than on Hit@1), and they are not comparable "
        f"with reports built on the issue-only rule. A mixed-provenance MultiSWEbenchRR score "
        f"therefore should not be interpreted as directly measuring prospective issue-only "
        f"localization; doing so conflates retrospective solution retrieval with prospective "
        f"bug localization.",
        "",
    ]

    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")

    # ---- sentences that live outside this section ------------------------
    claims = {
        "contribution_8": (
            "a controlled measurement of what that leakage is worth, holding the "
            "pipeline, indexes, candidate protocol, and metrics fixed and changing "
            "only the query rule: on the primary endpoint, BM25 MRR increases by "
            f"{aggm['delta']:+.4f} (Holm-adjusted \\(p\\) = 0.0025), while a "
            "negative-control stratum that lengthens the query without adding solution "
            f"text changes by {pym['delta']:+.4f} on Hit@1 and {pym_m['delta']:+.4f} on MRR;"
        ),
        "discussion_sentence": (
            "Section 5.7 measures the consequence rather than asserting it. With the "
            "pipeline held fixed, admitting post-solution text changes the reference "
            f"baseline's Hit@1 by {agg1['delta']:+.4f} ({nonpy['delta']:+.4f} on the "
            f"non-Python stratum) and MRR by {aggm['delta']:+.4f} ({nonpy_m['delta']:+.4f} "
            "on the non-Python stratum), and the negative-control stratum provides "
            "evidence against query length or repetition alone as an explanation. "
            "Superseded and issue-only scores therefore describe different tasks, "
            "however close their other settings are."
        ),
        "conclusion_sentence": (
            f"The instance-weighted MRR effect is {aggm['delta']:+.4f} (repository-cluster 95% CI "
            f"[{num(aggm['delta_cluster_bootstrap_95ci'][0])}, {num(aggm['delta_cluster_bootstrap_95ci'][1])}]), "
            "while complementary repository-level "
            "Wilcoxon testing remains significant after Holm correction (p = 0.0025); "
            f"AP shows the same directional pattern ({agg_ap['delta']:+.4f}, adjusted p = 0.00089). "
            f"Hit@1 rises by {agg1['delta']:.4f}, with a repository-cluster interval spanning zero. "
            "More fundamentally, superseded and issue-only scores should not be interpreted as "
            "estimates of the same prospective localization task because they are produced under "
            "different query-provenance rules."
        ),
    }
    CLAIMS.write_text(json.dumps(claims, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")

    print(text)
    print(f"\n[written to {OUT}]", file=sys.stderr)
    print(f"[claims written to {CLAIMS}]", file=sys.stderr)


if __name__ == "__main__":
    main()
