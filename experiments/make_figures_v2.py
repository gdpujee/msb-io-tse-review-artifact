#!/usr/bin/env python3
"""Generate submission figures for Protocol V2 from verified artifacts only.

Gate: refuses to run unless results/audit_v2/result_integrity.json reports
status VERIFIED. Every figure is regenerated from raw artifacts on each run;
no hand editing of PNGs.

Figures (G4 / P1-4):
  fig1_provenance.png — per-language stacked query-provenance bars
  fig2_heatmap_hit1.png — language x method Hit@1 heatmap
  fig3_cue_strata.png — path-cue stratification (present vs absent)
  fig4_reachability.png — per-language excluded-gold fraction
  fig5_leak_cost.png — per-language BM25 Hit@1 under both query rules (RQ6)
  fig6_rank_shift.png — configuration rank under both query rules (RQ7)
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mplconfig")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "results" / "raw_v2"
AUDIT_DIR = ROOT / "results" / "audit_v2"
FIG_DIR = ROOT / "results" / "figures"

LANGS = ("c", "cpp", "go", "java", "js", "kotlin", "python", "rust", "ts")
METHODS = (
    "bm25",
    "bm25_path",
    "anchor_path_only",
    "anchor_symbol_only",
    "bm25_anchor",
    "bm25_graph",
    "bm25_anchor_graph",
    "anchor_path_graph",
)
METHOD_SHORT = {
    "bm25": "BM25",
    "bm25_path": "+pathx3",
    "anchor_path_only": "+pathcue",
    "anchor_symbol_only": "+symcue",
    "bm25_anchor": "+bothcues",
    "bm25_graph": "+graph",
    "bm25_anchor_graph": "+cues+graph",
    "anchor_path_graph": "+pathcue+graph",
}


def gate() -> None:
    report_path = AUDIT_DIR / "result_integrity.json"
    if not report_path.exists():
        raise SystemExit("REFUSE: result_integrity.json missing; run verify_results_v2.py first")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "VERIFIED":
        raise SystemExit(f"REFUSE: integrity status is {report.get('status')}, not VERIFIED")


def load_rows() -> list[dict]:
    rows = []
    for lang in LANGS:
        path = RAW_DIR / f"main_{lang}.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def fig1_provenance() -> Path:
    audit = json.loads((AUDIT_DIR / "mteb_query_audit.json").read_text(encoding="utf-8"))
    per_lang_pr: dict[str, int] = defaultdict(int)
    per_lang_issue: dict[str, int] = defaultdict(int)
    for lang, counts in audit["per_language_exact_matches"].items():
        per_lang_pr[lang] = counts.get("pr_only_exact", 0)
    for rec in audit["records"]:
        for match in rec.get("issue_matches", []):
            per_lang_issue[match.split("/", 1)[0]] += 1
    n_unclassified = audit["counts"]["unmatched"]
    langs = [lang for lang in LANGS if (per_lang_pr[lang] or per_lang_issue[lang])]
    pr = [per_lang_pr[lang] for lang in langs]
    issue = [per_lang_issue[lang] for lang in langs]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    y = np.arange(len(langs))
    ax.barh(y, pr, label="PR-only (post-solution)", color="#c0392b")
    ax.barh(y, issue, left=pr, label="Issue-only (pre-solution)", color="#2471a3")
    for i, lang in enumerate(langs):
        ax.text(pr[i] + issue[i] + 8, i, f"{pr[i]}/{issue[i]}", va="center", fontsize=8)
    ax.set_yticks(y, langs)
    ax.set_xlabel("Queries (exact provenance match)")
    ax.set_title(
        f"MTEB MultiSWEbenchRR query provenance (n=1688; "
        f"{n_unclassified} unclassified, language n/a)"
    )
    ax.legend(loc="lower right")
    fig.tight_layout()
    out = FIG_DIR / "fig1_provenance.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def fig2_heatmap(rows: list[dict]) -> Path:
    grid = np.full((len(LANGS), len(METHODS)), np.nan)
    for i, lang in enumerate(LANGS):
        for j, method in enumerate(METHODS):
            vals = [r["hit@1"] for r in rows if r["lang"] == lang and r["method"] == method]
            grid[i, j] = sum(vals) / len(vals) if vals else np.nan
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    im = ax.imshow(grid, vmin=0, vmax=0.8, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(METHODS)), [METHOD_SHORT[m] for m in METHODS], rotation=30, ha="right")
    ax.set_yticks(range(len(LANGS)), LANGS)
    for i in range(len(LANGS)):
        for j in range(len(METHODS)):
            ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center", fontsize=7,
                    color="white" if grid[i, j] > 0.45 else "black")
    ax.set_title("Hit@1 by language and configuration (issue-only Protocol V2)")
    fig.colorbar(im, ax=ax, label="Hit@1")
    fig.tight_layout()
    out = FIG_DIR / "fig2_heatmap_hit1.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def fig3_cue_strata(rows: list[dict]) -> Path:
    base = {(r["lang"], r["instance_id"]): r for r in rows if r["method"] == "bm25"}
    path = {(r["lang"], r["instance_id"]): r for r in rows if r["method"] == "anchor_path_only"}
    strata = {}
    for cue, label in ((False, "absent"), (True, "present")):
        keys = [k for k, r in base.items() if bool(r["query_mentions_gold_path"]) == cue]
        strata[label] = {
            "n": len(keys),
            "bm25": sum(base[k]["hit@1"] for k in keys) / len(keys),
            "path": sum(path[k]["hit@1"] for k in keys) / len(keys),
        }
    labels = ["absent", "present"]
    x = np.arange(len(labels))
    bm25_vals = [strata[l]["bm25"] for l in labels]
    path_vals = [strata[l]["path"] for l in labels]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.bar(x - 0.2, bm25_vals, 0.4, label="BM25", color="#7f8c8d")
    bars = ax.bar(x + 0.2, path_vals, 0.4, label="+path cue", color="#2980b9")
    ymax = max(path_vals) * 1.40
    for i, l in enumerate(labels):
        delta = path_vals[i] - bm25_vals[i]
        ax.annotate(f"n={strata[l]['n']}\nΔ{delta:+.4f}",
                    xy=(x[i] + 0.2, path_vals[i]), xytext=(0, 8),
                    textcoords="offset points", ha="center", fontsize=9,
                    clip_on=False)
    ax.set_ylim(0, ymax)
    ax.set_xticks(x, [f"gold path {l}" for l in labels])
    ax.set_ylabel("Hit@1")
    ax.set_title("Path-cue gain is conditional on the answer being in the query")
    ax.legend()
    fig.tight_layout()
    out = FIG_DIR / "fig3_cue_strata.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def fig4_reachability(rows: list[dict]) -> Path:
    langs, fracs, totals = [], [], []
    for lang in LANGS:
        bm25_rows = [r for r in rows if r["lang"] == lang and r["method"] == "bm25"]
        all_gold = sum(r.get("n_gold_all", 0) for r in bm25_rows)
        excluded = sum(r.get("n_gold_excluded", 0) for r in bm25_rows)
        langs.append(lang)
        fracs.append(excluded / all_gold if all_gold else 0.0)
        totals.append(all_gold)
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    bars = ax.bar(langs, fracs, color="#8e44ad")
    for b, f, t in zip(bars, fracs, totals):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.008,
                f"{f:.1%}\n(n={t})", ha="center", fontsize=8)
    ax.set_ylabel("Fraction of gold files outside retrievable corpus")
    ax.set_title("Candidate reachability varies widely by language")
    ax.set_ylim(0, max(fracs) * 1.35)
    fig.tight_layout()
    out = FIG_DIR / "fig4_reachability.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def fig5_leak_cost(rows: list[dict]) -> Path:
    """Per-language BM25 Hit@1 under the released and the superseded query rule.

    The point of the figure is the pair of bars that do *not* move: the Python
    subset's superseded query repeats the same issue text and adds no
    post-solution information, so it is the information-matched control.  If it
    moved as much as the others, the effect would be query length, not leakage.
    """
    treat_dir = ROOT / "results" / "contrast_leaky_v1"
    treat: dict[tuple[str, str], dict] = {}
    for lang in LANGS:
        path = treat_dir / f"main_{lang}.jsonl"
        if not path.exists():
            raise SystemExit(f"REFUSE: contrast arm missing for {lang}; run run_leak_contrast.py")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("query_protocol") != "legacy_mixed_v1":
                raise SystemExit(f"REFUSE: {path} carries {row.get('query_protocol')}")
            if row["method"] == "bm25":
                treat[(row["lang"], row["instance_id"])] = row
    base = {(r["lang"], r["instance_id"]): r for r in rows if r["method"] == "bm25"}
    if set(base) != set(treat):
        raise SystemExit(f"REFUSE: arms do not pair ({len(base)} control, {len(treat)} treatment)")

    def mean(keys, table) -> float:
        return sum(table[k]["hit@1"] for k in keys) / len(keys)

    per_lang = []
    for lang in LANGS:
        keys = [k for k in base if k[0] == lang]
        per_lang.append((lang, mean(keys, base), mean(keys, treat), len(keys)))
    per_lang.sort(key=lambda item: item[2] - item[1])
    overall = (mean(list(base), base), mean(list(treat), treat))

    labels = [item[0] + (" (control)" if item[0] == "python" else "") for item in per_lang]
    control = [item[1] for item in per_lang]
    treated = [item[2] for item in per_lang]
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    y = np.arange(len(labels))
    ax.barh(y - 0.2, control, 0.4, label="issue-only query (released)", color="#2471a3")
    ax.barh(y + 0.2, treated, 0.4, label="superseded query (PR text admitted)", color="#c0392b")
    for i, (lang, c, t, n) in enumerate(per_lang):
        ax.text(max(c, t) + 0.012, i, f"Δ{t - c:+.4f}  (n={n})", va="center", fontsize=8)
    ax.set_yticks(y, labels)
    ax.set_xlabel("BM25 Hit@1")
    ax.set_xlim(0, max(max(control), max(treated)) * 1.30)
    ax.set_title(
        "What the leaked query is worth: same pipeline, only the query rule changed\n"
        f"all {len(base):,} instances \u0394{overall[1] - overall[0]:+.4f}; "
        f"Python is the information-matched control"
    )
    # Below the axes, because every bar starts at zero and the value labels occupy
    # the right margin: an in-axes legend covers the last row's label.
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, frameon=False)
    fig.tight_layout()
    out = FIG_DIR / "fig5_leak_cost.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def fig6_rank_shift() -> Path:
    """Rank of each configuration under both query rules (RQ7).

    Reads the released RQ7 table rather than recomputing anything, and refuses if
    the leader is not unchanged: the whole point of the figure is that the lines
    may cross below the leader and not at the top.
    """
    source = ROOT / "results" / "tables_v2" / "t14_leak_ranking.json"
    if not source.exists():
        raise SystemExit(f"missing {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    for metric in ("hit@1", "mrr"):
        if not data["agreement"][metric]["leader_unchanged"]:
            raise SystemExit(f"the figure assumes the leader is unchanged by {metric}")
    left = data["ordering"]["mrr"]["issue_only"]
    right = data["ordering"]["mrr"]["superseded"]
    if sorted(left) != sorted(METHODS) or sorted(right) != sorted(METHODS):
        raise SystemExit("the released ordering does not cover the released methods")
    rank_left = {m: i for i, m in enumerate(left)}
    rank_right = {m: i for i, m in enumerate(right)}
    gains = {m: data["per_method"][m]["mrr"]["delta"] for m in METHODS}
    highlighted = max(METHODS, key=lambda m: gains[m])

    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    cmap = plt.get_cmap("tab10")
    colours = {m: cmap(i % 10) for i, m in enumerate(left)}
    for method in left:
        strong = method == highlighted
        ax.plot([0, 1], [rank_left[method], rank_right[method]], marker="o",
                markersize=7 if strong else 5, lw=3.0 if strong else 1.5,
                color=colours[method], alpha=1.0 if strong else 0.8,
                zorder=3 if strong else 2)
        ax.text(-0.05, rank_left[method], METHOD_SHORT[method], ha="right",
                va="center", fontsize=9,
                fontweight="bold" if strong else "normal")
        ax.text(1.05, rank_right[method], METHOD_SHORT[method], ha="left",
                va="center", fontsize=9,
                fontweight="bold" if strong else "normal")

    ax.set_xlim(-0.72, 1.72)
    ax.set_ylim(len(METHODS) - 0.4, -0.6)
    ax.set_yticks(range(len(METHODS)),
                  [str(i + 1) for i in range(len(METHODS))])
    ax.set_xticks([0, 1], ["issue-only query", "superseded query"])
    ax.set_ylabel("Rank by MRR")
    ax.grid(axis="y", ls=":", alpha=0.45)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    rho = data["agreement"]["mrr"]["spearman"]
    ax.set_title(
        "Does the leaked query change which configuration wins?\n"
        f"leader unchanged; Spearman \u03c1 = {rho:.4f}; "
        f"only {METHOD_SHORT[highlighted]} improves its position"
    )
    fig.tight_layout()
    out = FIG_DIR / "fig6_rank_shift.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    gate()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    made = [fig1_provenance(), fig2_heatmap(rows), fig3_cue_strata(rows),
            fig4_reachability(rows), fig5_leak_cost(rows), fig6_rank_shift()]
    manifest = {"figures": [str(p.relative_to(ROOT)) for p in made],
                "rows": len(rows),
                "gate": "result_integrity VERIFIED"}
    (FIG_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for p in made:
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
