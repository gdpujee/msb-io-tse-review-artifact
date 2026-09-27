#!/usr/bin/env python3
"""Classify MultiSWEbenchRR queries against PR-only and issue-only source text."""
from __future__ import annotations

import json
import argparse
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from config import RAW_DIR  # noqa: E402
from dataset import build_query  # noqa: E402

DATASET = "mteb/MultiSWEbenchRR"
OUT_DIR = ROOT / "results" / "audit_v2"


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in str(text or "").strip().splitlines()).strip()


def pr_query(row: dict) -> str:
    parts = []
    for field in ("title", "body"):
        value = str(row.get(field) or "").strip()
        if value and value.lower() != "placeholder":
            parts.append(value)
    return normalize("\n".join(parts))


def fetch_queries() -> list[dict]:
    rows = []
    offset = 0
    while True:
        params = urllib.parse.urlencode({
            "dataset": DATASET, "config": "queries", "split": "train",
            "offset": offset, "length": 100,
        })
        with urllib.request.urlopen("https://datasets-server.huggingface.co/rows?" + params,
                                    timeout=120) as response:
            page = json.load(response)
        rows.extend(item["row"] for item in page["rows"])
        offset += len(page["rows"])
        if offset >= page["num_rows_total"] or not page["rows"]:
            break
    return rows


def summarize_records(records: list[dict]) -> tuple[Counter, dict[str, Counter]]:
    counts = Counter(record["classification"] for record in records)
    per_language: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        matched_languages = {
            instance_id.split("/", 1)[0]
            for instance_id in record["issue_matches"] + record["pr_matches"]
        }
        for lang in matched_languages:
            per_language[lang][record["classification"]] += 1
    return counts, per_language


def write_report(records: list[dict], local_rows: int) -> None:
    counts, per_language = summarize_records(records)
    matched = len(records) - counts["unmatched"]
    result = {
        "status": "VERIFIED",
        "mteb_dataset": DATASET,
        "mteb_query_count": len(records),
        "local_source_rows": local_rows,
        "counts": dict(counts),
        "per_language_exact_matches": {lang: dict(value) for lang, value in sorted(per_language.items())},
        "matched_to_local_fraction": round(matched / len(records), 6),
        "method": "exact normalized-text matching; no fuzzy classification",
        "interpretation": (
            "PR-only exact matches contain top-level solution PR title/body and are not valid "
            "pre-solution issue-only inputs. Unmatched rows are not classified."
        ),
        "records": records,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "mteb_query_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# MTEB MultiSWEbenchRR query provenance audit", "",
        f"- Status: **{result['status']}**",
        f"- MTEB queries: **{len(records)}**",
        f"- Local source rows available for exact matching: **{local_rows}**",
        f"- PR-only exact matches: **{counts['pr_only_exact']}**",
        f"- Issue-only exact matches: **{counts['issue_only_exact']}**",
        f"- Exact matches to both: **{counts['both_exact']}**",
        f"- Unmatched (not classified): **{counts['unmatched']}**",
        "", "## Exact matches by source language", "",
        "Each public query is counted at most once per language, even when duplicate local rows match it.",
        "", "| language | PR-only | issue-only | both |", "|---|---:|---:|---:|",
    ]
    for lang, value in sorted(per_language.items()):
        lines.append(f"| {lang} | {value['pr_only_exact']} | {value['issue_only_exact']} | {value['both_exact']} |")
    lines.extend([
        "",
        "Classification uses exact normalized text only. Therefore, it establishes provenance for matches",
        "without speculating about unmatched queries. A PR-only match is post-solution text and is not a",
        "valid issue-only localization input.",
    ])
    (OUT_DIR / "mteb_query_audit.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({key: result[key] for key in (
        "status", "mteb_query_count", "local_source_rows", "counts",
        "matched_to_local_fraction")}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reuse-records",
        action="store_true",
        help="Rebuild aggregate tables from the saved per-query exact-match records.",
    )
    args = parser.parse_args()
    saved_path = OUT_DIR / "mteb_query_audit.json"
    if args.reuse_records:
        saved = json.loads(saved_path.read_text())
        write_report(saved["records"], int(saved["local_source_rows"]))
        return

    issue_index: dict[str, set[str]] = defaultdict(set)
    pr_index: dict[str, set[str]] = defaultdict(set)
    local_rows = 0
    for path in sorted(RAW_DIR.glob("*.jsonl")):
        lang = path.name.split("__", 1)[0]
        with path.open() as stream:
            for line in stream:
                row = json.loads(line)
                iid = row.get("instance_id") or f"{row['org']}__{row['repo']}-{row.get('number')}"
                instance_id = f"{lang}/{iid}"
                issue, _ = build_query(row)
                issue_index[normalize(issue)].add(instance_id)
                pr_index[pr_query(row)].add(instance_id)
                local_rows += 1

    queries = fetch_queries()
    records = []
    for row in queries:
        text = normalize(row["text"])
        issue_hits = sorted(issue_index.get(text, ()))
        pr_hits = sorted(pr_index.get(text, ()))
        if pr_hits and issue_hits:
            label = "both_exact"
        elif pr_hits:
            label = "pr_only_exact"
        elif issue_hits:
            label = "issue_only_exact"
        else:
            label = "unmatched"
        records.append({"query_id": row["id"], "classification": label,
                        "issue_matches": issue_hits, "pr_matches": pr_hits,
                        "chars": len(text)})
    write_report(records, local_rows)


if __name__ == "__main__":
    main()
