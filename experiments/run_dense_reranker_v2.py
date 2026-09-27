#!/usr/bin/env python3
"""SweRankEmbed reranking of BM25's top-k candidates under Protocol V2.

This is a deliberately labelled two-stage baseline, not full-corpus dense
retrieval.  The BM25 tail is retained unchanged, so the reranker can improve
ordering but cannot manufacture recall beyond BM25's candidate set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from config import INDEX_DIR  # noqa: E402
from dataset import QUERY_PROTOCOL, TEST_FILTER_PROTOCOL, load_all  # noqa: E402
from evaluate import METRIC_PROTOCOL  # noqa: E402
from run_experiment import METHODS, eval_instance, load_index, rank_with, repo_balanced  # noqa: E402

MODEL_ID = "Salesforce/SweRankEmbed-Small"
MODEL_REVISION = "745d2a06103a66d3cfa600aa52fc0d3523010daa"
REMOTE_CODE_REVISION = "92d97331f1f4b6a366c1f161354b9f3390cc219f"
METHOD = "bm25_swerank_rerank50"
QUERY_PREFIX = "Represent this query for searching relevant code: "


def choose_device(requested: str) -> str:
    import torch
    if requested != "auto":
        return requested
    return "mps" if torch.backends.mps.is_available() else "cpu"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--max-seq-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--cap", type=int, default=0)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from sentence_transformers import SentenceTransformer

    device = choose_device(args.device)
    model = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION,
                                trust_remote_code=True, device=device,
                                model_kwargs={"code_revision": REMOTE_CODE_REVISION})
    model.max_seq_length = args.max_seq_length

    instances = load_all()
    source_by_id = {(row.lang, row.instance_id): row for row in instances}
    expected = Counter(row.lang for row in instances)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    seen: set[str] = set()
    if args.resume and args.out.exists():
        for line in args.out.read_text().splitlines():
            row = json.loads(line)
            if (row.get("method"), row.get("model_revision"), row.get("candidate_k"),
                    row.get("max_seq_length"), row.get("candidate_protocol")) != (
                    METHOD, MODEL_REVISION, args.candidate_k, args.max_seq_length,
                    TEST_FILTER_PROTOCOL) or row.get("metric_protocol") != METRIC_PROTOCOL:
                raise RuntimeError("resume file has incompatible configuration")
            seen.add(row["instance_id"])
            rows += 1
    passage_cache: dict[str, object] = {}

    with args.out.open("a" if args.resume else "w", encoding="utf-8") as output:
        for lang in args.langs:
            files = sorted((INDEX_DIR / lang).glob("*.json.gz"))
            if len(files) < 0.9 * expected[lang]:
                raise RuntimeError(f"incomplete {lang} index: {len(files)}/{expected[lang]}")
            files = repo_balanced(files, args.cap)
            if args.limit:
                files = files[:args.limit]
            print(f"### {lang}: {len(files)}", flush=True)
            for number, path in enumerate(files, 1):
                doc = load_index(path)
                if doc["instance_id"] in seen:
                    continue
                source = source_by_id[(lang, doc["instance_id"])]
                if source.stats.get("query_protocol") != QUERY_PROTOCOL or not source.query:
                    raise RuntimeError(f"unsafe query: {source.instance_id}")
                doc["query"] = source.query
                doc["gold_files"] = source.gold_files
                doc["test_files"] = source.test_files

                started = time.time()
                bm25_ranked, candidates, _ = rank_with(doc, METHODS["bm25"], True)
                candidate_paths = bm25_ranked[:args.candidate_k]
                by_path = {item["path"]: item for item in doc["files"]}
                passages = [path + "\n" + by_path[path].get("text", "")[:60_000]
                            for path in candidate_paths]
                query_embedding = model.encode(
                    [QUERY_PREFIX + doc["query"]], batch_size=1,
                    normalize_embeddings=True, show_progress_bar=False)[0]
                passage_keys = [hashlib.sha256(text.encode()).hexdigest() for text in passages]
                missing_keys: list[str] = []
                missing_passages: list[str] = []
                for key, passage in zip(passage_keys, passages):
                    if key not in passage_cache and key not in missing_keys:
                        missing_keys.append(key)
                        missing_passages.append(passage)
                if missing_passages:
                    fresh = model.encode(
                        missing_passages, batch_size=args.batch_size,
                        normalize_embeddings=True, show_progress_bar=False)
                    passage_cache.update(zip(missing_keys, fresh))
                passage_embeddings = __import__("numpy").stack(
                    [passage_cache[key] for key in passage_keys])
                scores = passage_embeddings @ query_embedding
                reranked_head = [candidate_paths[i] for i in sorted(
                    range(len(candidate_paths)), key=lambda i: (-float(scores[i]), candidate_paths[i]))]
                head = set(candidate_paths)
                ranked = reranked_head + [item for item in bm25_ranked if item not in head]
                metrics, info = eval_instance(doc, ranked, candidates)
                elapsed = time.time() - started
                output.write(json.dumps({
                    "instance_id": doc["instance_id"], "lang": lang, "repo": doc["repo"],
                    "method": METHOD, "query_protocol": QUERY_PROTOCOL,
                    "candidate_protocol": TEST_FILTER_PROTOCOL,
                    "metric_protocol": METRIC_PROTOCOL,
                    "query_source": source.stats["query_source"],
                    "query_sha256": hashlib.sha256(doc["query"].encode()).hexdigest(),
                    "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                    "remote_code_revision": REMOTE_CODE_REVISION,
                    "query_prefix": QUERY_PREFIX, "device": device,
                    "candidate_k": args.candidate_k, "max_seq_length": args.max_seq_length,
                    "batch_size": args.batch_size, **metrics.as_row(), **info,
                    "dense_cache_hits": len(passages) - len(missing_passages),
                    "top10": ranked[:10], "secs": round(elapsed, 3),
                    "n_files": doc["n_files"], "n_candidates": len(candidates),
                }, ensure_ascii=False) + "\n")
                output.flush()
                rows += 1
                seen.add(doc["instance_id"])
                if number % 5 == 0:
                    print(f"  [{number}/{len(files)}]", flush=True)

    done = {
        "status": "complete", "out": str(args.out), "rows": rows,
        "instances": len(seen), "langs": args.langs, "method": METHOD,
        "query_protocol": QUERY_PROTOCOL, "model_id": MODEL_ID,
        "candidate_protocol": TEST_FILTER_PROTOCOL,
        "metric_protocol": METRIC_PROTOCOL,
        "model_revision": MODEL_REVISION, "candidate_k": args.candidate_k,
        "remote_code_revision": REMOTE_CODE_REVISION,
        "max_seq_length": args.max_seq_length, "batch_size": args.batch_size,
        "device": device, "limit": args.limit, "cap": args.cap,
    }
    args.out.with_name(args.out.name + ".done").write_text(json.dumps(done, indent=2) + "\n")
    print(json.dumps(done, indent=2), flush=True)


if __name__ == "__main__":
    main()
