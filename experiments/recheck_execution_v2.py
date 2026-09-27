"""Deterministic execution re-check on two fixed instances per language."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import INDEX_DIR, RESULTS_DIR  # noqa: E402
from dataset import load_all  # noqa: E402
from run_experiment import METHODS, eval_instance, load_index, rank_with  # noqa: E402
from verify_results_v2 import LANGS, MAIN_METHODS  # noqa: E402


def main() -> None:
    out_dir = RESULTS_DIR / "audit_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = {(item.lang, item.instance_id): item for item in load_all()}
    errors: list[str] = []
    checked = []
    for lang in LANGS:
        result_path = RESULTS_DIR / "raw_v2" / f"main_{lang}.jsonl"
        stored_rows = [json.loads(line) for line in result_path.open() if line.strip()]
        by_id = {}
        for row in stored_rows:
            by_id.setdefault(row["instance_id"], {})[row["method"]] = row
        selected = sorted(by_id)
        selected = [selected[0], selected[-1]] if len(selected) > 1 else selected
        for instance_id in selected:
            index_path = INDEX_DIR / lang / f"{instance_id}.json.gz"
            doc = load_index(index_path)
            source = sources[(lang, instance_id)]
            doc["query"] = source.query
            doc["stats_query"] = source.stats
            doc["gold_files"] = source.gold_files
            doc["test_files"] = source.test_files
            sym_cache = {}
            for method in MAIN_METHODS:
                ranked, candidates, _ = rank_with(doc, METHODS[method], True, sym_cache)
                metrics, _ = eval_instance(doc, ranked, candidates)
                stored = by_id[instance_id][method]
                observed = {
                    "top10": ranked[:10],
                    "hit@1": metrics.hit_at[1],
                    "hit@10": metrics.hit_at[10],
                    "mrr": metrics.mrr,
                    "ap": metrics.ap,
                }
                expected = {key: stored[key] for key in observed}
                if observed != expected:
                    errors.append(f"{lang}/{instance_id}/{method}: {observed} != {expected}")
            checked.append({"lang": lang, "instance_id": instance_id,
                            "methods": len(MAIN_METHODS), "status": "VERIFIED"})
    report = {
        "status": "VERIFIED" if not errors else "FAILED",
        "selection": "lexicographically first and last indexed instance per language",
        "instances_reexecuted": len(checked),
        "method_instance_runs": len(checked) * len(MAIN_METHODS),
        "errors": errors,
        "checked": checked,
    }
    (out_dir / "execution_recheck.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Protocol V2 Execution Re-check",
        "",
        f"- Status: **{report['status']}**",
        f"- Instances re-executed: {report['instances_reexecuted']}",
        f"- Method-instance runs: {report['method_instance_runs']}",
        f"- Mismatches: {len(errors)}",
        "",
        "Selection is fixed before execution: lexicographically first and last instance in each language.",
        "Every rerun must exactly match stored Top-10, Hit@1, Hit@10, MRR, and AP.",
    ]
    (out_dir / "execution_recheck.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("status", "instances_reexecuted", "method_instance_runs")}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
