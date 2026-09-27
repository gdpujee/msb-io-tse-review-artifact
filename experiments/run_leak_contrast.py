#!/usr/bin/env python3
"""Controlled contrast: what is the leaked query actually worth?

Motivation
----------
Section 5.1 establishes that a large share of public reranking queries reproduce
post-solution pull-request text, and that our own superseded materialization did
so for 72.1% of instances.  Both are statements about *queries*.  Neither answers
the question a reader actually has: **how much does that change a reported
score?**  Answering it needs a controlled experiment, not a second audit.

Design
------
One factor is manipulated: the query rule.  Everything else is held fixed by
construction, because this script does not reimplement the pipeline -- it
*imports* it.  ``run_experiment.run_all`` is called with its own ranking,
candidate-selection, and metric code untouched; the only two names swapped are
the instance source and the protocol label it stamps on rows.

    treatment   query = legacy_query(row)      the audited superseded rule
    control     query = build_query(row)[0]    the released issue-only rule

Both rules are read from raw rows in ``data/raw/``; the repository index, the
candidate protocol (``component_aware_test_filter_v6``), the eight method
configurations, and the metric implementation (``full_precision_metrics_v1``) are
identical between arms.  A difference in outcome therefore has exactly one
admissible explanation.

Why the treatment is not a guess
--------------------------------
``legacy_query`` is not a re-derivation written for this experiment: it is the
function that ``audit_query_leakage.py`` proved reproduces all 1,791 superseded
queries byte-for-byte.  This script re-verifies that claim per instance before
running (``--verify-only`` stops after the check) and every emitted row carries
the treatment query's SHA-256, so the analysis can confirm post hoc that each row
was scored on the audited query and not on an approximation of it.

Pre-registered predictions
--------------------------
Written before the run, in ``notes/leak_contrast_prereg.md``:

  P1 (negative control)  Python should be unaffected.  The superseded rule
     differs from the released rule only where top-level ``title``/``body`` carry
     real text; the Python subset sets both to the literal "placeholder", so both
     rules select ``problem_statement`` and the two queries are identical.  A
     non-zero Python effect would falsify the mechanism, not merely weaken it.
  P2 (differential)      Cue-exploiting methods should gain more than plain BM25,
     because pull-request text names the files and symbols the patch touched,
     which is precisely what those components consume.

Output
------
``results/contrast_leaky_v1/main_<lang>.jsonl`` with ``query_protocol`` set to
``legacy_mixed_v1``.  The rows are deliberately *not* valid Protocol V2 rows:
``verify_results_v2.py`` rejects them by protocol id, and they must never be
averaged into a V2 table.  They exist only as the treatment arm of this contrast.

Usage
-----
    python run_leak_contrast.py --verify-only
    python run_leak_contrast.py --langs c cpp go java js kotlin python rust ts \
        --methods bm25 bm25_path anchor_path_only anchor_symbol_only \
                  bm25_anchor bm25_graph bm25_anchor_graph anchor_path_graph
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

import audit_query_leakage as aql  # noqa: E402
import dataset  # noqa: E402
import run_experiment as rx  # noqa: E402

# The label stamped into every treatment row.  It is deliberately distinct from
# QUERY_PROTOCOL so that no downstream V2 consumer can mistake a deliberately
# leaked row for a released one.
LEGACY_PROTOCOL = "legacy_mixed_v1"
DEFAULT_OUT = ROOT / "results" / "contrast_leaky_v1"
FORBIDDEN_OUT = (ROOT / "results" / "raw_v2").resolve()


def build_treatment() -> list:
    """Return V2 instances with only ``query``/``stats`` replaced by V1's.

    Gold files, test files, ids, and language come from the authoritative loader
    so the two arms share one ground truth by construction.
    """
    corpus = aql.load_raw_corpus()
    control = dataset.load_all()
    # The audited hashes of the superseded queries.  Comparing against them turns
    # "this looks like the old rule" into a per-instance equality proof.
    audited = json.loads(aql.LEGACY_HASHES.read_text(encoding="utf-8"))
    treatment = []
    missing, mismatched, empty, unaudited = [], [], [], []
    for inst in control:
        entry = corpus.get(inst.instance_id)
        if entry is None:
            missing.append(inst.instance_id)
            continue
        query = aql.legacy_query(entry["row"])
        if not query:
            empty.append(inst.instance_id)
        digest = hashlib.sha256(query.encode()).hexdigest()
        expected = audited.get(inst.instance_id)
        if expected is None:
            unaudited.append(inst.instance_id)
        elif digest != expected:
            mismatched.append(inst.instance_id)
        stats = dict(inst.stats)
        stats["query_protocol"] = LEGACY_PROTOCOL
        stats["query_source"] = "legacy_mixed"
        stats["fields_used"] = ["title", "body", "problem_statement", "resolved_issues"]
        treatment.append(dataclasses.replace(inst, query=query, stats=stats))
    return treatment, {"missing": missing, "mismatched": mismatched,
                       "empty": empty, "unaudited": unaudited}


def verify_only() -> int:
    """Prove the treatment rule is the audited one, then stop."""
    treatment, problems = build_treatment()
    print(f"treatment instances: {len(treatment)}")
    for key, ids in problems.items():
        print(f"  {key}: {len(ids)}" + (f" e.g. {ids[:3]}" if ids else ""))
    if problems["mismatched"]:
        print("FAIL: treatment queries do not match the audited legacy hashes")
        return 1
    if problems["missing"]:
        print("FAIL: instances with no raw row")
        return 1
    if problems["unaudited"]:
        print("FAIL: instances absent from the audited legacy hash set")
        return 1
    if problems["empty"]:
        print("FAIL: empty treatment queries would abort the run")
        return 1
    by_lang: dict[str, int] = {}
    changed = 0
    control = {i.instance_id: i for i in dataset.load_all()}
    for inst in treatment:
        by_lang[inst.lang] = by_lang.get(inst.lang, 0) + 1
        if inst.query != control[inst.instance_id].query:
            changed += 1
    print("  queries differing from the released rule:", changed)
    for lang, n in sorted(by_lang.items()):
        print(f"  {lang:8s} {n}")
    print("VERIFIED: treatment queries are the audited superseded rule")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="*", default=None)
    ap.add_argument("--methods", nargs="*", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    if args.verify_only:
        raise SystemExit(verify_only())

    out_dir = (args.out or DEFAULT_OUT).resolve()
    if out_dir == FORBIDDEN_OUT:
        raise SystemExit("refusing to write deliberately-leaked rows into results/raw_v2")

    langs = args.langs or ["c", "cpp", "go", "java", "js", "kotlin", "python", "rust", "ts"]
    methods = args.methods or [
        "bm25", "bm25_path", "anchor_path_only", "anchor_symbol_only",
        "bm25_anchor", "bm25_graph", "bm25_anchor_graph", "anchor_path_graph",
    ]

    treatment, problems = build_treatment()
    for key, ids in problems.items():
        if ids:
            raise SystemExit(f"{key}: {len(ids)} instances -- refusing to run")
    by_id = {i.instance_id: i for i in treatment}

    # --- the only two things this experiment changes -------------------------
    # 1. the instance source: V1 queries instead of V2 queries
    rx.load_all = lambda _langs=None: list(by_id.values())
    # 2. the protocol label stamped on every row and on the completion marker
    rx.QUERY_PROTOCOL = LEGACY_PROTOCOL
    # run_all writes its summary next to RAW_OUT; keep it out of results/raw/
    rx.RAW_OUT = out_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CONTRAST.json").write_text(json.dumps({
        "purpose": (
            "Treatment arm of the query-provenance contrast. Rows are produced by "
            "the released pipeline with the superseded query rule and are NOT "
            "Protocol V2 results; they must never enter a V2 aggregate."
        ),
        "treatment_protocol": LEGACY_PROTOCOL,
        "control_protocol": dataset.QUERY_PROTOCOL,
        "treatment_query_rule": "audit_query_leakage.legacy_query",
        "control_query_rule": "dataset.build_query",
        "held_fixed": [
            "repository index", "candidate protocol", "method configurations",
            "metric implementation", "gold definitions",
        ],
        "prereg": "notes/leak_contrast_prereg.md",
        "langs": langs,
        "methods": methods,
    }, indent=2), encoding="utf-8")

    for lang in langs:
        out = out_dir / f"main_{lang}.jsonl"
        rx.run_all(methods, [lang], True, out, 0, 0, 0)


if __name__ == "__main__":
    main()
