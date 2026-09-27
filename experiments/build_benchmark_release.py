#!/usr/bin/env python3
"""Build the MSB-IO release artifact: a corrected, issue-only localization benchmark.

What MSB-IO is
--------------
Multi-SWE-bench ships each instance with several text fields.  Only some of them
predate the solution: ``problem_statement`` and ``resolved_issues[].title/body``
are issue text, whereas the top-level ``title``/``body``/``hints``/``hints_text``
are post-solution pull-request text.  MTEB's ``MultiSWEbenchRR`` reranking task
packages the top-level text as its query, so 56.5% of its published queries
already contain the answer.  MSB-IO is the same 1,791 instances re-queried under
a rule that admits only pre-solution text, released with the hashes and the
field-availability accounting needed to check that rule.

Design rules
------------
* Every field written here is either (a) read straight out of the authoritative
  instance materialization produced by ``dataset.load_all()`` -- the same code
  path the independent verifier uses -- or (b) taken from a field the verifier
  has proven constant across all eight configurations.  Nothing is recomputed by
  a second code path, so the release cannot silently disagree with the results.
* The builder refuses to run unless ``result_integrity.json`` reports VERIFIED.
* The per-language accounting is cross-checked against ``protocol_audit.json``;
  a mismatch aborts rather than publishing two different answers.
* The query hash is asserted to be unique per instance across methods; if two
  methods were ever scored on different queries the release would be invalid.
* The on-disk dump ``data/instances.jsonl`` is cross-checked against
  ``load_all()``.  That dump once outlived the module that produced it and
  disagreed with the protocol on all 1,791 instances (FAILURES F019); it is not
  a source of truth here, and any future drift now aborts the build.

Outputs (benchmark/msb_io/)
---------------------------
``msb_io.jsonl``            one row per instance: query, hash, source, labels
``field_availability.csv``  per-language provenance and label accounting
``MANIFEST.sha256``         SHA-256 of every released file
``README.md``               what this is, what it is not, how to obtain source
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from dataset import load_all  # noqa: E402

RAW_DIR = ROOT / "results" / "raw_v2"
AUDIT_DIR = ROOT / "results" / "audit_v2"
INSTANCE_DUMP = ROOT / "data" / "instances.jsonl"
OUT_DIR = ROOT / "benchmark" / "msb_io"

LANGS = ("c", "cpp", "go", "java", "js", "kotlin", "python", "rust", "ts")

# Fields the independent verifier (verify_results_v2.py:114) proves constant
# across every configuration.  A field that varied by method would make the
# release depend on which method you looked at, so only these may be published.
INVARIANT_FIELDS = (
    "n_gold_all",
    "n_gold_evaluable",
    "n_gold_excluded",
    "no_evaluable_gold",
    "query_mentions_gold_path",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_instances() -> dict[str, dict]:
    """Authoritative per-instance materialization, via the pipeline's own loader.

    This is deliberately the same call the independent verifier makes, so the
    released query strings are the query strings that were actually scored.
    """
    return {item.instance_id: item for item in load_all()}


def check_dump(instances: dict) -> list[str]:
    """The on-disk dump must agree with the loader; it once did not (F019)."""
    problems: list[str] = []
    if not INSTANCE_DUMP.exists():
        return [f"{INSTANCE_DUMP.name} is missing; regenerate it with dataset.py --dump"]
    seen = 0
    with INSTANCE_DUMP.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            doc = json.loads(line)
            item = instances.get(doc["instance_id"])
            if item is None:
                problems.append(f"dump has unknown instance {doc['instance_id']}")
                continue
            seen += 1
            if doc.get("stats", {}).get("query_source") != item.stats["query_source"]:
                problems.append(
                    f"{doc['instance_id']}: dump query_source "
                    f"{doc.get('stats', {}).get('query_source')!r} != loader "
                    f"{item.stats['query_source']!r}"
                )
            elif sha256_bytes(doc["query"].encode()) != sha256_bytes(item.query.encode()):
                problems.append(f"{doc['instance_id']}: dump query text != loader query text")
    if seen != len(instances):
        problems.append(f"dump has {seen} instances, loader has {len(instances)}")
    return problems


def load_invariants() -> tuple[dict[str, dict], list[str]]:
    """Collect the per-instance fields that are constant across methods.

    Returns the merged record per instance plus any consistency violations.
    """
    per_instance: dict[str, dict] = {}
    violations: list[str] = []
    for lang in LANGS:
        path = RAW_DIR / f"main_{lang}.jsonl"
        with path.open() as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = row["instance_id"]
                record = {
                    "query_sha256": row["query_sha256"],
                    "query_source": row["query_source"],
                    "lang": row["lang"],
                    **{field: row[field] for field in INVARIANT_FIELDS},
                }
                previous = per_instance.get(key)
                if previous is None:
                    per_instance[key] = record
                elif previous != record:
                    differing = sorted(
                        k for k in record if previous.get(k) != record[k]
                    )
                    violations.append(
                        f"{key}: fields not constant across configurations: {differing}"
                    )
    return per_instance, violations


def build_rows() -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    instances = load_instances()
    problems.extend(check_dump(instances))
    invariants, violations = load_invariants()
    problems.extend(violations)

    missing = sorted(set(instances) - set(invariants))
    extra = sorted(set(invariants) - set(instances))
    if missing:
        problems.append(f"{len(missing)} instances absent from results: {missing[:5]}")
    if extra:
        problems.append(f"{len(extra)} result instances absent from index: {extra[:5]}")

    rows: list[dict] = []
    for instance_id in sorted(instances):
        inst = instances[instance_id]
        if instance_id not in invariants:
            continue
        inv = invariants[instance_id]
        query = inst.query
        computed_hash = sha256_bytes(query.encode("utf-8"))
        if computed_hash != inv["query_sha256"]:
            problems.append(
                f"{instance_id}: query hash mismatch (loader {computed_hash[:12]} "
                f"vs result {inv['query_sha256'][:12]})"
            )
        if inv["query_source"] != inst.stats["query_source"]:
            problems.append(f"{instance_id}: query source disagrees with loader")
        if inv["lang"] != inst.lang:
            problems.append(f"{instance_id}: language disagrees with loader")
        if not query.strip():
            problems.append(f"{instance_id}: empty query")
        if inst.stats["query_empty"]:
            problems.append(f"{instance_id}: loader reports an empty query")
        rows.append({
            "instance_id": instance_id,
            "lang": inst.lang,
            "repo": f"{inst.org}/{inst.repo}",
            "base_sha": inst.base_sha,
            "query_source": inv["query_source"],
            "query_sha256": inv["query_sha256"],
            "query_chars": len(query),
            "n_linked_issues": inst.stats["n_linked_issues"],
            "n_gold_all": inv["n_gold_all"],
            "n_gold_evaluable": inv["n_gold_evaluable"],
            "n_gold_excluded": inv["n_gold_excluded"],
            "no_evaluable_gold": inv["no_evaluable_gold"],
            "query_mentions_gold_path": inv["query_mentions_gold_path"],
            "gold_files": inst.gold_files,
            "gold_files_nontest": inst.gold_files_nontest,
            "test_files": inst.test_files,
            "query": query,
        })
    return rows, problems


def field_availability(rows: list[dict]) -> list[dict]:
    table: list[dict] = []
    for lang in LANGS:
        subset = [r for r in rows if r["lang"] == lang]
        sources = Counter(r["query_source"] for r in subset)
        cues = sum(1 for r in subset if r["query_mentions_gold_path"])
        table.append({
            "lang": lang,
            "instances": len(subset),
            "repositories": len({r["repo"] for r in subset}),
            "query_from_problem_statement": sources.get("problem_statement", 0),
            "query_from_resolved_issues": sources.get("resolved_issues", 0),
            "query_source_missing": sum(v for k, v in sources.items() if k is None),
            "instances_with_gold_path_cue": cues,
            "gold_path_cue_fraction": round(cues / len(subset), 6) if subset else 0.0,
            "gold_files_all": sum(r["n_gold_all"] for r in subset),
            "gold_files_evaluable": sum(r["n_gold_evaluable"] for r in subset),
            "gold_files_excluded": sum(r["n_gold_excluded"] for r in subset),
            "instances_without_evaluable_gold": sum(
                1 for r in subset if r["no_evaluable_gold"]
            ),
            "mean_query_chars": round(
                sum(r["query_chars"] for r in subset) / len(subset), 1
            ) if subset else 0.0,
        })
    return table


def cross_check(table: list[dict]) -> list[str]:
    """The release accounting must equal the protocol audit's accounting."""
    problems: list[str] = []
    audit = json.loads((AUDIT_DIR / "protocol_audit.json").read_text())
    per_language = audit["per_language"]
    for row in table:
        reference = per_language.get(row["lang"])
        if reference is None:
            problems.append(f"{row['lang']}: absent from protocol_audit.json")
            continue
        if row["instances"] != reference["instances"]:
            problems.append(
                f"{row['lang']}: instances {row['instances']} != audit "
                f"{reference['instances']}"
            )
        if row["repositories"] != reference["repositories"]:
            problems.append(
                f"{row['lang']}: repositories {row['repositories']} != audit "
                f"{reference['repositories']}"
            )
        expected_sources = reference["query_sources"]
        if row["query_from_problem_statement"] != expected_sources.get("problem_statement", 0):
            problems.append(f"{row['lang']}: problem_statement count disagrees with audit")
        if row["query_from_resolved_issues"] != expected_sources.get("resolved_issues", 0):
            problems.append(f"{row['lang']}: resolved_issues count disagrees with audit")
        if row["instances_with_gold_path_cue"] != reference["gold_path_cue_instances"]:
            problems.append(
                f"{row['lang']}: gold-path-cue count disagrees with audit"
            )
    if sum(r["instances"] for r in table) != audit["n_instances"]:
        problems.append("total instances disagree with audit")
    return problems


