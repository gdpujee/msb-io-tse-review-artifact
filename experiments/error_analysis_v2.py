#!/usr/bin/env python3
"""Generate stratified and qualitative Protocol V2 error analyses."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from dataset import load_all  # noqa: E402

RAW_DIR = ROOT / "results" / "raw_v2"
TABLE_DIR = ROOT / "results" / "tables_v2"
AUDIT_DIR = ROOT / "results" / "audit_v2"
METHODS = ("bm25", "anchor_path_only", "bm25_graph")


def load_rows() -> dict[str, dict[str, dict]]:
    joined: dict[str, dict[str, dict]] = defaultdict(dict)
    for path in sorted(RAW_DIR.glob("main_*.jsonl")):
        with path.open() as stream:
            for line in stream:
                row = json.loads(line)
                if row["method"] in METHODS:
                    joined[row["instance_id"]][row["method"]] = row
    return {iid: rows for iid, rows in joined.items() if set(rows) == set(METHODS)}


def qcuts(values: list[int], prefix: str) -> tuple[list[float], list[str]]:
    bounds = [-np.inf, *np.quantile(values, [0.25, 0.5, 0.75]).tolist(), np.inf]
    labels = []
    for i in range(4):
        lo = "min" if i == 0 else str(int(bounds[i]) + 1)
        hi = "max" if i == 3 else str(int(bounds[i + 1]))
        labels.append(f"{prefix} Q{i + 1} ({lo}–{hi})")
    return bounds, labels


def assign(value: int, bounds: list[float], labels: list[str]) -> str:
    for index in range(4):
        if bounds[index] < value <= bounds[index + 1]:
            return labels[index]
    raise AssertionError(value)


def summarize(groups: dict[str, list[str]], joined: dict[str, dict[str, dict]]) -> list[dict]:
    output = []
    for group, ids in groups.items():
        for method in METHODS:
            rows = [joined[iid][method] for iid in ids]
            output.append({
                "stratum": group, "method": method, "n": len(rows),
                "hit@1": sum(row["hit@1"] for row in rows) / len(rows),
                "hit@10": sum(row["hit@10"] for row in rows) / len(rows),
                "mrr": sum(row["mrr"] for row in rows) / len(rows),
            })
    return output


def main() -> None:
    joined = load_rows()
    bm25 = {iid: rows["bm25"] for iid, rows in joined.items()}
    token_bounds, token_labels = qcuts([row["n_tokens_query"] for row in bm25.values()], "query tokens")
    file_bounds, file_labels = qcuts([row["n_candidates"] for row in bm25.values()], "candidate files")

    groups: dict[str, list[str]] = defaultdict(list)
    for iid, row in bm25.items():
        groups[assign(row["n_tokens_query"], token_bounds, token_labels)].append(iid)
        groups[assign(row["n_candidates"], file_bounds, file_labels)].append(iid)
        gold_group = "gold files = 1" if row["n_gold_all"] == 1 else (
            "gold files = 2" if row["n_gold_all"] == 2 else "gold files >= 3")
        groups[gold_group].append(iid)
        groups["explicit gold-path cue present" if row["query_mentions_gold_path"]
               else "explicit gold-path cue absent"].append(iid)
        groups[f"query source = {row['query_source']}"].append(iid)

    summaries = summarize(groups, joined)
    by_key = {(row["stratum"], row["method"]): row for row in summaries}
    order = token_labels + file_labels + ["gold files = 1", "gold files = 2", "gold files >= 3",
                                           "explicit gold-path cue absent",
                                           "explicit gold-path cue present",
                                           "query source = resolved_issues",
                                           "query source = problem_statement"]
    lines = ["# Error analysis by task characteristics", "",
             "All strata are defined from method-invariant instance attributes. Deltas are paired within stratum.", "",
             "| stratum | n | BM25 Hit@1 | path-anchor ΔHit@1 | graph ΔHit@1 | BM25 Hit@10 | BM25 MRR |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for group in order:
        base = by_key[(group, "bm25")]
        path = by_key[(group, "anchor_path_only")]
        graph = by_key[(group, "bm25_graph")]
        lines.append(f"| {group} | {base['n']} | {base['hit@1']:.4f} | "
                     f"{path['hit@1'] - base['hit@1']:+.4f} | "
                     f"{graph['hit@1'] - base['hit@1']:+.4f} | "
                     f"{base['hit@10']:.4f} | {base['mrr']:.4f} |")
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    (TABLE_DIR / "t10_error_strata.md").write_text("\n".join(lines) + "\n")
    (TABLE_DIR / "t10_error_strata.json").write_text(json.dumps({
        "n_instances": len(joined), "token_bounds": token_bounds[1:-1],
        "candidate_bounds": file_bounds[1:-1], "rows": summaries,
    }, indent=2) + "\n")

    sources = {row.instance_id: row for row in load_all()}
    predicates = {
        "path cue helps": lambda b, p, g: b["hit@1"] == 0 and p["hit@1"] == 1 and b["query_mentions_gold_path"],
        "non-gold path cue misleads": lambda b, p, g: b["hit@1"] == 1 and p["hit@1"] == 0 and not b["query_mentions_gold_path"],
        "graph expansion hurts": lambda b, p, g: b["hit@1"] == 1 and g["hit@1"] == 0,
        "graph expansion helps": lambda b, p, g: b["hit@1"] == 0 and g["hit@1"] == 1,
    }
    cases = []
    for category, predicate in predicates.items():
        selected = []
        for iid in sorted(joined):
            rows = joined[iid]
            if predicate(rows["bm25"], rows["anchor_path_only"], rows["bm25_graph"]):
                source = sources[iid]
                selected.append({
                    "category": category, "instance_id": iid, "lang": rows["bm25"]["lang"],
                    "repo": rows["bm25"]["repo"], "gold_files": source.gold_files_nontest,
                    "gold_path_cues": rows["bm25"]["gold_path_cues"],
                    "query_excerpt": " ".join(source.query.split())[:400],
                    "bm25_top3": rows["bm25"]["top10"][:3],
                    "path_top3": rows["anchor_path_only"]["top10"][:3],
                    "graph_top3": rows["bm25_graph"]["top10"][:3],
                })
                if len(selected) == 3:
                    break
        cases.extend(selected)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "qualitative_cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    case_lines = ["# Qualitative localization cases", "",
                  "Cases are deterministically selected (lexicographically first three matching instances per category).", ""]
    for case in cases:
        case_lines.extend([
            f"## {case['category']} — `{case['instance_id']}`", "",
            f"- Language/repository: {case['lang']} / `{case['repo']}`",
            f"- Gold: `{case['gold_files']}`",
            f"- Explicit gold-path cues: `{case['gold_path_cues']}`",
            f"- Query excerpt: {case['query_excerpt']}",
            f"- BM25 top-3: `{case['bm25_top3']}`",
            f"- Path-anchor top-3: `{case['path_top3']}`",
            f"- Graph top-3: `{case['graph_top3']}`", "",
        ])
    (AUDIT_DIR / "qualitative_cases.md").write_text("\n".join(case_lines) + "\n")
    print(json.dumps({"instances": len(joined), "strata": len(groups), "cases": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
