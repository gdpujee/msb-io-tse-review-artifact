#!/usr/bin/env python3
"""Treatment arm of the query-provenance contrast for the dense reranker.

The lexical contrast (``run_leak_contrast.py``) answers "what is the leaked
query worth to a sparse or structural ranker?"  It cannot answer the question a
reader is more likely to ask, because the leaked material is *natural language*
-- a pull-request title and body, which frequently name the modified component
and sometimes the file.  A task-specific neural retriever is trained to match
exactly that kind of text against code, so it is the method most likely to
extract additional signal from it.

This script therefore re-runs the *dense* method under the superseded rule.
It does not reimplement anything: ``run_dense_reranker_v2.main`` is called with
its ranking, candidate-selection, reranking, and metric code untouched.  The
only two names swapped are the instance source (V1 queries instead of V2) and
the protocol label stamped on every row and on the completion marker.

Consequence worth stating explicitly, because it differs from the lexical arm:
the candidate set is BM25's top-50 *under the same query*, so the treatment arm
changes both the head that is reranked and the text used to rerank it.  That is
not a flaw -- it is the comparison a leaderboard consumer actually faces, where
the published number was produced by a pipeline whose every stage saw the
superseded query.  The paired difference is still attributable to the query
rule alone, because the rule is the only thing that differs between arms.

Output is written to ``results/contrast_leaky_dense_v1/`` -- a *different*
directory from the lexical treatment arm, so that the ``main_*.jsonl`` glob
used by ``analyze_leak_contrast.py`` and ``make_figures_v2.py`` cannot pick
these rows up.  Every row carries ``query_protocol = legacy_mixed_v1`` and is
rejected by ``verify_results_v2.py``.

Usage
-----
    python run_leak_contrast_dense.py --verify-only
    python run_leak_contrast_dense.py --resume
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

import run_dense_reranker_v2 as rd  # noqa: E402
from run_leak_contrast import LEGACY_PROTOCOL, build_treatment  # noqa: E402

DEFAULT_OUT = ROOT / "results" / "contrast_leaky_dense_v1" / "swerank_all.jsonl"
LANGS = ["c", "cpp", "go", "java", "js", "kotlin", "python", "rust", "ts"]


def verified_treatment() -> dict:
    """Build the treatment instances, refusing to proceed on any defect."""
    treatment, problems = build_treatment()
    for key, ids in problems.items():
        if ids:
            raise SystemExit(f"{key}: {len(ids)} instances -- refusing to run")
    return {i.instance_id: i for i in treatment}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--langs", nargs="*", default=None)
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--resume", action="store_true")
    # Forwarded verbatim to run_dense_reranker_v2 so the two arms are configured
    # identically; candidate_k and max_seq_length change the result, batch_size
    # only the throughput.
    ap.add_argument("--candidate-k", type=int, default=50)
    ap.add_argument("--max-seq-length", type=int, default=512)
    ap.add_argument("--batch-size", type=int, default=24)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    by_id = verified_treatment()

    if args.verify_only:
        print(f"treatment instances: {len(by_id)}")
        missing = [iid for iid, inst in by_id.items()
                   if inst.stats.get("query_protocol") != LEGACY_PROTOCOL]
        print(f"  instances not carrying {LEGACY_PROTOCOL}: {len(missing)}")
        if missing:
            raise SystemExit("FAIL: treatment label missing")
        print("VERIFIED: dense treatment arm would be scored on the audited "
              "superseded queries")
        return

    out = (args.out or DEFAULT_OUT).resolve()
    if "raw_v2" in out.parts:
        raise SystemExit("refusing to write deliberately-leaked rows into results/raw_v2")

    # --- the only two things this experiment changes -------------------------
    rd.load_all = lambda _langs=None: list(by_id.values())
    rd.QUERY_PROTOCOL = LEGACY_PROTOCOL

    langs = args.langs or LANGS
    argv = ["run_leak_contrast_dense.py", "--langs", *langs, "--out", str(out),
            "--candidate-k", str(args.candidate_k),
            "--max-seq-length", str(args.max_seq_length),
            "--batch-size", str(args.batch_size),
            "--device", args.device]
    if args.resume:
        argv.append("--resume")
    sys.argv = argv
    rd.main()


if __name__ == "__main__":
    main()