def write_csv(path: Path, table: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0].keys()))
        writer.writeheader()
        writer.writerows(table)


def write_readme(path: Path, table: list[dict], rows: list[dict]) -> None:
    total = sum(r["instances"] for r in table)
    statement = sum(r["query_from_problem_statement"] for r in table)
    issues = sum(r["query_from_resolved_issues"] for r in table)
    distinct_repos = len({r["repo"] for r in rows})
    lines = [
        "# MSB-IO: an issue-only localization benchmark",
        "",
        f"{total} instances over {distinct_repos} repositories and {len(table)} "
        "languages, re-queried so that no query contains post-solution text.",
        "",
        "## Why this exists",
        "",
        "Multi-SWE-bench stores several text fields per instance. Some predate the",
        "solution (`problem_statement`, `resolved_issues[].title/body`); others are",
        "written after it (the top-level `title`, `body`, `hints`, `hints_text`).",
        "The MTEB reranking task `MultiSWEbenchRR` uses the top-level text as its",
        "query, so 56.5% of its published queries exactly reproduce pull-request",
        "text that postdates the fix. MSB-IO applies the opposite rule: a query is",
        "built only from pre-solution text, and every query is published with its",
        "SHA-256 so the rule is checkable without trusting the builder.",
        "",
        "## What is in the package",
        "",
        "| file | contents |",
        "| --- | --- |",
        "| `msb_io.jsonl` | one row per instance: query text, query hash, query "
        "source, gold labels, candidate-accounting fields |",
        "| `field_availability.csv` | per-language provenance and label accounting |",
        "| `MANIFEST.sha256` | SHA-256 of every file in this directory |",
        "",
        "## Query provenance",
        "",
        "The rule is uniform but the available field is not: only Python instances",
        f"carry a usable `problem_statement` ({statement} of {total} instances); the",
        f"other {issues} instances fall back to linked-issue title and body. Any",
        "comparison across languages therefore compares differently sourced text,",
        "and `field_availability.csv` records which is which.",
        "",
        "## What this is not",
        "",
        "* It is not a redistribution of repository source. The package holds",
        "  queries, labels, and hashes only; obtain source from each upstream",
        "  repository at the recorded `base_sha`.",
        "* It is not a claim that the upstream benchmark is unusable. It is the same",
        "  instance set under a different, stated query rule.",
        "* It is not a leaderboard. Numbers computed on it are only comparable to",
        "  others computed on it under the same protocol identifiers.",
        "",
        "## Protocol identifiers",
        "",
        "| identifier | value |",
        "| --- | --- |",
        "| query | `issue_only_v2` |",
        "| candidates | `component_aware_test_filter_v6` |",
        "| metrics | `full_precision_metrics_v1` |",
        "",
        "Dataset revision: `56ff018c04a38e27ada1e9d0a6d5839a51f88f0d`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    integrity_path = AUDIT_DIR / "result_integrity.json"
    if not integrity_path.exists():
        raise SystemExit("REFUSE: result_integrity.json missing; run verify_results_v2.py first")
    integrity = json.loads(integrity_path.read_text())
    if integrity.get("status") != "VERIFIED":
        raise SystemExit(f"REFUSE: integrity status is {integrity.get('status')}, not VERIFIED")

    rows, problems = build_rows()
    table = field_availability(rows)
    problems.extend(cross_check(table))

    if problems:
        print(f"FAILED ({len(problems)})")
        for item in problems[:40]:
            print("  -", item)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = OUT_DIR / "msb_io.jsonl"
    with jsonl_path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    csv_path = OUT_DIR / "field_availability.csv"
    write_csv(csv_path, table)
    readme_path = OUT_DIR / "README.md"
    write_readme(readme_path, table, rows)

    released = sorted(p for p in OUT_DIR.iterdir() if p.name != "MANIFEST.sha256")
    manifest_lines = [f"{sha256_file(p)}  {p.name}" for p in released]
    (OUT_DIR / "MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    print(f"instances: {len(rows)}")
    print(f"languages: {len(table)}")
    print(f"distinct repositories: {len({r['repo'] for r in rows})}  "
          f"language-repository checkouts: {sum(r['repositories'] for r in table)}")
    print(f"files: {', '.join(p.name for p in released)}")
    print("VERIFIED: MSB-IO release built and cross-checked against protocol_audit.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
