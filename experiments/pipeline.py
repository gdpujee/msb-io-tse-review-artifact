"""Build the per-instance repository index.

For each instance: download the base-commit tarball, parse every source file
with tree-sitter, store a compact JSON index, then **delete the source tree**.
This keeps disk bounded (measured: a full repo tarball is often < 1 MB).

Output: data/index/{lang}/{instance_id}.json.gz
  {instance_id, lang, org, repo, sha, n_files, n_defs, n_calls, n_imports,
   parse stats, gold_files, test_files, query, files:[{path, n_lines, defs, calls, imports, text}] }
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import INDEX_DIR, DATA_DIR, SRC_EXT  # noqa: E402
from dataset import load_all  # noqa: E402
from fetch_data import stream_source, _free_bytes, MIN_FREE_BYTES  # noqa: E402
from parse_repo import parse_sources, index_stats  # noqa: E402

MAX_FILE_CHARS = 60_000  # cap stored text per file; recorded (affects BM25 input, not the file list)
MAX_REPO_SOURCE_BYTES = 250_000_000  # refuse to materialise a repo larger than this in RAM


def index_path(lang: str, instance_id: str) -> Path:
    d = INDEX_DIR / lang
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{instance_id}.json.gz"


def process_instance(inst, force: bool = False) -> dict | None:
    """Stream the base-commit tarball, parse in memory, write a gz index.

    No source is ever written to disk (see FAILURES.md F008 / F008b).
    """
    out = index_path(inst.lang, inst.instance_id)
    if out.exists() and not force:
        return {"status": "cached", "instance_id": inst.instance_id}
    free = _free_bytes(INDEX_DIR)
    if 0 <= free < MIN_FREE_BYTES:
        return {"status": "low_disk", "instance_id": inst.instance_id,
                "lang": inst.lang, "free_gb": round(free / 1e9, 1)}
    t0 = time.time()
    try:
        # language-specific extension set: using the union over languages
        # polluted the corpus with vendored foreign-language files (F010)
        pairs = list(stream_source(inst.org, inst.repo, inst.base_sha,
                                   exts=SRC_EXT.get(inst.lang, set()),
                                   max_bytes=MAX_REPO_SOURCE_BYTES))
    except Exception as e:  # noqa: BLE001
        return {"status": "fetch_failed", "instance_id": inst.instance_id,
                "lang": inst.lang, "error": str(e)[:200]}
    if not pairs:
        return {"status": "fetch_failed", "instance_id": inst.instance_id,
                "lang": inst.lang, "error": "no source files"}
    try:
        idx = parse_sources(pairs, inst.lang)
        texts = {rel: src.decode("utf-8", errors="ignore")[:MAX_FILE_CHARS]
                 for rel, src in pairs}
        del pairs
        files = []
        for f in idx["files"]:
            f["text"] = texts.get(f["path"], "")
            f.pop("error", None)
            files.append(f)
        del texts
        doc = {
            "instance_id": inst.instance_id,
            "lang": inst.lang,
            "org": inst.org,
            "repo": inst.repo,
            "sha": inst.base_sha,
            "query": inst.query,
            "gold_files": inst.gold_files,
            "test_files": inst.test_files,
            "stats_query": inst.stats,
            "stats_parse": {k: v for k, v in idx.items() if k != "files"},
            "n_files": len(files),
            "files": files,
        }
        with gzip.open(out, "wt", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        st = index_stats(idx)
        return {"status": "ok", "instance_id": inst.instance_id, "lang": inst.lang,
                "n_files": st["n_files"], "n_defs": st["n_defs"], "n_calls": st["n_calls"],
                "n_imports": st["n_imports"], "frac_files_with_defs": st["frac_files_with_defs"],
                "secs": round(time.time() - t0, 2),
                "mb": round(out.stat().st_size / 1e6, 3)}
    except Exception as e:  # noqa: BLE001
        return {"status": "parse_failed", "instance_id": inst.instance_id,
                "lang": inst.lang, "error": str(e)[:200]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=0, help="per-language limit")
    ap.add_argument("--part", type=int, default=0,
                    help="0-based shard index; with --parts N this worker only "
                         "handles instances i where i %% N == part")
    ap.add_argument("--parts", type=int, default=1, help="number of shards")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--log", type=Path, default=DATA_DIR / "index_log.jsonl")
    args = ap.parse_args()

    insts = load_all(args.langs)
    by_lang: dict[str, list] = {}
    for i in insts:
        by_lang.setdefault(i.lang, []).append(i)
    for lang in by_lang:
        by_lang[lang].sort(key=lambda x: x.instance_id)
        if args.limit:
            by_lang[lang] = by_lang[lang][: args.limit]
        if args.parts > 1:
            by_lang[lang] = by_lang[lang][args.part :: args.parts]

    t0 = time.time()
    n_ok = n_fail = n_cached = 0
    with args.log.open("a", encoding="utf-8") as log:
        for lang, items in by_lang.items():
            print(f"### {lang}: {len(items)} instances", flush=True)
            for n, inst in enumerate(items, 1):
                r = process_instance(inst, force=args.force)
                if r is None:
                    continue
                log.write(json.dumps(r, ensure_ascii=False) + "\n")
                if r["status"] == "ok":
                    n_ok += 1
                elif r["status"] == "cached":
                    n_cached += 1
                else:
                    n_fail += 1
                if n % 10 == 0 or n == len(items):
                    print(f"  [{n}/{len(items)}] ok={n_ok} cached={n_cached} fail={n_fail} "
                          f"last={r.get('instance_id')} {r.get('n_files','-')} files "
                          f"{r.get('secs','-')}s", flush=True)
    total_mb = sum(p.stat().st_size for p in INDEX_DIR.rglob("*.json.gz")) / 1e6
    print(f"DONE ok={n_ok} cached={n_cached} fail={n_fail} index={total_mb:.1f} MB "
          f"in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
