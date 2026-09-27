"""Run the retrieval method ladder over the built index; write raw per-instance results.

Method ladder (see notes/research_design.md):
  B1  bm25                     sparse lexical over file content
  B2  bm25_path                + file-path augmentation
  B5  ..._anchor               + symbol anchors extracted from the issue text
  B6  ..._anchor_graph         + dependency-graph expansion   <-- proposed

Every result row carries its full config so that any number in the paper can be
traced to (code, config, instance).
"""
from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import INDEX_DIR, RESULTS_DIR, TEST_PATH_HINTS, SRC_EXT  # noqa: E402
from evaluate import METRIC_PROTOCOL, evaluate_ranking, aggregate, Metrics  # noqa: E402
from retrieval import BM25, build_corpus, tokenize_code  # noqa: E402
from methods import (RepoSymbols, anchor_scores, extract_path_candidates, graph_expand,  # noqa: E402
                     minmax_norm, rank_list, rrf_fuse)
from dataset import QUERY_PROTOCOL, TEST_FILTER_PROTOCOL, _looks_test, load_all  # noqa: E402

RAW_OUT = RESULTS_DIR / "raw"
RAW_OUT.mkdir(parents=True, exist_ok=True)
_SRC_SUFFIXES = {e for exts in SRC_EXT.values() for e in exts}

# --- method configurations ----------------------------------------------------

def _cfg(path_repeat=1, anchor=0.0, graph=0.0, hops=1, decay=0.5,
         reverse=True, use_import=True, use_call=True, seed_topk=20, **kw):
    return dict(path_repeat=path_repeat, anchor=anchor, graph=graph, hops=hops,
                decay=decay, reverse=reverse, use_import=use_import,
                use_call=use_call, seed_topk=seed_topk, **kw)


METHODS: dict[str, dict] = {
    # --- baselines
    "bm25":                     _cfg(path_repeat=1),
    "bm25_path":                _cfg(path_repeat=3),
    "bm25_anchor":              _cfg(path_repeat=1, anchor=1.0),
    "bm25_graph":               _cfg(path_repeat=1, graph=1.0, hops=1),
    "bm25_anchor_graph":        _cfg(path_repeat=1, anchor=1.0, graph=1.0, hops=1),
    "bm25_path_anchor":         _cfg(path_repeat=3, anchor=1.0),
    # --- proposed
    "bm25_path_anchor_graph":   _cfg(path_repeat=3, anchor=1.0, graph=1.0, hops=1),
    # --- ablations of the proposed method
    # --- decomposing the anchor component (RQ3: symbol vs path) -------------
    "anchor_symbol_only":       _cfg(path_repeat=1, anchor=1.0, anchor_mode="symbol"),
    "anchor_path_only":         _cfg(path_repeat=1, anchor=1.0, anchor_mode="path"),
    "anchor_path_graph":        _cfg(path_repeat=1, anchor=1.0, anchor_mode="path",
                                      graph=1.0, hops=1),
    "bm25_path_anchor_symbol":  _cfg(path_repeat=3, anchor=1.0, anchor_mode="symbol"),
    "bm25_path_anchor_path":    _cfg(path_repeat=3, anchor=1.0, anchor_mode="path"),
    # --- anchor-path weight sensitivity (RQ3 / F012) -------------------------
    # The path-anchor list is tiny (0-5 files). With RRF weight 1.0 an anchored
    # file only *ties* with BM25's rank-1 (both get 1/(60+1)), so the effect is
    # partly decided by the index tie-break -- clearly not intended. Sweep the
    # weight on the dev split and fix it there, never on the test instances.
    "anchor_path_w1":           _cfg(path_repeat=1, anchor=1.0, anchor_mode="path"),
    "anchor_path_w2":           _cfg(path_repeat=1, anchor=2.0, anchor_mode="path"),
    "anchor_path_w3":           _cfg(path_repeat=1, anchor=3.0, anchor_mode="path"),
    "anchor_path_w5":           _cfg(path_repeat=1, anchor=5.0, anchor_mode="path"),
    "anchor_path_w10":          _cfg(path_repeat=1, anchor=10.0, anchor_mode="path"),
    # --- graph weight sensitivity (RQ2 / F006) -------------------------------
    "graph_w01":                _cfg(path_repeat=3, anchor=1.0, graph=0.1),
    "graph_w02":                _cfg(path_repeat=3, anchor=1.0, graph=0.2),
    "graph_w03":                _cfg(path_repeat=3, anchor=1.0, graph=0.3),
    "graph_w05":                _cfg(path_repeat=3, anchor=1.0, graph=0.5),
    # --- ablations of the proposed method
    "abl_no_anchor":            _cfg(path_repeat=3, anchor=0.0, graph=1.0, hops=1),
    "abl_no_graph":             _cfg(path_repeat=3, anchor=1.0, graph=0.0),
    "abl_import_only":          _cfg(path_repeat=3, anchor=1.0, graph=1.0, use_call=False),
    "abl_call_only":            _cfg(path_repeat=3, anchor=1.0, graph=1.0, use_import=False),
    "abl_fwd_only":             _cfg(path_repeat=3, anchor=1.0, graph=1.0, reverse=False),
    "abl_hop2":                 _cfg(path_repeat=3, anchor=1.0, graph=1.0, hops=2),
    "abl_seed50":               _cfg(path_repeat=3, anchor=1.0, graph=1.0, seed_topk=50),
    # graph used as a recall booster behind the primary ranker
    "cascade_graph":            _cfg(path_repeat=3, anchor=1.0, graph=1.0, hops=1, mode="cascade"),
    "cascade_graph_hop2":       _cfg(path_repeat=3, anchor=1.0, graph=1.0, hops=2, mode="cascade"),
}


