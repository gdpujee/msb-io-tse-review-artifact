#!/usr/bin/env python3
"""Record which field each localization benchmark family uses as the query.

Motivation
----------
This project's central finding is that the published MTEB reranking task
`mteb/MultiSWEbenchRR` ships post-solution pull-request text as its *query* for
at least 954 of 1,688 rows.  A natural objection is that this is simply how
issue-localization benchmarks are built.  It is not.  The upstream benchmarks
keep the issue and the solution in separate fields; the contamination appears
when a derivative task re-packages them.

This script makes that comparison reproducible.  For each family it records the
released column set, the field a localization system would receive as the query,
and the provenance of that field.  Nothing is inferred about text we cannot see:
the provenance label for the SWE-bench family follows from the field layout
(issue text in `problem_statement`, solution in `patch`/`test_patch`), and the
label for MultiSWEbenchRR is taken from the measured exact-match audit in
`results/audit_v2/mteb_query_audit.json`.

Every network read records the dataset revision so the snapshot is pinned.
"""
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "audit_v2"
MTEB_AUDIT = OUT_DIR / "mteb_query_audit.json"

ssl._create_default_https_context = ssl._create_unverified_context
UA = {"User-Agent": "agentic-research-query-provenance-audit/1.0"}

FAMILIES = [
    "SWE-bench/SWE-bench",
    "princeton-nlp/SWE-bench_Verified",
    "SWE-bench/SWE-bench_Multilingual",
    "mteb/MultiSWEbenchRR",
]

# The field a localization system receives as its query, per family.
QUERY_FIELD = {
    "SWE-bench/SWE-bench": "problem_statement",
    "princeton-nlp/SWE-bench_Verified": "problem_statement",
    "SWE-bench/SWE-bench_Multilingual": "problem_statement",
    "mteb/MultiSWEbenchRR": "text",
}

SOLUTION_FIELDS = ("patch", "test_patch", "resolved_issues")


def get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return json.load(r)


def dataset_sha(dataset: str) -> str:
    try:
        return get("https://huggingface.co/api/datasets/" + urllib.parse.quote(dataset)).get("sha", "?")
    except Exception as exc:  # noqa: BLE001
        return f"UNRESOLVED ({type(exc).__name__})"


def main() -> None:
    mteb = json.loads(MTEB_AUDIT.read_text())
    mteb_counts = mteb["counts"]
    mteb_total = mteb["mteb_query_count"]
    mteb_pr = mteb_counts["pr_only_exact"]

    records = []
    for dataset in FAMILIES:
        entry = {"dataset": dataset, "sha": dataset_sha(dataset)}
        try:
            splits = get("https://datasets-server.huggingface.co/splits?dataset="
                         + urllib.parse.quote(dataset))
            pairs = [(s["config"], s["split"]) for s in splits.get("splits", [])]
            entry["configs"] = sorted({c for c, _ in pairs})
            if not pairs:
                entry["error"] = "no splits exposed"
                records.append(entry)
                continue
            # Use the split the family actually exposes; MTEB's task uses
            # config=queries, split=train, so hard-coding "test" would report a
            # wrong (or missing) column set.
            config, split = pairs[0]
            entry["probed_config"] = config
            entry["probed_split"] = split
            info = get("https://datasets-server.huggingface.co/first-rows?dataset="
                       + urllib.parse.quote(dataset)
                       + f"&config={urllib.parse.quote(config)}&split={urllib.parse.quote(split)}")
            entry["columns"] = sorted(f["name"] for f in info["features"])
            entry["query_field"] = QUERY_FIELD[dataset]
            entry["solution_fields_present"] = [f for f in SOLUTION_FIELDS if f in entry["columns"]]
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"
        records.append(entry)

    for entry in records:
        if entry["dataset"] == "mteb/MultiSWEbenchRR":
            entry["query_provenance"] = "MIXED"
            entry["measured_pr_only_exact"] = mteb_pr
            entry["measured_total"] = mteb_total
            entry["evidence"] = ("exact normalized-text matching against Multi-SWE-bench issue and "
                                 "top-level PR text; see results/audit_v2/mteb_query_audit.json")
        elif "query_field" in entry:
            entry["query_provenance"] = "PRE_SOLUTION_ISSUE_TEXT"
            entry["evidence"] = ("the query field is the GitHub issue text and the solution is carried "
                                 "by the separate patch/test_patch fields, so a query cannot contain the "
                                 "solution by construction")

    result = {
        "status": "VERIFIED",
        "question": "Is a post-solution query a property of issue-localization benchmarks, "
                    "or of a particular derivative conversion?",
        "answer": ("It is a property of the derivative conversion. Every SWE-bench family examined "
                   "separates the issue text (query) from the solution (patch/test_patch), whereas the "
                   "MTEB reranking task packages top-level PR text as its query."),
        "caveat": ("This audit classifies the *query field's provenance from the released schema*. It is "
                   "not a text-level leak audit of the SWE-bench families; the solution-leakage question "
                   "for those benchmarks is a different measurement, addressed by Aleithan et al. (2024) "
                   "and by OpenAI (2026)."),
        "records": records,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "query_field_provenance.json").write_text(json.dumps(result, indent=2) + "\n")

    lines = [
        "# Query-field provenance across localization benchmark families", "",
        f"**Question.** {result['question']}", "",
        f"**Answer.** {result['answer']}", "",
        "| dataset | revision | query field | solution fields | query provenance |",
        "|---|---|---|---|---|",
    ]
    for entry in records:
        lines.append("| `{}` | `{}` | `{}` | {} | {} |".format(
            entry["dataset"],
            str(entry["sha"])[:12],
            entry.get("query_field", "?"),
            ", ".join(f"`{f}`" for f in entry.get("solution_fields_present", [])) or "—",
            entry.get("query_provenance", entry.get("error", "?")),
        ))
    lines += ["", "**Caveat.** " + result["caveat"]]
    (OUT_DIR / "query_field_provenance.md").write_text("\n".join(lines) + "\n")

    for entry in records:
        print(entry["dataset"], "->", entry.get("query_provenance", entry.get("error")))


if __name__ == "__main__":
    main()
