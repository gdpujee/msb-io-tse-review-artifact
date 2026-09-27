#!/usr/bin/env python3
"""Read-only verification of the public reviewer snapshot, without downloads."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METHODS = {
    "bm25", "bm25_path", "anchor_path_only", "anchor_symbol_only",
    "bm25_anchor", "bm25_graph", "bm25_anchor_graph", "anchor_path_graph",
}
FAMILIES = (
    ("results/raw_v2", "main_*.jsonl", "issue_only_v2", 14328, METHODS),
    ("results/raw_v2", "swerank_all.jsonl", "issue_only_v2", 1791, {"bm25_swerank_rerank50"}),
    ("results/contrast_leaky_v1", "main_*.jsonl", "legacy_mixed_v1", 14328, METHODS),
    ("results/contrast_leaky_dense_v1", "swerank_all.jsonl", "legacy_mixed_v1", 1791, {"bm25_swerank_rerank50"}),
)


def check_manifest() -> int:
    entries = {}
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        sha, name = line.split("  ", 1)
        entries[name] = sha
    actual = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ROOT.rglob("*")
        if p.is_file() and p.name != "SHA256SUMS" and ".git" not in p.parts
        and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
    }
    assert entries == actual, "file inventory or SHA256SUMS mismatch"
    return len(entries)


def main() -> None:
    nfiles = check_manifest()
    queries = {}
    for line in (ROOT / "benchmark/msb_io/msb_io.jsonl").open():
        row = json.loads(line)
        key = (row["lang"], row["instance_id"])
        assert key not in queries
        assert hashlib.sha256(row["query"].encode()).hexdigest() == row["query_sha256"]
        queries[key] = row["query_sha256"]
    assert len(queries) == 1791

    legacy = json.loads((ROOT / "results/audit_v2/legacy_query_hashes.json").read_text())
    assert len(legacy) == 1791
    for directory, pattern, protocol, expected, methods in FAMILIES:
        seen = set()
        counts = Counter()
        for path in sorted((ROOT / directory).glob(pattern)):
            for line in path.open():
                row = json.loads(line)
                key = (row["lang"], row["instance_id"])
                method = row["method"]
                assert key in queries and method in methods
                assert (key, method) not in seen
                seen.add((key, method))
                counts[key] += 1
                assert row["query_protocol"] == protocol
                expected_hash = queries[key] if protocol == "issue_only_v2" else legacy[row["instance_id"]]
                assert row["query_sha256"] == expected_hash
        assert len(seen) == expected
        assert len(counts) == 1791 and set(counts.values()) == {len(methods)}
        print(f"{directory}/{pattern}: VERIFIED {len(seen)} rows; {len(counts)} instances; {protocol}")
    print(f"VERIFIED: {nfiles} manifest files; 1791 query hashes; four disjoint result families")


if __name__ == "__main__":
    main()
