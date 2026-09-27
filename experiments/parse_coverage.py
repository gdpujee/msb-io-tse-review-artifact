"""Per-language parser coverage, sampled from the built indexes.

Why this exists
---------------
The study compares nine languages that share ONE generic tree-sitter walk.
That uniformity is a deliberate design choice (a cross-language study needs an
identical procedure), but it is only fair if we *measure* how well the walk
actually works per language and report it. In particular:

  * `kotlin` has no tree-sitter binding in this environment
    (config.TS_LANG["kotlin"] is None) -> every file is flagged "no_parser",
    so `defs`/`calls`/`imports` are empty and the anchor + graph components
    are inert for that language. This must be stated, not hidden.

Output: results/tables/t9_parse_coverage.{csv,md}
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import INDEX_DIR, RESULTS_DIR  # noqa: E402

TABLES = RESULTS_DIR / "tables"
TABLES.mkdir(parents=True, exist_ok=True)


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def sample_lang(lang_dir: Path, k: int, seed: int = 0) -> list[dict]:
    files = sorted(lang_dir.glob("*.json.gz"))
    if not files:
        return []
    random.Random(seed).shuffle(files)
    out = []
    for p in files[:k]:
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:  # noqa: BLE001
            continue
    return out


def write_table(name: str, header: list[str], rows: list[list]):
    import csv
    with (TABLES / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    with (TABLES / f"{name}.md").open("w", encoding="utf-8") as f:
        f.write("| " + " | ".join(header) + " |\n")
        f.write("|" + "|".join(["---"] * len(header)) + "|\n")
        for r in rows:
            f.write("| " + " | ".join(str(x) for x in r) + " |\n")
    print(f"  wrote {TABLES}/{name}.csv + .md")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-lang", type=int, default=25)
    ap.add_argument("--langs", nargs="*", default=None)
    args = ap.parse_args()

    langs = args.langs or sorted(p.name for p in INDEX_DIR.iterdir() if p.is_dir())
    rows = []
    print(f"{'lang':8s} {'inst':>5s} {'files':>7s} {'defs/file':>9s} "
          f"{'%files w/ defs':>14s} {'%parse_err':>10s} {'%no_parser':>10s} {'edges/file':>10s}")
    for lang in langs:
        d = INDEX_DIR / lang
        if not d.is_dir():
            continue
        docs = sample_lang(d, args.per_lang)
        if not docs:
            continue
        n_files = [doc.get("n_files", len(doc.get("files", []))) for doc in docs]
        n_defs = [sum(len(f.get("defs", [])) for f in doc.get("files", [])) for doc in docs]
        n_calls = [sum(len(f.get("calls", [])) for f in doc.get("files", [])) for doc in docs]
        n_imp = [sum(len(f.get("imports", [])) for f in doc.get("files", [])) for doc in docs]
        frac_def = [sum(1 for f in doc.get("files", []) if f.get("defs")) /
                    max(1, len(doc.get("files", []))) for doc in docs]
        # stats_parse is per-document; average the per-document fractions
        no_parser = [doc.get("stats_parse", {}).get("n_no_parser", 0) /
                     max(1, doc.get("n_files", 1)) for doc in docs]
        parse_err = [doc.get("stats_parse", {}).get("n_parse_has_error", 0) /
                     max(1, doc.get("n_files", 1)) for doc in docs]
        rows.append([lang, len(docs), round(mean(n_files), 1), round(mean(n_defs) /
                    max(1e-9, mean(n_files)), 2), round(mean(frac_def), 3),
                    round(mean(parse_err), 3), round(mean(no_parser), 3),
                    round(mean(n_calls) / max(1e-9, mean(n_files)), 2),
                    round(mean(n_imp) / max(1e-9, mean(n_files)), 2)])
        print(f"{lang:8s} {len(docs):5d} {mean(n_files):7.1f} "
              f"{mean(n_defs) / max(1e-9, mean(n_files)):9.2f} "
              f"{mean(frac_def):14.3f} {mean(parse_err):10.3f} {mean(no_parser):10.3f} "
              f"{mean(n_calls) / max(1e-9, mean(n_files)):10.2f}")
    write_table("t9_parse_coverage",
                ["lang", "n_instances_sampled", "avg_files", "defs_per_file",
                 "frac_files_with_defs", "frac_parse_error", "frac_no_parser",
                 "calls_per_file", "imports_per_file"], rows)
    print("\nDONE")


if __name__ == "__main__":
    main()
