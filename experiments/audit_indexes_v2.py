#!/usr/bin/env python3
"""Verify every repository index against its authoritative benchmark row."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from config import INDEX_DIR, SRC_EXT  # noqa: E402
from dataset import load_all  # noqa: E402
from pipeline import MAX_FILE_CHARS  # noqa: E402

OUT = ROOT / "results" / "audit_v2" / "index_audit.json"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    sources = {(row.lang, row.instance_id): row for row in load_all()}
    paths = sorted(INDEX_DIR.glob("*/*.json.gz"))
    records = []
    errors: list[str] = []
    observed: set[tuple[str, str]] = set()
    for number, path in enumerate(paths, 1):
        lang = path.parent.name
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            doc = json.load(stream)
        key = (lang, doc.get("instance_id"))
        if key in observed:
            errors.append(f"duplicate index key {key}")
        observed.add(key)
        source = sources.get(key)
        if source is None:
            errors.append(f"unknown index {key}")
            continue
        expected = {
            "lang": source.lang, "org": source.org, "repo": source.repo,
            "sha": source.base_sha, "instance_id": source.instance_id,
        }
        for field, value in expected.items():
            if doc.get(field) != value:
                errors.append(f"{key}: {field}={doc.get(field)!r}, expected {value!r}")
        files = doc.get("files", [])
        file_paths = [item.get("path") for item in files]
        if doc.get("n_files") != len(files):
            errors.append(f"{key}: n_files mismatch")
        if len(file_paths) != len(set(file_paths)):
            errors.append(f"{key}: duplicate source paths")
        bad_ext = [name for name in file_paths if Path(name or "").suffix.lower() not in SRC_EXT[lang]]
        if bad_ext:
            errors.append(f"{key}: foreign extensions {bad_ext[:3]}")
        too_long = [item.get("path") for item in files if len(item.get("text", "")) > MAX_FILE_CHARS]
        if too_long:
            errors.append(f"{key}: text over truncation bound {too_long[:3]}")
        records.append({
            "path": str(path.relative_to(ROOT)), "lang": lang,
            "instance_id": source.instance_id, "repo": f"{source.org}/{source.repo}",
            "base_commit": source.base_sha, "n_files": len(files),
            "bytes": path.stat().st_size, "sha256": sha256(path),
        })
        if number % 100 == 0:
            print(f"[{number}/{len(paths)}]", flush=True)

    missing = sorted(set(sources) - observed)
    if missing:
        errors.append(f"missing indexes: {missing[:10]} (n={len(missing)})")
    report = {
        "status": "VERIFIED" if not errors else "FAILED",
        "indexes": len(records), "expected_instances": len(sources),
        "languages": dict(Counter(item["lang"] for item in records)),
        "total_compressed_bytes": sum(item["bytes"] for item in records),
        "checks": [
            "language/instance set equals authoritative raw rows",
            "org, repository, and base commit equal authoritative raw row",
            "source paths are unique and use only the configured language extensions",
            "stored text obeys the 60,000-character truncation bound",
            "each compressed index has a SHA-256 digest",
        ],
        "errors": errors, "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "status", "indexes", "expected_instances", "languages", "total_compressed_bytes")}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