def repo_balanced(files: list[Path], cap: int) -> list[Path]:
    """Round-robin sample across repositories, at most `cap` instances.

    Two reasons this exists:
      1. Runtime. go has 428 instances and python 500; a full pass costs hours.
      2. Balance. Repositories are sampled very unevenly in Multi-SWE-bench
         (e.g. ponyc is 64% of the C instances), and measured between-repo
         difficulty variance far exceeds between-method variance. A
         repo-balanced subsample makes the language-level estimate far less
         sensitive to which repos happen to dominate the split.

    Sampling is deterministic (sorted instance ids, round-robin) and is
    reported as an explicit threat to validity.
    """
    if not cap or len(files) <= cap:
        return files
    by_repo: dict[str, list[Path]] = defaultdict(list)
    for p in files:
        by_repo[p.stem.rsplit("-", 1)[0]].append(p)
    keys = sorted(by_repo)
    out: list[Path] = []
    i = 0
    while len(out) < cap:
        added = False
        for k in keys:
            if i < len(by_repo[k]):
                out.append(by_repo[k][i])
                added = True
                if len(out) >= cap:
                    break
        if not added:
            break
        i += 1
    return sorted(out)


def load_index(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def select_candidates(doc: dict, exclude_tests: bool) -> list[dict]:
    files = doc["files"]
    if exclude_tests:
        cand = [f for f in files if not _looks_test(f["path"], TEST_PATH_HINTS)]
        return cand or files
    return files


def rank_with(doc: dict, cfg: dict, exclude_tests: bool = True,
              sym_cache: dict | None = None) -> tuple[list[str], set[str], dict]:
    cand = select_candidates(doc, exclude_tests)
    ids, toks = build_corpus(cand, path_repeat=cfg["path_repeat"])
    bm = BM25(toks)
    raw = {i: s for i, s in enumerate(bm.scores(tokenize_code(doc["query"])))}
    diag = {"n_tokens_query": len(tokenize_code(doc["query"])),
            "bm25_max": round(max(raw.values()), 2) if raw else 0.0}

    local_sym: dict[str, RepoSymbols] = {}

    def _sym():
        # reuse across methods for the same instance: building the symbol tables
        # and edges is the expensive part and is method-independent
        key = str(id(doc))
        box = sym_cache if sym_cache is not None else local_sym
        if key not in box:
            box[key] = RepoSymbols(cand)
        return box[key]

    lists: list[list[int]] = []
    weights: list[float] = []
    lists.append(rank_list(raw))
    weights.append(1.0)

    if cfg["anchor"] > 0:
        sym = _sym()
        a = anchor_scores(sym, doc["query"], mode=cfg.get("anchor_mode", "both"))
        diag["n_anchor_hits"] = len(a)
        diag["n_common_symbols"] = sym.n_common
        lists.append(rank_list(a, limit=cfg.get("anchor_topk", 50)))
        weights.append(cfg["anchor"])

    if cfg["graph"] > 0:
        sym = _sym()
        edges = sym.all_edges(use_import=cfg["use_import"], use_call=cfg["use_call"])
        diag["n_edges"] = sum(len(v) for v in edges.values())
        diag["n_nodes_with_edges"] = len(edges)
        # seeds: union of what BM25 and (optionally) anchors retrieved so far
        seed_scores: dict[int, float] = {}
        for lst, w in zip(lists, weights):
            for r, i in enumerate(lst[: cfg["seed_topk"]]):
                seed_scores[i] = seed_scores.get(i, 0.0) + w / (60 + r + 1)
        g = graph_expand(sym, seed_scores, edges, hops=cfg["hops"],
                         decay=cfg["decay"], reverse=cfg["reverse"])
        diag["n_graph_expanded"] = len(g)
        lists.append(rank_list(g, limit=cfg.get("graph_topk", 100)))
        weights.append(cfg["graph"])

    mode = cfg.get("mode", "fuse")
    if mode == "cascade" and len(lists) > 2:
        # Graph output is used ONLY as a recall booster: files that the primary
        # ranker (BM25 + anchors) did not retrieve at all are ordered by graph
        # score *behind* everything the primary ranker retrieved. This keeps
        # head precision (hit@1/5) untouched while extending tail recall.
        # Motivation (measured on the C subset): equal-weight RRF fusion of the
        # graph list *hurt* MRR 0.505 -> 0.333, yet 60% of BM25 top-20 misses
        # are in fact 1-hop neighbours of the seeds -- i.e. the signal is real
        # but too noisy to be given the same weight as lexical evidence.
        primary = rrf_fuse(lists[:-1], k=cfg.get("rrf_k", 60), weights=weights[:-1])
        boost = {i: 1.0 / (cfg.get("rrf_k", 60) + r + 1) for r, i in enumerate(lists[-1])}
        diag["mode"] = "cascade"
        ranked_idx = sorted(range(len(ids)),
                            key=lambda i: (0 if primary.get(i, 0.0) > 0 else 1,
                                           -primary.get(i, 0.0) if primary.get(i, 0.0) > 0 else 0.0,
                                           -boost.get(i, 0.0), i))  # F009: index breaks ties
    else:
        fused = rrf_fuse(lists, k=cfg.get("rrf_k", 60), weights=weights)
        diag["mode"] = "fuse"
        ranked_idx = sorted(range(len(ids)), key=lambda i: (-fused.get(i, 0.0), i))
    ranked = [ids[i] for i in ranked_idx]
    return ranked, set(ids), diag


def eval_instance(doc: dict, ranked: list[str], candidate_paths: set[str]) -> tuple[Metrics, dict]:
    """Evaluate the primary protocol and retain alternate-protocol fields.

    Primary metrics use every non-test file touched by the fix.  Files absent
    from the base-commit candidate set therefore remain genuine unreachable
    targets.  ``reachable_*`` fields support the explicitly labelled
    candidate-conditional sensitivity analysis; they are never substituted
    silently for the primary result.
    """
    gold_all = set(doc["gold_files"])
    gold_all -= set(doc.get("test_files") or [])
    gold_all = {g for g in gold_all if not _looks_test(g, TEST_PATH_HINTS)}
    gold_eval = {g for g in gold_all if g in candidate_paths}
    excluded = gold_all - gold_eval
    n_new_file = sum(1 for g in excluded if Path(g).suffix.lower() in _SRC_SUFFIXES)
    m = evaluate_ranking(ranked, gold_all)
    m.n_gold = len(gold_all)
    m.n_gold_reachable = len(gold_eval)
    m.n_unreachable = len(excluded)
    reachable = evaluate_ranking(ranked, gold_eval)
    mentioned = set(extract_path_candidates(doc["query"]))
    mentioned_lower = {p.lower() for p in mentioned}
    gold_path_cues = sorted(
        g for g in gold_all
        if g.lower() in mentioned_lower or Path(g).name.lower() in mentioned_lower
    )
    info = {"n_gold_all": len(gold_all), "n_gold_evaluable": len(gold_eval),
            "n_gold_excluded": len(excluded), "n_gold_probably_new": n_new_file,
            "no_evaluable_gold": len(gold_eval) == 0,
            "query_mentions_gold_path": bool(gold_path_cues),
            "n_gold_path_cues": len(gold_path_cues),
            "gold_path_cues": gold_path_cues,
            "gold_protocol": "non_test_fix_files_unconditional_any_v2",
            "reachable_protocol": "candidate_present_non_test_fix_files_any_v2"}
    info.update(reachable.as_row(prefix="reachable_"))
    for k in m.hit_at:
        top = set(ranked[:k])
        info[f"all_hit@{k}"] = int(bool(gold_all) and gold_all.issubset(top))
        info[f"reachable_all_hit@{k}"] = int(bool(gold_eval) and gold_eval.issubset(top))
    return m, info


def run_all(methods: list[str], langs: list[str] | None, exclude_tests: bool,
            out: Path | None = None, limit: int = 0, offset: int = 0,
            cap: int = 0) -> Path:
    # Guard: never run on a half-built index. An indexing job can be hours from
    # done while its language directory already exists with a handful of files;
    # running on it would produce a tiny, silently wrong "result" (and a .done
    # marker that stops any later re-run). Require >= 90% of the instances that
    # the dataset actually has for that language.
    instances = load_all()
    expected = Counter(i.lang for i in instances)
    source_by_id = {(i.lang, i.instance_id): i for i in instances}

    idx_dirs = sorted(INDEX_DIR.iterdir()) if not langs else [INDEX_DIR / l for l in langs]
    grouped: dict[tuple[str, str], list[Metrics]] = defaultdict(list)
    all_grouped: dict[str, list[Metrics]] = defaultdict(list)

    # Incremental output: results are appended as soon as each instance is done.
    # Previously rows were buffered and written only at the very end, so an OOM
    # at 90% of a multi-hour run destroyed the whole run (see FAILURES F009).
    out = out or (RAW_OUT / f"results_{'-'.join(methods)}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    fh = out.open("w", encoding="utf-8")
    n_written = 0
    seen: set[str] = set()

    for lang_dir in idx_dirs:
        if not lang_dir.is_dir():
            continue
        files = sorted(lang_dir.glob("*.json.gz"))
        if not files:
            continue
        exp_n = expected.get(lang_dir.name, 0)
        if exp_n and len(files) < 0.9 * exp_n:
            print(f"### {lang_dir.name}: index incomplete "
                  f"({len(files)}/{exp_n}), skipping", flush=True)
            continue
        files = repo_balanced(files, cap)
        if offset:
            files = files[offset:]
        if limit:
            files = files[:limit]
        print(f"### {lang_dir.name}: {len(files)} indexed instances", flush=True)
        for n, p in enumerate(files, 1):
            doc = load_index(p)
            source = source_by_id.get((lang_dir.name, doc["instance_id"]))
            if source is None:
                raise RuntimeError(f"index has no matching raw instance: {p}")
            if source.stats.get("query_protocol") != QUERY_PROTOCOL or not source.query:
                raise RuntimeError(
                    f"unsafe or empty query for {source.instance_id}: {source.stats}")
            # Index files created under V1 contain leaked PR text.  Repository
            # content is still valid, so replace only the query/labels from the
            # authoritative raw dataset rather than rebuilding 1.9 GB of source
            # indexes.  Never fall back to doc['query'].
            doc["query"] = source.query
            doc["stats_query"] = source.stats
            doc["gold_files"] = source.gold_files
            doc["test_files"] = source.test_files
            seen.add(doc["instance_id"])
            sym_cache = {}
            for method in methods:
                cfg = METHODS[method]
                t0 = time.time()
                ranked, cand, diag = rank_with(doc, cfg, exclude_tests, sym_cache)
                secs = time.time() - t0
                m, info = eval_instance(doc, ranked, cand)
                grouped[(lang_dir.name, method)].append(m)
                all_grouped[method].append(m)
                fh.write(json.dumps({
                    "instance_id": doc["instance_id"], "lang": doc["lang"],
                    "repo": doc["repo"], "method": method, "cfg": cfg,
                    "query_protocol": QUERY_PROTOCOL,
                    "candidate_protocol": TEST_FILTER_PROTOCOL,
                    "metric_protocol": METRIC_PROTOCOL,
                    "query_source": source.stats["query_source"],
                    "query_sha256": hashlib.sha256(doc["query"].encode()).hexdigest(),
                    **m.as_row(), **info, **diag, "top10": ranked[:10],
                    "secs": round(secs, 3), "n_files": doc["n_files"],
                    "n_candidates": len(cand),
                }, ensure_ascii=False) + "\n")
                n_written += 1
            del doc, sym_cache
            gc.collect()
            if n % 25 == 0:
                fh.flush()
                print(f"   [{n}/{len(files)}] rows={n_written}", flush=True)
    fh.close()
    if not seen:
        print("no instance processed -- not writing a completion marker", flush=True)
        return out
    # A run that is killed (OOM) leaves a truncated file that silently looks
    # like a valid result set. This marker lets every downstream step assert
    # completeness instead of averaging over a partial sample (F011).
    (out.parent / (out.name + ".done")).write_text(json.dumps({
        "out": str(out), "rows": n_written,
        "instances": len(seen),
        "methods": methods, "langs": langs, "cap": cap,
        "exclude_tests": exclude_tests,
        "query_protocol": QUERY_PROTOCOL,
        "candidate_protocol": TEST_FILTER_PROTOCOL,
        "metric_protocol": METRIC_PROTOCOL,
        "gold_protocol": "non_test_fix_files_unconditional_any_v2",
    }, indent=2), encoding="utf-8")

    # NOTE: keep this in sync with METRIC_COLS in analyze.py. It previously
    # omitted hit@3 while aggregate() returned it, so the printed table had 7
    # headers and 8 numbers and every column after hit@1 was mislabelled --
    # which made a partial run look like a huge positive result. Never read
    # numbers off this table: recompute from the raw jsonl (F011).
    cols = ["hit@1", "hit@3", "hit@5", "hit@10", "hit@20", "hit@50", "mrr", "map"]
    print("\n=== aggregate (file-level) ===")
    print(f"{'lang':8s} {'method':26s} {'n':>4s} " + " ".join(f"{c:>9s}" for c in cols))
    summary = {}
    for (lang, method), ms in sorted(grouped.items()):
        agg = aggregate(ms)
        summary[f"{lang}/{method}"] = agg
        print(f"{lang:8s} {method:26s} {agg['n']:4d} " +
              " ".join(f"{agg[c]:9.4f}" for c in cols))
    for method, ms in all_grouped.items():
        agg = aggregate(ms)
        summary[f"ALL/{method}"] = agg
        print(f"{'ALL':8s} {method:26s} {agg['n']:4d} " +
              " ".join(f"{agg[c]:9.4f}" for c in cols))
    (RAW_OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="*", default=["bm25", "bm25_path"])
    ap.add_argument("--langs", nargs="*", default=None)
    ap.add_argument("--exclude-tests", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--cap", type=int, default=0,
                    help="repo-balanced subsample of at most N instances per language")
    args = ap.parse_args()
    run_all(args.methods, args.langs, bool(args.exclude_tests), args.out,
            args.limit, args.offset, args.cap)


if __name__ == "__main__":
    main()
