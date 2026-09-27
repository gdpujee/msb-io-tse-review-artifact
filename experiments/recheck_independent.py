"""Independent re-check of the headline cross-language claims.

This script deliberately does NOT import analyze.py / stats.py. It reads the raw
per-instance jsonl directly and recomputes everything from scratch, so the paper
numbers have a second, independent derivation path (double-check rule, F011).

Claims re-checked:
  C1  cross-language spread of BM25 file-level localization (3.1x hit@1)
  C2  path anchor improves hit@1 / MRR in 9/9 languages (sign test)
  C3  symbol anchor inconsistent / often negative
  C4  graph expansion hurts MRR in most languages
  C5  BM25 hit@50 saturated (0.859-0.987) across all 9 languages
"""
from __future__ import annotations

import json
from collections import defaultdict
from math import comb
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results" / "raw"
LANGS = ["c", "cpp", "go", "java", "js", "kotlin", "python", "rust", "ts"]


def sign_test_p(npos: int, n: int) -> float:
    if n == 0:
        return 1.0
    k = min(npos, n - npos)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def load() -> list[dict]:
    rows = []
    for lang in LANGS:
        f = RESULTS / f"main_{lang}.jsonl"
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    # clean path-anchor isolation (path_repeat=1 on both sides)
    extra = RESULTS / "main_anchor_path_only.jsonl"
    if extra.exists():
        for line in extra.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    rows = load()
    print(f"loaded {len(rows)} rows, {len({r['instance_id'] for r in rows})} instances\n")

    by_lang_method = defaultdict(list)
    for r in rows:
        by_lang_method[(r["lang"], r["method"])].append(r)

    # ---- C1 + C5: BM25 per-language baseline ----
    print("=" * 70)
    print("C1 / C5 : BM25 baseline per language (hit@1, mrr, hit@50)")
    print("=" * 70)
    bm25 = {}
    for lang in LANGS:
        sub = by_lang_method[(lang, "bm25")]
        h1 = sum(r["hit@1"] for r in sub) / len(sub)
        mrr = sum(r["mrr"] for r in sub) / len(sub)
        h50 = sum(r["hit@50"] for r in sub) / len(sub)
        bm25[lang] = (len(sub), h1, mrr, h50)
        print(f"  {lang:8s} n={len(sub):4d}  hit@1={h1:.4f}  mrr={mrr:.4f}  hit@50={h50:.4f}")
    h1s = [v[1] for v in bm25.values()]
    h50s = [v[3] for v in bm25.values()]
    print(f"\n  -> hit@1 spread: {min(h1s):.3f} ({LANGS[h1s.index(min(h1s))]}) .. "
          f"{max(h1s):.3f} ({LANGS[h1s.index(max(h1s))]}); ratio = {max(h1s)/min(h1s):.2f}x")
    print(f"  -> hit@50 range: {min(h50s):.3f} .. {max(h50s):.3f}  (saturated)")

    # ---- C2 / C3 / C4: paired delta vs bm25, sign test across languages ----
    print("\n" + "=" * 70)
    print("C2/C3/C4 : paired delta vs BM25, sign test across 9 languages")
    print("=" * 70)
    methods = sorted({r["method"] for r in rows if r["method"] != "bm25"})
    for metric in ["hit@1", "mrr", "hit@10"]:
        print(f"\n--- metric = {metric} ---")
        for m in methods:
            deltas = []
            for lang in LANGS:
                a = {r["instance_id"]: r[metric] for r in by_lang_method[(lang, "bm25")]}
                b = {r["instance_id"]: r[metric] for r in by_lang_method[(lang, m)]}
                ks = sorted(set(a) & set(b))
                if len(ks) < 10:
                    continue
                per_inst = [(b[k] - a[k]) for k in ks]
                # micro (instance-pooled) mean delta:
                micro_delta = sum(per_inst) / len(per_inst)
                # language-averaged mean delta (what analyze.py t3b reports as mean_lang_delta)
                deltas.append((lang, len(ks), micro_delta))
            n = len(deltas)
            npos = sum(1 for _, _, d in deltas if d > 0)
            nneg = sum(1 for _, _, d in deltas if d < 0)
            p = sign_test_p(npos, n)
            mean_lang_delta = sum(d for _, _, d in deltas) / n
            print(f"  {m:26s} n_langs={n} pos={npos} neg={nneg} "
                  f"sign_p={p:.4f}  mean_lang_delta={mean_lang_delta:+.4f}")

    # ---- clean isolation of PATH ANCHOR (path_repeat=1 on both sides) ----
    print("\n" + "=" * 70)
    print("CLEAN PATH-ANCHOR ISOLATION: anchor_path_only vs bm25 (path_repeat=1 both)")
    print("=" * 70)
    present = all((lang, "anchor_path_only") in by_lang_method for lang in LANGS)
    if not present:
        print("  [SKIP] anchor_path_only not in this dataset (only in C ablation). "
              "Run it 9-lang to isolate the path-anchor effect. See text.")
        return
    for metric in ["hit@1", "mrr"]:
        deltas = []
        for lang in LANGS:
            a = {r["instance_id"]: r[metric] for r in by_lang_method[(lang, "bm25")]}
            b = {r["instance_id"]: r[metric] for r in by_lang_method[(lang, "anchor_path_only")]}
            ks = sorted(set(a) & set(b))
            if len(ks) < 10:
                continue
            per_inst = [b[k] - a[k] for k in ks]
            deltas.append((lang, sum(per_inst) / len(per_inst)))
        n = len(deltas)
        npos = sum(1 for _, d in deltas if d > 0)
        p = sign_test_p(npos, n)
        mean_delta = sum(d for _, d in deltas) / n
        print(f"  {metric:6s}: n_langs={n} pos={npos} sign_p={p:.4f} "
              f"mean_lang_delta={mean_delta:+.4f}")
        for lang, d in deltas:
            print(f"      {lang:8s} {d:+.4f}")

    print("\nDONE")


if __name__ == "__main__":
    main()
