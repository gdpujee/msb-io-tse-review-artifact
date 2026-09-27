"""Independent integrity and aggregate re-check for Protocol V2 raw results.

This script intentionally does not import analyze.py or stats_v2.py. It checks
the raw evidence chain and recomputes the main descriptive effects through an
independent aggregation path.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import RESULTS_DIR  # noqa: E402
from dataset import QUERY_PROTOCOL, TEST_FILTER_PROTOCOL, load_all  # noqa: E402
from evaluate import METRIC_PROTOCOL  # noqa: E402
from run_experiment import METHODS  # noqa: E402

LANGS = ("c", "cpp", "go", "java", "js", "kotlin", "python", "rust", "ts")
MAIN_METHODS = (
    "bm25", "bm25_path", "anchor_path_only", "anchor_symbol_only",
    "bm25_anchor", "bm25_graph", "bm25_anchor_graph", "anchor_path_graph",
)
METRICS = ("hit@1", "hit@10", "hit@50", "mrr", "ap")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def main() -> None:
    raw_dir = RESULTS_DIR / "raw_v2"
    out_dir = RESULTS_DIR / "audit_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    source = {(item.lang, item.instance_id): item for item in load_all()}
    expected_counts = Counter(lang for lang, _ in source)
    errors: list[str] = []
    rows: list[dict] = []
    artifacts = []

    for lang in LANGS:
        path = raw_dir / f"main_{lang}.jsonl"
        done_path = Path(str(path) + ".done")
        if not path.exists() or not done_path.exists():
            errors.append(f"missing raw/done artifact for {lang}")
            continue
        language_rows = [json.loads(line) for line in path.open() if line.strip()]
        done = json.load(done_path.open())
        expected_rows = expected_counts[lang] * len(MAIN_METHODS)
        if len(language_rows) != expected_rows or done.get("rows") != expected_rows:
            errors.append(f"{lang}: rows raw={len(language_rows)} done={done.get('rows')} expected={expected_rows}")
        if done.get("instances") != expected_counts[lang] or done.get("cap") != 0:
            errors.append(f"{lang}: invalid completion metadata {done}")
        if (done.get("query_protocol") != QUERY_PROTOCOL or
                done.get("candidate_protocol") != TEST_FILTER_PROTOCOL or
                done.get("metric_protocol") != METRIC_PROTOCOL or
                set(done.get("methods", [])) != set(MAIN_METHODS)):
            errors.append(f"{lang}: wrong protocol/method completion metadata")
        artifacts.append({
            "path": str(path.relative_to(path.parents[2])),
            "rows": len(language_rows),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
            "done_sha256": file_sha256(done_path),
        })
        rows.extend(language_rows)

    by_instance: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (row.get("lang"), row.get("instance_id"))
        by_instance[key].append(row)
        if key not in source:
            errors.append(f"result has unknown instance {key}")
            continue
        item = source[key]
        expected_hash = hashlib.sha256(item.query.encode()).hexdigest()
        if (row.get("query_protocol") != QUERY_PROTOCOL or
                row.get("candidate_protocol") != TEST_FILTER_PROTOCOL or
                row.get("metric_protocol") != METRIC_PROTOCOL or
                row.get("query_sha256") != expected_hash):
            errors.append(f"{key}: query protocol/hash mismatch")
        if row.get("query_source") != item.stats["query_source"]:
            errors.append(f"{key}: query source mismatch")
        if row.get("method") not in MAIN_METHODS or row.get("cfg") != METHODS.get(row.get("method")):
            errors.append(f"{key}: method/config mismatch {row.get('method')}")
        if len(row.get("top10", [])) != len(set(row.get("top10", []))):
            errors.append(f"{key}/{row.get('method')}: duplicate top10 paths")
        for metric in METRICS:
            value = row.get(metric)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                errors.append(f"{key}/{row.get('method')}: invalid {metric}={value}")

    if set(by_instance) != set(source):
        missing = sorted(set(source) - set(by_instance))
        errors.append(f"missing instances: {missing[:10]} (n={len(missing)})")
    for key, group in by_instance.items():
        methods = [row["method"] for row in group]
        if len(group) != len(MAIN_METHODS) or set(methods) != set(MAIN_METHODS) or len(methods) != len(set(methods)):
            errors.append(f"{key}: unpaired method rows {methods}")
        if len({row["query_sha256"] for row in group}) != 1:
            errors.append(f"{key}: methods used different queries")
        invariant_fields = ("n_gold_all", "n_gold_evaluable", "n_gold_excluded",
                            "no_evaluable_gold", "query_mentions_gold_path")
        for field in invariant_fields:
            if len({json.dumps(row[field], sort_keys=True) for row in group}) != 1:
                errors.append(f"{key}: method-dependent {field}")

    aggregates = {}
    for lang in (*LANGS, "ALL"):
        for method in MAIN_METHODS:
            selected = [row for row in rows if row["method"] == method and
                        (lang == "ALL" or row["lang"] == lang)]
            aggregates[f"{lang}/{method}"] = {
                "n": len(selected),
                **{metric: round(mean([row[metric] for row in selected]), 8) for metric in METRICS},
            }

    matched = {}
    for base, treatment in (
        ("bm25", "bm25_path"),
        ("bm25", "anchor_path_only"),
        ("bm25", "anchor_symbol_only"),
        ("bm25", "bm25_graph"),
        ("bm25_anchor", "bm25_anchor_graph"),
        ("anchor_path_only", "anchor_path_graph"),
    ):
        base_rows = {(row["lang"], row["instance_id"]): row for row in rows if row["method"] == base}
        treatment_rows = {(row["lang"], row["instance_id"]): row for row in rows
                          if row["method"] == treatment}
        keys = sorted(set(base_rows) & set(treatment_rows))
        matched[f"{treatment}-minus-{base}"] = {
            metric: round(mean([treatment_rows[key][metric] - base_rows[key][metric]
                                for key in keys]), 8)
            for metric in ("hit@1", "hit@10", "mrr")
        }

    cue_strata = {}
    base_rows = {(row["lang"], row["instance_id"]): row for row in rows if row["method"] == "bm25"}
    path_rows = {(row["lang"], row["instance_id"]): row for row in rows
                 if row["method"] == "anchor_path_only"}
    for cue in (False, True):
        keys = [key for key, row in base_rows.items() if bool(row["query_mentions_gold_path"]) == cue]
        cue_strata["present" if cue else "absent"] = {
            "n": len(keys),
            **{metric: round(mean([path_rows[key][metric] - base_rows[key][metric]
                                   for key in keys]), 8)
               for metric in ("hit@1", "hit@10", "mrr")},
        }

    report = {
        "status": "VERIFIED" if not errors else "FAILED",
        "errors": errors,
        "query_protocol": QUERY_PROTOCOL,
        "instances": len(by_instance),
        "rows": len(rows),
        "languages": len({row["lang"] for row in rows}),
        "repositories": len({(row["lang"], row["repo"]) for row in rows}),
        "methods": list(MAIN_METHODS),
        "artifacts": artifacts,
        "aggregates": aggregates,
        "matched_deltas": matched,
        "path_cue_strata_anchor_path_minus_bm25": cue_strata,
    }
    (out_dir / "result_integrity.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Protocol V2 Result Integrity",
        "",
        f"- Status: **{report['status']}**",
        f"- Rows: {report['rows']}",
        f"- Instances: {report['instances']}",
        f"- Languages: {report['languages']}",
        f"- Repositories: {report['repositories']}",
        f"- Errors: {len(errors)}",
        "",
        "## Independently recomputed matched deltas",
        "",
        "| Contrast | Hit@1 | Hit@10 | MRR |",
        "|---|---:|---:|---:|",
    ]
    for contrast, values in matched.items():
        lines.append(f"| {contrast} | {values['hit@1']:+.4f} | {values['hit@10']:+.4f} | {values['mrr']:+.4f} |")
    lines += [
        "",
        "## Explicit gold-path cue stratification",
        "",
        "| Cue | n | Hit@1 delta | Hit@10 delta | MRR delta |",
        "|---|---:|---:|---:|---:|",
    ]
    for cue, values in cue_strata.items():
        lines.append(f"| {cue} | {values['n']} | {values['hit@1']:+.4f} | {values['hit@10']:+.4f} | {values['mrr']:+.4f} |")
    (out_dir / "result_integrity.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "rows", "instances", "languages", "repositories")},
                     ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
