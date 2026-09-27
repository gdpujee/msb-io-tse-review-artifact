#!/usr/bin/env python3
"""Audit every headline number in the manuscript against results/tables_v2/.

Why this exists
---------------
The manuscript's numbers are *derived* quantities.  A silent change in the
candidate protocol, the metric implementation, or the aggregation path can make
a printed number wrong without making it obviously wrong.  This script closes
that gap: it reads the verified tables and asserts that the exact string printed
in the manuscript is the string derived from those tables.

Design rules (learned from this project's failure ledger)
--------------------------------------------------------
* Compare at the *printed precision* of the manuscript, never at float-noise
  precision.
* Assert the NEW value is present AND that no stale value survives anywhere in
  the file -- a one-directional check is fail-open.
* Derive the rendered string from the table cell; never retype it.
* Fail loudly, naming the claim, the expected string, and the file.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_DIR = ROOT / "results" / "tables_v2"
AUDIT_DIR = ROOT / "results" / "audit_v2"
FIG_DIR = ROOT / "results" / "figures"
RELEASE_DIR = ROOT / "benchmark" / "msb_io"
MANUSCRIPT = ROOT / "paper" / "manuscript_ESE_v2.md"

# Numbers that were correct under an earlier protocol and would be silently
# wrong now.  Append-only.
#
# A bare value is a valid control only while nothing else in the paper can
# legitimately print that same string.  One entry had to move out of this list
# for exactly that reason: 0.0816 was the graph-over-cues Hit@10 Holm-adjusted
# p-value until the correction made it 0.0864, and it now reappears legitimately
# as the dense reranker's JavaScript MRR delta.  A bare forbid fires on the new,
# correct claim, and the usual response to a false positive is to delete the
# control -- which re-opens the hole it was guarding.  It is controlled by role
# instead, below.
STALE = [
    "0.4020", "0.6092", "0.7063", "0.8135", "0.8744", "0.9419", "0.5351", "0.4389",
    "0.4327", "0.0307", "0.0135", "0.1575", "0.1461", "0.1228", "0.0648", "0.0927",
    "0.0525", "0.0631", "0.0516", "5,553", "0.2031",
]

# (label, string) pairs that anchor a superseded value in the role it held, so
# the control survives the value's legitimate reappearance somewhere else.
STALE_IN_ROLE = [
    ("stale graph Hit@10 Holm p-values",
     "Holm-adjusted p-values are 0.0816 and 0.0516"),
    ("stale graph Hit@10 Holm p-value pair", "0.0816 and 0.0516"),
]


def rows(name: str) -> list[dict]:
    with (TABLE_DIR / name).open() as handle:
        return list(csv.DictReader(handle))


def f4(value) -> str:
    """Render a numeric cell the way the manuscript prints it."""
    return f"{float(value):.4f}"


def f3(value) -> str:
    return f"{float(value):.3f}"


CAPTION_LINE = re.compile(r"^\*\*(Figure|Table) \d")


def float_citation_failures(text: str) -> list[str]:
    """Every figure has to be named in running text, in numerical order.

    IEEE's editorial style manual requires the first citations of figures and
    tables to appear in numerical order, which presupposes that each float is
    cited at all.  A caption or an image link is not a citation, so both are
    excluded here -- otherwise a table caption that happens to mention
    ``Figure 2`` would let Figure 2 pass uncited.
    """
    body = [line for line in text.splitlines()
            if not line.startswith("![") and not CAPTION_LINE.match(line)]
    out: list[str] = []
    first_seen: dict[int, int] = {}
    for number in range(1, 7):
        hits = [i for i, line in enumerate(body)
                if re.search(rf"Figure {number}\b", line)]
        if not hits:
            out.append(f"Figure {number} is never named in running text")
        else:
            first_seen[number] = hits[0]
    order = sorted(first_seen, key=lambda k: first_seen[k])
    if order != sorted(order):
        out.append(f"first figure citations are out of numerical order: {order}")
    return out


def table_denominator_failures(text: str) -> list[str]:
    """Every table has to say how many units its numbers are computed over.

    A printed effect size with no denominator cannot be re-derived by a reader
    (lesson 56). Fourteen of the fifteen floats carried one; Table 5 was the
    exception -- its three rows are paired comparisons over all 1,791 instances
    in 57 repository clusters, stated nowhere in the caption and in no column.

    Tables only. Figures are deliberately not swept: each one is a plot of a
    table that already carries its denominator, and their captions name units
    ("1,688 public queries", "14,328 verified runs", "the 313 cue queries")
    rather than an ``n =`` token, so a mechanical ``n =`` rule over figures
    would produce false alarms and nothing else.
    """
    lines = text.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        m = re.match(r"^\*\*Table (\d+)\.\*\*(.*)$", line)
        if not m:
            continue
        number, caption = m.group(1), m.group(2)
        if re.search(r"n\s*=\s*[\d,]+", caption):
            continue
        header = next((l for l in lines[i + 1:i + 6] if l.startswith("|")), "")
        if re.search(r"\|\s*n\s*\||\|\s*instances\s*\|", header, re.I):
            continue
        out.append(
            f"Table {number} states no denominator: the caption has no 'n =' and "
            f"the body has no n/instances column")
    return out


def float_position_failures(text: str) -> list[str]:
    """Every float must appear *after* its first in-text mention.

    IEEE's style manual: "Figures and tables should be placed in columns as close
    to their first mention as possible, but preferably after the mention." The
    existing gates check that a float is cited at all and that first citations
    are in numerical order; neither can see a float that is cited *but placed
    before* the sentence citing it. That was F034: Table 3 and Figure 5 were both
    in that position and both passed every gate then running.

    Only the caption and the image link are treated as the float itself; the
    table body follows its caption, so the caption index is the float's start.
    """
    lines = text.splitlines()
    out: list[str] = []

    def check(kind: str, number: int) -> None:
        cap_i = next((i for i, l in enumerate(lines)
                      if re.match(rf"^\*\*{kind} {number}\.\*\*", l)), None)
        if cap_i is None:
            out.append(f"{kind} {number}: no caption found")
            return
        img_i = next((i for i, l in enumerate(lines)
                      if re.match(rf"^!\[{kind} {number}\.", l)), None)
        start = min(i for i in (cap_i, img_i) if i is not None)
        cites = [i for i, l in enumerate(lines)
                 if i not in (cap_i, img_i) and not CAPTION_LINE.match(l)
                 and re.search(rf"{kind} {number}\b", l)]
        if not cites:
            return  # "never cited" is the citation gate's job, not this one
        if cites[0] > start:
            out.append(
                f"{kind} {number} is placed at L{start + 1}, before its first "
                f"mention at L{cites[0] + 1}")

    for number in range(1, 7):
        check("Figure", number)
    for number in range(1, 10):
        check("Table", number)
    return out


def main() -> int:
    text = MANUSCRIPT.read_text(encoding="utf-8")
    fails: list[str] = []
    checks = 0

    def expect(label: str, needle: str) -> None:
        nonlocal checks
        checks += 1
        if needle not in text:
            fails.append(f"{label}: manuscript does not contain {needle!r}")

    def forbid(label: str, needle: str) -> None:
        nonlocal checks
        checks += 1
        if needle in text:
            fails.append(f"{label}: manuscript still contains {needle!r}")

    # ---- Table 2: overall method means -----------------------------------
    t2 = {r["method"]: r for r in rows("t2_overall_method.csv")}
    for column in ("hit@1", "hit@3", "hit@5", "hit@10", "hit@20", "hit@50", "mrr", "ap"):
        expect(f"overall bm25 {column}", f4(t2["bm25"][column]))

    # ---- Table 1: per-language BM25 --------------------------------------
    t1 = {(r["lang"], r["method"]): r for r in rows("t1_lang_method.csv")}
    for lang in ("c", "cpp", "go", "java", "js", "kotlin", "python", "rust", "ts"):
        for column in ("hit@1", "hit@10", "hit@50", "mrr"):
            expect(f"{lang} bm25 {column}", f4(t1[(lang, "bm25")][column]))

    # ---- Table 3c: matched ablations (magnitudes as printed) -------------
    for row in rows("t3c_matched_ablation.csv"):
        if row["metric"] == "hit@1" and row["component"] in {
            "path-text weighting", "explicit path cue", "graph over BM25",
            "graph over both cues", "graph over path cue",
        }:
            expect(f"t3c hit@1 {row['component']}", f4(abs(float(row["delta"]))))
        if row["metric"] == "mrr" and row["component"] == "explicit path cue":
            expect("t3c mrr explicit path cue", f4(abs(float(row["delta"]))))

    # ---- Table 3d: cue strata for the path-cue configuration -------------
    for row in rows("t3d_path_cue_strata.csv"):
        if row["method"] == "anchor_path_only" and row["metric"] in {"hit@1", "hit@10", "mrr"}:
            expect(f"t3d {row['metric']} cue={row['gold_path_cue']}",
                   f4(abs(float(row["delta"]))))

    # ---- Table 3b: cross-language sign tests ----------------------------
    for row in rows("t3b_cross_language.csv"):
        if row["metric"] == "hit@1" and row["method"] in {"anchor_path_only", "bm25_graph"}:
            expect(f"sign test {row['method']}", f4(row["sign_test_p"]))

    # ---- Table 5: gold accounting ---------------------------------------
    t5 = rows("t5_gold_accounting.csv")
    expect("total non-test gold files", f"{sum(int(r['gold_files_all']) for r in t5):,}")
    unreachable_instances = sum(int(r["inst_without_evaluable_gold"]) for r in t5)
    expect("instances without reachable gold", str(unreachable_instances))
    # The checklist in Section 6.5 states the same count in prose.  It once said
    # 24 while Section 5.5 said 23, because the correction had landed in only one
    # of the two places.  A bare forbid("24") is unusable -- "24" occurs inside
    # years and other numbers -- so the control is the stale phrase in context.
    expect("checklist reachability sentence",
           f"and {unreachable_instances} instances have no reachable non-test gold file")
    forbid("stale checklist reachability sentence",
           "24 instances have no reachable non-test gold file")
    for row in t5:
        expect(f"t5 {row['lang']} excluded fraction", f3(row["frac_excluded"]))

    # ---- Table 5b: protocol sensitivity on C and Java -------------------
    for row in rows("t5b_protocol_sensitivity.csv"):
        if row["method"] != "bm25":
            continue
        if row["lang"] == "c":
            expect("C any-target Hit@1", f4(row["any_hit1_unconditional"]))
            expect("C candidate-conditional Hit@1", f4(row["any_hit1_conditional"]))
            expect("C all-target Hit@1", f4(row["all_target_hit1"]))
        if row["lang"] == "java":
            expect("Java any-target Hit@1", f4(row["any_hit1_unconditional"]))
            expect("Java all-target Hit@1", f4(row["all_target_hit1"]))

    # ---- Table 10: error strata (JSON companion) ------------------------
    t10 = json.loads((TABLE_DIR / "t10_error_strata.json").read_text())
    strata = {r["stratum"]: r for r in t10["rows"] if r["method"] == "bm25"}
    for name in ("query tokens Q1 (min\u201389)", "query tokens Q4 (270\u2013max)",
                 "gold files = 1", "gold files = 2"):
        if name in strata:
            expect(f"t10 {name} hit@1", f4(strata[name]["hit@1"]))
    if "query tokens Q4 (270\u2013max)" in strata:
        expect("t10 Q4 hit@10", f4(strata["query tokens Q4 (270\u2013max)"]["hit@10"]))

    # ---- structural checks ----------------------------------------------
    checks += 1
    if text.count("![Figure") != 6:
        fails.append(f"expected 6 figure links, found {text.count('![Figure')}")
    checks += 1
    if text.count("**Figure ") != 6:
        fails.append(f"expected 6 figure captions, found {text.count('**Figure ')}")
    for n in (1, 2, 3, 4, 5, 6, 7, 8, 9):
        expect(f"table caption {n}", f"**Table {n}.**")
        expect(f"in-text table reference {n}", f"(Table {n})")
    for fig in ("fig1_provenance", "fig2_heatmap_hit1", "fig3_cue_strata",
                "fig4_reachability", "fig5_leak_cost", "fig6_rank_shift"):
        checks += 1
        if not (FIG_DIR / f"{fig}.png").exists():
            fails.append(f"missing figure file: {fig}.png")
    # Figures 1-4 and 6 were shipped without ever being named in the prose
    # (F032).  Counting links and captions cannot see that, so the citation is
    # checked here.
    # One check, not one per failure: the reported total used to grow with the
    # number of failures, which makes "N assertions" an unstable quantity.
    citation_problems = float_citation_failures(text)
    checks += 1
    fails.extend(citation_problems)
    denominator_problems = table_denominator_failures(text)
    checks += 1
    fails.extend(denominator_problems)
    position_problems = float_position_failures(text)
    checks += 1
    fails.extend(position_problems)

    # ---- Table 1: query-level leakage (from the leakage gate) ------------
    leakage = json.loads((AUDIT_DIR / "query_leakage.json").read_text())
    released = leakage["protocols"]["issue_only"]
    legacy = leakage["protocols"]["legacy_mixed"]
    if leakage.get("status") != "VERIFIED":
        fails.append(f"leakage gate status is {leakage.get('status')}, not VERIFIED")
    if released["residual_unexplained"] != 0:
        fails.append("released protocol has unattributable title matches")
    if released["residual_body_unexplained"] != 0:
        fails.append("released protocol has unattributable body-span matches")
    total = released["instances"]

    # The table's two match counts must be fully accounted for by the
    # attribution columns, for both materializations.  A row that does not add
    # up is the failure this table exists to prevent, so it is checked here
    # rather than trusted.
    for name, block in (("superseded", legacy), ("released", released)):
        title_parts = (block["attributed_issue_title"] + block["attributed_issue_proposal"]
                       + block["attributed_pr_reference"] + block["residual_unexplained"])
        if title_parts != block["pr_title_in_query"]:
            fails.append(f"{name} title matches do not add up: "
                         f"{title_parts} vs {block['pr_title_in_query']}")
        body_parts = (block["body_attributed_issue_text"]
                      + block["body_attributed_pr_reference"]
                      + block["residual_body_unexplained"])
        if body_parts != block["pr_body_in_query"]:
            fails.append(f"{name} body matches do not add up: "
                         f"{body_parts} vs {block['pr_body_in_query']}")

    def row(prefix: str, block: dict) -> str:
        title_pre = (block["attributed_issue_title"]
                     + block["attributed_issue_proposal"])
        return (f"| {prefix} | {block['pr_title_in_query']:,} "
                f"({block['pr_title_in_query_fraction']:.1%}) | "
                f"{block['pr_body_in_query']:,} ({block['pr_body_in_query_fraction']:.1%}) | "
                f"{title_pre} | {block['attributed_pr_reference']:,} | "
                f"{block['residual_unexplained']:,} | "
                f"{block['body_attributed_issue_text']:,} | "
                f"{block['body_attributed_pr_reference']:,} | "
                f"{block['residual_body_unexplained']:,} |")

    expect("Table 1 superseded row", row("Superseded (concatenated PR text)", legacy))
    expect("Table 1 released row", row("Released (issue-only)", released))
    expect("superseded title count in prose",
           f"{legacy['pr_title_in_query']:,} of {total:,} queries "
           f"({legacy['pr_title_in_query_fraction']:.1%})")
    expect("superseded body count in prose",
           f"of the PR body in {legacy['pr_body_in_query']:,} "
           f"({legacy['pr_body_in_query_fraction']:.1%})")
    attributable = (legacy["attributed_issue_title"] + legacy["attributed_issue_proposal"]
                    + legacy["body_attributed_issue_text"])
    expect("superseded pre-solution count in prose",
           f"only {attributable} of those matches are attributable to pre-solution text")
    expect("released title count in prose",
           f"contains the PR title in {released['pr_title_in_query']} queries "
           f"({released['pr_title_in_query_fraction']:.1%})")
    expect("released body count in prose",
           f"of the PR body in {released['pr_body_in_query']} "
           f"({released['pr_body_in_query_fraction']:.1%})")
    expect("released issue_title attribution in prose",
           f"{released['attributed_issue_title']} because the pull request is named after")
    expect("released issue_proposal attribution in prose",
           f"{released['attributed_issue_proposal']} because the reporter")
    residual = released["attributed_pr_reference"]
    expect("residual count in prose", f"{residual} ({residual / total:.1%})")
    expect("Discussion restatement of the residual",
           f"{residual} of {total:,} queries ({residual / total:.1%})")
    # The lower-bound caveat, with all three numbers derived from the gate.
    expect("unexamined body overlaps are counted",
           f"leaves {released['body_on_other_pr_line']} of the "
           f"{released['pr_body_in_query']} body overlaps unexamined")
    expect("unexamined body overlaps are broken down",
           f"Inspecting those {released['body_on_other_pr_line']}, "
           f"{released['body_on_bot_pr_line']} are GitHub merge-queue bot lines")
    unexamined_other = (released["body_on_other_pr_line"]
                        - released["body_on_bot_pr_line"])
    expect("remaining unexamined overlaps are described",
           f"and {unexamined_other} cite an unrelated earlier pull request")
    expect("released benchmark is named", "MSB-IO")

    # ---- MSB-IO release: consistent with the manuscript's accounting ------
    availability_path = RELEASE_DIR / "field_availability.csv"
    if not availability_path.exists():
        fails.append("benchmark/msb_io/field_availability.csv is missing")
        availability = []
    else:
        with availability_path.open() as handle:
            availability = list(csv.DictReader(handle))
    release_instances = sum(int(r["instances"]) for r in availability)
    if release_instances != total:
        fails.append(f"release has {release_instances} instances, leakage gate has {total}")
    if sum(int(r["gold_files_all"]) for r in availability) != sum(
            int(r["gold_files_all"]) for r in t5):
        fails.append("release gold-file total disagrees with Table 5")
    if sum(int(r["instances_without_evaluable_gold"]) for r in availability) != sum(
            int(r["inst_without_evaluable_gold"]) for r in t5):
        fails.append("release unreachable-gold count disagrees with Table 5")
    for r in availability:
        if r["lang"] != "python" and int(r["query_from_problem_statement"]) != 0:
            fails.append(f"{r['lang']} claims problem_statement queries")
    python_rows = [r for r in availability if r["lang"] == "python"]
    if not python_rows or int(python_rows[0]["query_from_resolved_issues"]) != 0:
        fails.append("python should draw its query from problem_statement only")

    manifest_path = RELEASE_DIR / "MANIFEST.sha256"
    if not manifest_path.exists():
        fails.append("benchmark/msb_io/MANIFEST.sha256 is missing")
    else:
        listed = {}
        for line in manifest_path.read_text().splitlines():
            if line.strip():
                digest, name = line.split(None, 1)
                listed[name.strip()] = digest
        present = sorted(f.name for f in RELEASE_DIR.iterdir()
                         if f.is_file() and f.name != "MANIFEST.sha256")
        if sorted(listed) != present:
            fails.append(f"manifest lists {sorted(listed)}, directory holds {present}")
        for name, digest in listed.items():
            actual = hashlib.sha256((RELEASE_DIR / name).read_bytes()).hexdigest()
            if actual != digest:
                fails.append(f"manifest hash mismatch for {name}")

    # ---- Table 3: dense reranking (from the dense generator) --------------
    t11 = json.loads((TABLE_DIR / "t11_swerank_reranker.json").read_text())
    agg = t11["aggregate"]
    if agg["n"] != total:
        fails.append(f"dense table covers {agg['n']} instances, leakage gate has {total}")
    if t11["done"].get("query_protocol") != "issue_only_v2":
        fails.append("dense rows were not produced under the released query protocol")
    if t11["done"].get("cap") or t11["done"].get("limit"):
        fails.append("dense run was capped or limited")
    protocol = json.loads((AUDIT_DIR / "protocol_audit.json").read_text())

    def signed(value: float) -> str:
        """Print a delta the way the tables do: no sign on a zero, U+2212 minus."""
        if abs(value) < 5e-5:
            return "0.0000"
        return f"{value:+.4f}".replace("-", "\u2212")

    labels = {"c": "C", "cpp": "C++", "go": "Go", "java": "Java", "js": "JavaScript",
              "kotlin": "Kotlin", "python": "Python", "rust": "Rust", "ts": "TypeScript"}
    lang = {item["lang"]: item for item in t11["per_language"]}
    for name in labels:
        item = lang[name]
        expect(f"Table 3 {name} row",
               f"| {labels[name]} | {item['n']} | {item['bm25_hit1']:.4f} | "
               f"{item['model_hit1']:.4f} | {signed(item['model_hit1'] - item['bm25_hit1'])} | "
               f"{item['bm25_hit10']:.4f} | {item['model_hit10']:.4f} | "
               f"{signed(item['model_mrr'] - item['bm25_mrr'])} | {item['model_secs']:.3f} |")
    bm25, model = agg["bm25"], agg["model"]
    expect("Table 3 aggregate row",
           f"| **All** | {agg['n']:,} | {bm25['hit@1']:.4f} | {model['hit@1']:.4f} | "
           f"**{signed(model['hit@1'] - bm25['hit@1'])}** | {bm25['hit@10']:.4f} | "
           f"{model['hit@10']:.4f} | {signed(model['mrr'] - bm25['mrr'])} | "
           f"{model['secs']:.3f} |")
    expect("dense aggregate deltas in prose",
           f"raises Hit@1 by {model['hit@1'] - bm25['hit@1']:.4f} and MRR by "
           f"{model['mrr'] - bm25['mrr']:.4f}, and lowers Hit@10 by "
           f"{bm25['hit@10'] - model['hit@10']:.4f}")
    holm = {item["metric"]: item["p_cluster_holm"] for item in t11["comparisons"]}
    expect("dense Holm-adjusted p-values in prose",
           f"= {holm['hit@1']:.3f}, {holm['mrr']:.3f}, and {holm['hit@10']:.3f}")
    # The resolution of the comparison, stated so that "not significant" is not
    # read as "equivalent".  Derived from the interval, not typed in.
    hit1_ci = [item for item in t11["comparisons"] if item["metric"] == "hit@1"][0][
        "delta_cluster_bootstrap_95ci"]
    expect("dense resolution in prose", f"about {(hit1_ci[1] - hit1_ci[0]) / 2:.3f} Hit@1")
    expect("dense cost in prose",
           f"{model['secs']:.3f} s per instance against {bm25['secs']:.3f} s for BM25")
    expect("dense TypeScript gain in prose",
           f"from {lang['ts']['bm25_hit1']:.4f} to {lang['ts']['model_hit1']:.4f} on TypeScript")
    for name in ("js", "go", "java"):
        expect(f"dense {name} gain in prose",
               f"{lang[name]['model_hit1'] - lang[name]['bm25_hit1']:.4f} on "
               f"{labels[name]}")
    expect("dense C++ loss in prose",
           f"by {lang['cpp']['bm25_hit1'] - lang['cpp']['model_hit1']:.4f} on C++")
    expect("dense Rust loss in prose",
           f"and {lang['rust']['bm25_hit1'] - lang['rust']['model_hit1']:.4f} on Rust")
    sign = t11["sign_test"]
    expect("dense sign counts in prose",
           f"{sign['up']} of the {sign['languages']} languages improve, {sign['down']} "
           f"worsen, and {sign['tied']} is unchanged")
    expect("dense sign test in prose",
           f"over the {sign['up'] + sign['down']} non-tied languages, \\(p\\) = "
           f"{sign['p_two_sided_exact']:.3f}")
    cues = {item["stratum"]: item for item in t11["cue_strata"]}
    expect("dense cue-absent stratum in prose",
           f"it is {cues['absent']['delta']:+.4f} on the {cues['absent']['n']:,} "
           f"cue-absent queries")
    expect("dense cue-present stratum in prose",
           f"and {cues['present']['delta']:+.4f} on the {cues['present']['n']} "
           f"cue-present ones")
    # The small-panel caveat quotes each language's panel size and repository
    # count; both come from released tables rather than from the prose.
    for name in ("ts", "js"):
        expect(f"dense {name} panel size in prose", f"{lang[name]['n']} instances in "
               f"{protocol['per_language'][name]['repositories']} repositories")
    expect("contamination threat quotes the measured dense delta",
           f"moves aggregate Hit@1 by {model['hit@1'] - bm25['hit@1']:.4f} with a "
           "repository-cluster interval containing zero")
    expect("threats state the leakage residual is a lower bound",
           "the residual rule counts a reference only to the instance's own pull "
           "request, so the residual is a lower bound")

    # ---- Section 5.7 and Table 7: the cost of leakage (RQ6) --------------
    t12 = json.loads((TABLE_DIR / "t12_leak_contrast.json").read_text())
    if t12["protocols"] != {"control": "issue_only_v2", "treatment": "legacy_mixed_v1"}:
        fails.append(f"contrast arms carry unexpected protocols: {t12['protocols']}")
    premise = t12["premise"]
    if premise["python_treatment_contains_pr_text"] != 0:
        fails.append("the Python stratum is not an information-matched control")
    if premise["python_treatment_is_repeated_issue_text"] != premise["python_instances"]:
        fails.append("the Python treatment query is not the repeated issue text")
    if premise["python_pr_fields_are_placeholder_literal"] != premise["python_instances"]:
        fails.append("the Python pull-request fields are not all the literal 'placeholder'")
    if premise["non_python_treatment_contains_pr_title"] != premise["non_python_instances"]:
        fails.append("the non-Python treatment query does not carry the PR title")
    if premise["python_instances"] + premise["non_python_instances"] != total:
        fails.append("the contrast strata do not partition the instance set")
    for arm in ("control", "treatment"):
        if t12["query_hashes_checked"][arm] != t12["rows"][arm]:
            fails.append(f"{arm} contrast rows were not all hash-checked")
        if t12["rows"][arm] != total * 8:
            fails.append(f"{arm} arm has {t12['rows'][arm]} rows, expected {total * 8}")
    if len({item["arm_method"] for item in t12["comparisons"]}) != 8:
        fails.append("the contrast does not cover all eight configurations")

    # The section and the sentences it exports elsewhere are generated from the
    # contrast table, so asserting that they appear verbatim makes the coupling
    # byte-exact instead of "looks the same to a reader".
    t12_section = (TABLE_DIR / "t12_leak_contrast_section.md").read_text(encoding="utf-8")
    for block in [part.strip() for part in t12_section.split("\n\n") if part.strip()]:
        expect("Section 5.7 block", block)
    t12_claims = json.loads((TABLE_DIR / "t12_leak_contrast_claims.json").read_text())
    for name, sentence in t12_claims.items():
        expect(f"RQ6 claim {name}", sentence)

    # ---- the dense treatment arm, when it has run ------------------------
    # Conditional for the same reason the section generator is: an arm that has
    # not run must not be claimed.  If it is claimed, the file must be sound.
    t13_path = TABLE_DIR / "t13_dense_leak_contrast.json"
    if t13_path.exists():
        t13 = json.loads(t13_path.read_text())
        if t13["protocols"] != {"control": "issue_only_v2", "treatment": "legacy_mixed_v1"}:
            fails.append(f"dense contrast carries unexpected protocols: {t13['protocols']}")
        if t13["rows"] != {"control": total, "treatment": total}:
            fails.append(f"dense contrast arms cover {t13['rows']}, expected {total} each")
        for key in ("model_revision", "remote_code_revision", "candidate_k",
                    "max_seq_length", "metric_protocol"):
            if not t13["configuration"].get(key):
                fails.append(f"dense contrast does not record {key}")
        strata = {item["stratum"] for item in t13["comparisons"]}
        if strata != {"all", "non_python", "python"}:
            fails.append(f"dense contrast covers strata {sorted(strata)}")
        if {item["stratum"] for item in t13["difference_in_differences"]} != strata:
            fails.append("dense contrast lacks a difference-in-differences per stratum")
        if "A second treatment arm applies the same manipulation to the dense" not in text:
            fails.append("the dense arm has run but the manuscript does not describe it")
    elif "A second treatment arm applies the same manipulation to the dense" in text:
        fails.append("the manuscript claims a dense treatment arm that has not run")

    # ---- RQ7: does the leakage change the comparison? ---------------------
    # Section 5.8 makes three claims that a regeneration could silently falsify:
    # that the leader is unchanged, that exactly one configuration improves, and
    # that exactly one Hit@1 interval excludes zero.  They are re-derived here
    # from the released table rather than trusted from the prose.
    t14_path = TABLE_DIR / "t14_leak_ranking.json"
    t14_claims: dict | None = None
    if not t14_path.exists():
        fails.append("the manuscript reports RQ7 but "
                     "results/tables_v2/t14_leak_ranking.json is absent")
    else:
        t14 = json.loads(t14_path.read_text())
        if (t14["control_protocol"], t14["treatment_protocol"]) != (
                "issue_only_v2", "legacy_mixed_v1"):
            fails.append(f"RQ7 reads unexpected protocols: "
                         f"{t14['control_protocol']!r}, {t14['treatment_protocol']!r}")
        methods = list(t14["per_method"])
        if len(methods) != t14["n_methods"]:
            fails.append("RQ7 n_methods disagrees with its per-method table")
        if t14["n_instances"] != total:
            fails.append(f"RQ7 covers {t14['n_instances']} instances, "
                         f"expected {total}")
        for metric in ("hit@1", "mrr"):
            agree = t14["agreement"][metric]
            if not agree["leader_unchanged"]:
                fails.append(f"RQ7: the leader changes by {metric}, but Section 5.8 "
                             f"says it does not")
            order_c = t14["ordering"][metric]["issue_only"]
            order_t = t14["ordering"][metric]["superseded"]
            if sorted(order_c) != sorted(methods) or sorted(order_t) != sorted(methods):
                fails.append(f"RQ7 {metric} ordering does not cover every configuration")
                continue
            rank_c = {m: i for i, m in enumerate(order_c)}
            rank_t = {m: i for i, m in enumerate(order_t)}
            improved = [m for m in methods if rank_t[m] < rank_c[m]]
            if len(improved) != 1:
                fails.append(f"RQ7 {metric}: {len(improved)} configurations improve, "
                             f"but Section 5.8 says only one does")
        only_h1 = [m for m in methods
                   if t14["per_method"][m]["hit@1"]["delta_ci"][0] > 0
                   or t14["per_method"][m]["hit@1"]["delta_ci"][1] < 0]
        top = max(methods, key=lambda m: t14["per_method"][m]["mrr"]["delta"])
        if only_h1 != [top]:
            fails.append(f"RQ7: the configurations whose Hit@1 interval excludes zero "
                         f"are {only_h1}, but Section 5.8 names only {top}")
        for flip in t14["flips"]:
            if top not in (flip["favoured_under_issue_only"],
                           flip["favoured_under_superseded"]):
                fails.append(f"RQ7: a flipped pair does not involve {top}, but "
                             f"Section 5.8 says all of them do")
        if t14["mechanism_query_mentions_gold_path"]["python"]["delta"] != 0.0:
            fails.append("RQ7: the control stratum's path-mention share moves, but "
                         "Section 5.8 says it does not move at all")

        # The section and the sentences it exports are generated from that table,
        # so asserting they appear verbatim makes the coupling byte-exact.
        t14_section = (TABLE_DIR / "t14_leak_ranking_section.md").read_text(
            encoding="utf-8")
        for block in [part.strip() for part in t14_section.split("\n\n") if part.strip()]:
            expect("Section 5.8 block", block)
        t14_claims = json.loads(
            (TABLE_DIR / "t14_leak_ranking_claims.json").read_text())
        for name, sentence in t14_claims.items():
            expect(f"RQ7 claim {name}", sentence)
        # F031: the abstract and the conclusion used to say the leak "shifts the
        # ranking of the rest" while this very section says "Every other position
        # is identical under the two rules".  Both sentences now have to carry
        # the count of moved configurations derived above, so the phrase cannot
        # silently come back.
        moved_h1 = len(t14["agreement"]["hit@1"]["moved"])
        moved_mrr = len(t14["agreement"]["mrr"]["moved"])
        checks += 1
        if (f"{moved_h1} of the remaining configurations by Hit@1"
                not in t14_claims["abstract_sentence"]):
            fails.append("RQ7 abstract sentence does not name the "
                         f"{moved_h1} configurations that move by Hit@1")
        checks += 1
        if (f"{moved_mrr} of the remaining configurations by MRR and "
                f"{moved_h1} by Hit@1"
                not in t14_claims["conclusion_sentence"]):
            fails.append("RQ7 conclusion sentence does not name the "
                         f"{moved_mrr}/{moved_h1} configurations that move")
    # ---- RQ5, third part: the aggregation itself (F033) ------------------
    # RQ5 asks how much repository-cluster aggregation changes the reported
    # result.  Section 5.5 used to answer only the other two parts and left this
    # one qualitative, even though the artifact has shipped the comparison all
    # along.  Both numbers are derived from that table, so a regeneration that
    # changes them makes this fail.
    micro_macro = rows("t7_micro_vs_macro.csv")
    bm25_agg = {r["lang"]: r for r in micro_macro if r["method"] == "bm25"}
    for lang in ("js", "rust"):
        expect(f"micro-vs-macro BM25 Hit@1 delta ({lang})",
               signed(float(bm25_agg[lang]["diff_hit@1"])))

    # ---- abstract length -------------------------------------------------
    # A constraint, not a stated value: the limit does not go stale when the
    # text changes, so this check never needs maintenance.
    abstract = re.search(r"## Abstract\n\n(.*?)\n\n\*\*Keywords", text, re.S)
    checks += 1
    if not abstract:
        fails.append("cannot locate the abstract block")
    else:
        words = len(abstract.group(1).split())
        if words > 250:
            fails.append(f"abstract is {words} words, over the 250-word limit")
        # The claim checks above only prove the sentence is somewhere in the
        # manuscript.  The sentence it replaces was in the abstract, so the
        # replacement has to be in the abstract too.
        checks += 1
        if t14_claims is not None and \
                t14_claims.get("abstract_sentence") not in abstract.group(1):
            fails.append("the RQ7 abstract sentence is not inside the abstract block")

    # ---- citation integrity ---------------------------------------------
    # Every reference must be cited and every citation must have an entry.  The
    # key is (first author surname, year with any a/b suffix); two works sharing
    # a key would make the check blind, so that is a failure in its own right.
    body_text, refs_text = text.split("## References", 1)
    entries = [line[2:].strip() for line in refs_text.splitlines() if line.startswith("- ")]

    def ref_key(entry: str) -> tuple[str, str | None]:
        head = entry.split("(", 1)[0]
        surname = re.split(r"[,\s]", head.strip())[0]
        year = re.search(r"\((\d{4}[a-z]?)", entry)
        return (surname, year.group(1) if year else None)

    ref_keys = [ref_key(e) for e in entries]
    ref_set = set(ref_keys)

    cites: set[tuple[str, str]] = set()
    for group in re.findall(r"\(([^()]*?(?:19|20)\d{2}[a-z]?(?:[^()]*?)?)\)", body_text):
        for part in group.split(";"):
            year = re.search(r"(\d{4}[a-z]?)\s*$", part.strip())
            if not year:
                continue
            names = re.findall(r"([A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dc][\w\u00c7\u011e\u0130\u00d6\u015e\u00dc\u00e7\u011f\u0131\u00f6\u015f\u00fc'\-]+)(?: et al\.)?", part)
            if names:
                cites.add((names[0], year.group(1)))
    for match in re.finditer(r"([A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dc][\w\u00c7\u011e\u0130\u00d6\u015e\u00dc\u00e7\u011f\u0131\u00f6\u015f\u00fc'\-]+)(?: et al\.)?\s\((\d{4}[a-z]?)\)", body_text):
        cites.add((match.group(1), match.group(2)))

    checks += 1
    if len(ref_set) != len(ref_keys):
        duplicates = sorted({k for k in ref_keys if ref_keys.count(k) > 1})
        fails.append(f"reference list has ambiguous keys {duplicates}")
    checks += 1
    for key in sorted(cites - ref_set):
        fails.append(f"citation without a reference entry: {key}")
    checks += 1
    for key in sorted(ref_set - cites):
        fails.append(f"reference never cited in the text: {key}")

    # ---- declarations ----------------------------------------------------
    for label in ("Data and code availability",
                  "Funding", "Competing interests", "CRediT"):
        expect(f"declaration: {label}", f"**{label}")
    # The AI-use disclosure lives in the (unnumbered) Acknowledgment section,
    # per IEEE Author Center submission/peer-review policy, not Declarations.
    expect("acknowledgment: Generative AI disclosure",
           "Generative AI systems (specifically gpt-6-sol, gpt-6-astra")

    # ---- stale-value sweep ----------------------------------------------
    for bad in STALE:
        forbid("stale sweep", bad)
    for label, phrase in STALE_IN_ROLE:
        forbid(label, phrase)

    # Section 8 prints a concrete assertion count.  A count in prose is an
    # environment quantity: it goes stale the moment a check is added, and a
    # stale count is a false claim.  Bind it to the number this run performs.
    # Not counted as a check, so the printed number is the count of content
    # assertions only.
    stated = re.search(r"it currently carries (\d+) assertions", text)
    if not stated:
        fails.append("Section 8 does not state the assertion count")
    elif int(stated.group(1)) != checks:
        fails.append(f"Section 8 claims {stated.group(1)} assertions, "
                     f"this run performs {checks}")

    print(f"checks: {checks}")
    if fails:
        print(f"FAILED ({len(fails)})")
        for item in fails:
            print("  -", item)
        return 1
    print("VERIFIED: every audited manuscript number matches results/tables_v2/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
