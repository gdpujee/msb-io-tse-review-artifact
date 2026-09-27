#!/usr/bin/env python3
"""Audit the final test-path predicate over every saved index and gold path."""
from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from config import INDEX_DIR, TEST_PATH_HINTS  # noqa: E402
from dataset import TEST_FILTER_PROTOCOL, _looks_test, load_all  # noqa: E402


def legacy_filter(path: str) -> bool:
    """The superseded predicate, retained only for audit comparison."""
    low = path.lower()
    parts = set(low.replace("\\", "/").split("/"))
    return any(
        hint in parts or f"/{hint}" in low or low.endswith(f"_{hint}.py")
        for hint in TEST_PATH_HINTS
    ) or low.endswith(("Test.java", "Test.kt"))


POSITIVE_CASES = (
    "app/src/androidTest/java/FooTest.java",
    "module/src/integration-test/java/Foo.java",
    "analyzer/src/funTest/kotlin/AnalyzerFunTest.kt",
    "crates/clap_test/src/lib.rs",
    "src/widget.spec.tsx",
    "grep-searcher/src/testutil.rs",
    "programs/bench.c",
    "interop/test_utils.go",
    "projects/XCode/OCTest/OCTest/TestObj.h",
    "astropy/nddata/_testing.py",
)
NEGATIVE_CASES = (
    "src/main/java/Latest.java",
    "src/contest/results.py",
    "astropy/coordinates/spectral_coordinate.py",
    "src/specialized/specification.py",
    "detekt-core/src/main/ProcessingSpecSettingsBridge.kt",
    "include/internal/catch_test_spec.cpp",
    "src/_pytest/unittest.py",
)


def main() -> None:
    counts: Counter = Counter()
    unique: dict[tuple[str, str], set[str]] = defaultdict(set)
    samples: dict[tuple[str, str], list[str]] = defaultdict(list)
    all_test_fallbacks: list[str] = []

    for index_path in sorted(INDEX_DIR.rglob("*.json.gz")):
        lang = index_path.parent.name
        with gzip.open(index_path, "rt", encoding="utf-8") as stream:
            doc = json.load(stream)
        current_non_test = 0
        for file_doc in doc["files"]:
            path = file_doc["path"]
            old, new = legacy_filter(path), _looks_test(path, TEST_PATH_HINTS)
            current_non_test += int(not new)
            relation = "newly_excluded" if new and not old else "newly_included" if old and not new else None
            if relation:
                key = relation, lang
                counts[key] += 1
                is_new = path not in unique[key]
                unique[key].add(path)
                if is_new and len(samples[key]) < 20:
                    samples[key].append(path)
        if doc["files"] and current_non_test == 0:
            all_test_fallbacks.append(str(index_path.relative_to(ROOT)))

    gold_counts: Counter = Counter()
    gold_samples: dict[tuple[str, str], list[str]] = defaultdict(list)
    for instance in load_all():
        gold = set(instance.gold_files) - set(instance.test_files)
        for path in gold:
            old, new = legacy_filter(path), _looks_test(path, TEST_PATH_HINTS)
            relation = "newly_excluded" if new and not old else "newly_included" if old and not new else None
            if relation:
                key = relation, instance.lang
                gold_counts[key] += 1
                if len(gold_samples[key]) < 20:
                    gold_samples[key].append(f"{instance.instance_id}:{path}")

    positive_failures = [path for path in POSITIVE_CASES if not _looks_test(path, TEST_PATH_HINTS)]
    negative_failures = [path for path in NEGATIVE_CASES if _looks_test(path, TEST_PATH_HINTS)]
    status = "VERIFIED" if not positive_failures and not negative_failures and not all_test_fallbacks else "FAILED"

    def nested(source: Counter, sample_source=None) -> dict:
        out: dict[str, dict] = {}
        for relation, lang in sorted(source):
            out.setdefault(relation, {})[lang] = {
                "occurrences": source[(relation, lang)],
            }
            if sample_source is None:
                out[relation][lang]["unique_paths"] = len(unique[(relation, lang)])
                out[relation][lang]["samples"] = sorted(set(samples[(relation, lang)]))
            else:
                out[relation][lang]["samples"] = sorted(set(sample_source[(relation, lang)]))
        return out

    report = {
        "status": status,
        "candidate_protocol": TEST_FILTER_PROTOCOL,
        "index_files_scanned": sum(1 for _ in INDEX_DIR.rglob("*.json.gz")),
        "positive_cases": list(POSITIVE_CASES),
        "negative_cases": list(NEGATIVE_CASES),
        "positive_failures": positive_failures,
        "negative_failures": negative_failures,
        "all_test_candidate_fallbacks": all_test_fallbacks,
        "candidate_differences_from_legacy": nested(counts),
        "gold_differences_from_legacy": nested(gold_counts, gold_samples),
        "note": "Legacy comparison quantifies protocol change; manual semantic review is still required for heuristic labels.",
    }
    out_dir = ROOT / "results" / "audit_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "test_filter_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "status": status,
        "candidate_protocol": TEST_FILTER_PROTOCOL,
        "index_files_scanned": report["index_files_scanned"],
        "positive_failures": positive_failures,
        "negative_failures": negative_failures,
        "all_test_candidate_fallbacks": len(all_test_fallbacks),
        "candidate_differences_from_legacy": report["candidate_differences_from_legacy"],
        "gold_differences_from_legacy": report["gold_differences_from_legacy"],
    }, indent=2))
    if status != "VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
