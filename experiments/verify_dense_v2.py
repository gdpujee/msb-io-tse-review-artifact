#!/usr/bin/env python3
"""Independent integrity and aggregate check for the dense reranker output."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from dataset import QUERY_PROTOCOL, TEST_FILTER_PROTOCOL, load_all  # noqa: E402
from evaluate import METRIC_PROTOCOL  # noqa: E402
from run_dense_reranker_v2 import (  # noqa: E402
    METHOD, MODEL_ID, MODEL_REVISION, REMOTE_CODE_REVISION,
)

RAW = ROOT / "results" / "raw_v2" / "swerank_all.jsonl"
DONE = Path(str(RAW) + ".done")
OUT = ROOT / "results" / "audit_v2" / "dense_verification.json"
METRICS = ("hit@1", "hit@10", "hit@50", "mrr", "ap")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def mean(rows: list[dict], key: str) -> float:
    return sum(row[key] for row in rows) / len(rows)


def main() -> None:
    errors: list[str] = []
    if not RAW.exists() or not DONE.exists():
        raise SystemExit("dense raw result or completion marker is missing")
    rows = [json.loads(line) for line in RAW.open() if line.strip()]
    done = json.loads(DONE.read_text())
    source = {(item.lang, item.instance_id): item for item in load_all()}
    keys = [(row.get("lang"), row.get("instance_id")) for row in rows]
    if len(rows) != 1791 or done.get("rows") != 1791 or done.get("instances") != 1791:
        errors.append(f"incomplete rows: raw={len(rows)} marker={done.get('rows')}")
    if len(keys) != len(set(keys)):
        errors.append("duplicate language/instance keys")
    if set(keys) != set(source):
        errors.append(f"instance-set mismatch: dense={len(set(keys))} source={len(source)}")
    expected_marker = {
        "status": "complete", "method": METHOD, "query_protocol": QUERY_PROTOCOL,
        "candidate_protocol": TEST_FILTER_PROTOCOL,
        "metric_protocol": METRIC_PROTOCOL,
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "remote_code_revision": REMOTE_CODE_REVISION, "candidate_k": 50,
        "max_seq_length": 512, "limit": 0, "cap": 0,
    }
    for field, expected in expected_marker.items():
        if done.get(field) != expected:
            errors.append(f"marker {field}: {done.get(field)!r} != {expected!r}")

    bm25: dict[tuple[str, str], dict] = {}
    for path in sorted((ROOT / "results" / "raw_v2").glob("main_*.jsonl")):
        for line in path.open():
            row = json.loads(line)
            if row["method"] == "bm25":
                bm25[(row["lang"], row["instance_id"])] = row

    for row, key in zip(rows, keys):
        if key not in source or key not in bm25:
            continue
        expected_hash = hashlib.sha256(source[key].query.encode()).hexdigest()
        fixed = {
            "method": METHOD, "query_protocol": QUERY_PROTOCOL,
            "candidate_protocol": TEST_FILTER_PROTOCOL,
            "metric_protocol": METRIC_PROTOCOL,
            "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
            "remote_code_revision": REMOTE_CODE_REVISION, "candidate_k": 50,
            "max_seq_length": 512,
        }
        for field, expected in fixed.items():
            if row.get(field) != expected:
                errors.append(f"{key}: {field} mismatch")
        if row.get("query_sha256") != expected_hash:
            errors.append(f"{key}: query hash mismatch")
        if len(row.get("top10", [])) != len(set(row.get("top10", []))):
            errors.append(f"{key}: duplicate Top-10 path")
        for metric in METRICS:
            value = row.get(metric)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                errors.append(f"{key}: invalid {metric}={value!r}")
        for field in ("n_gold_all", "n_gold_evaluable", "n_gold_excluded",
                      "no_evaluable_gold", "query_mentions_gold_path"):
            if row.get(field) != bm25[key].get(field):
                errors.append(f"{key}: method-invariant {field} differs from BM25")

    aggregates = {
        metric: round(mean(rows, metric), 8) for metric in METRICS
    }
    deltas = {
        metric: round(mean(rows, metric) - mean(list(bm25.values()), metric), 8)
        for metric in METRICS
    }
    report = {
        "status": "VERIFIED" if not errors else "FAILED",
        "rows": len(rows),
        "languages": dict(Counter(row["lang"] for row in rows)),
        "raw_sha256": digest(RAW),
        "done_sha256": digest(DONE),
        "aggregates": aggregates,
        "delta_vs_bm25": deltas,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "rows", "aggregates", "delta_vs_bm25")},
                     indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
