"""Audit dataset provenance, query leakage, index alignment, and path cues."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import INDEX_DIR, LANG_FILES, RAW_DIR, RESULTS_DIR  # noqa: E402
from dataset import QUERY_PROTOCOL, TEST_FILTER_PROTOCOL, load_all  # noqa: E402
from methods import extract_path_candidates  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    out_dir = RESULTS_DIR / "audit_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    instances = load_all()
    by_lang = Counter(instance.lang for instance in instances)
    repos: dict[str, set[str]] = defaultdict(set)
    source_counts: dict[str, Counter] = defaultdict(Counter)
    path_cues = Counter()
    empty_queries: list[str] = []
    no_gold: list[str] = []
    duplicate_ids: list[str] = []
    seen: set[tuple[str, str]] = set()

    for instance in instances:
        key = (instance.lang, instance.instance_id)
        if key in seen:
            duplicate_ids.append(f"{instance.lang}/{instance.instance_id}")
        seen.add(key)
        repos[instance.lang].add(f"{instance.org}/{instance.repo}")
        source_counts[instance.lang][instance.stats["query_source"]] += 1
        if not instance.query:
            empty_queries.append(f"{instance.lang}/{instance.instance_id}")
        if not instance.gold_files_nontest:
            no_gold.append(f"{instance.lang}/{instance.instance_id}")
        mentioned = {item.lower() for item in extract_path_candidates(instance.query)}
        if any(gold.lower() in mentioned or Path(gold).name.lower() in mentioned
               for gold in instance.gold_files_nontest):
            path_cues[instance.lang] += 1

    raw_files = []
    for lang, names in LANG_FILES.items():
        for name in names:
            path = RAW_DIR / f"{lang}__{name}"
            if not path.exists():
                continue
            rows = sum(1 for line in path.open(encoding="utf-8") if line.strip())
            raw_files.append({
                "path": str(path.relative_to(RAW_DIR.parent.parent)),
                "lang": lang,
                "rows": rows,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })

    index_counts = {
        lang: len(list((INDEX_DIR / lang).glob("*.json.gz")))
        for lang in sorted(by_lang)
    }
    index_protocol_samples = {}
    for lang in sorted(by_lang):
        samples = sorted((INDEX_DIR / lang).glob("*.json.gz"))[:1]
        for path in samples:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                doc = json.load(handle)
            index_protocol_samples[lang] = {
                "file": path.name,
                "stored_protocol": doc.get("stats_query", {}).get("query_protocol", "legacy_v1"),
            }

    report = {
        "status": "VERIFIED" if not empty_queries and not duplicate_ids else "FAILED",
        "query_protocol": QUERY_PROTOCOL,
        "candidate_protocol": TEST_FILTER_PROTOCOL,
        "query_policy": {
            "allowed": ["problem_statement", "resolved_issues[].title", "resolved_issues[].body"],
            "forbidden": ["top-level title", "top-level body", "hints", "hints_text"],
        },
        "n_instances": len(instances),
        "n_repositories": len({repo for values in repos.values() for repo in values}),
        "per_language": {
            lang: {
                "instances": by_lang[lang],
                "repositories": len(repos[lang]),
                "query_sources": dict(source_counts[lang]),
                "gold_path_cue_instances": path_cues[lang],
                "gold_path_cue_fraction": round(path_cues[lang] / by_lang[lang], 6),
                "index_files": index_counts[lang],
            }
            for lang in sorted(by_lang)
        },
        "empty_queries": empty_queries,
        "instances_without_non_test_gold": no_gold,
        "duplicate_instance_ids": duplicate_ids,
        "legacy_index_query_samples": index_protocol_samples,
        "index_query_handling": (
            "run_experiment.py replaces legacy stored queries from authoritative raw rows; "
            "legacy query text is never used by protocol V2"
        ),
        "raw_files": raw_files,
    }
    json_path = out_dir / "protocol_audit.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Protocol V2 Audit",
        "",
        f"- Status: **{report['status']}**",
        f"- Query protocol: `{QUERY_PROTOCOL}`",
        f"- Instances: {len(instances)}",
        f"- Repositories: {report['n_repositories']}",
        f"- Empty queries: {len(empty_queries)}",
        f"- Duplicate language/instance IDs: {len(duplicate_ids)}",
        "",
        "| Language | Instances | Repositories | Query source | Gold-path cue n (%) | Index files |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for lang, values in report["per_language"].items():
        sources = ", ".join(f"{key}={value}" for key, value in values["query_sources"].items())
        lines.append(
            f"| {lang} | {values['instances']} | {values['repositories']} | {sources} | "
            f"{values['gold_path_cue_instances']} ({100 * values['gold_path_cue_fraction']:.1f}%) | "
            f"{values['index_files']} |"
        )
    lines += [
        "",
        "Top-level PR title/body and hint fields are forbidden by construction and tested in",
        "`tests/test_protocol_v2.py`. Existing repository indexes contain legacy V1 query text,",
        "but the V2 runner replaces it from the raw dataset and refuses missing or empty V2 queries.",
        "",
        "The JSON companion contains SHA-256 checksums for every raw dataset file.",
    ]
    (out_dir / "protocol_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "query_protocol", "n_instances", "n_repositories")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
