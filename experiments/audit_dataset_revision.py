#!/usr/bin/env python3
"""Pin and verify the exact Hugging Face dataset revision used locally."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from config import HF_DATASET_REVISION, LANG_FILES, RAW_DIR, SKIP_LARGE  # noqa: E402

DATASET_ID = "ByteDance-Seed/Multi-SWE-bench"
API_URL = f"https://huggingface.co/api/datasets/{DATASET_ID}"
OUT_DIR = ROOT / "results" / "audit_v2"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_blob_sha1(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def upstream_tree(revision: str) -> dict[str, dict]:
    """Read file object IDs from the Hub API, including true LFS SHA-256 OIDs."""
    base = f"https://huggingface.co/api/datasets/{DATASET_ID}/tree/{revision}"
    url = base + "?recursive=true&expand=true&limit=100"
    items: list[dict] = []
    while url:
        request = urllib.request.Request(url, headers={"User-Agent": "research-audit/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            items.extend(json.load(response))
            link = response.headers.get("Link", "")
        url = ""
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split("<", 1)[1].split(">", 1)[0]
                break
    return {item["path"]: item for item in items if item.get("type") == "file"}


def main() -> None:
    with urllib.request.urlopen(API_URL, timeout=120) as response:
        upstream = json.load(response)
    revision = HF_DATASET_REVISION
    tree = upstream_tree(revision)
    files = []
    expected = []
    omitted = []

    for lang, names in LANG_FILES.items():
        for name in names:
            remote_path = f"{lang}/{name}"
            local_path = RAW_DIR / f"{lang}__{name}"
            if remote_path in SKIP_LARGE and not local_path.exists():
                omitted.append({"path": remote_path, "reason": "predeclared large-file exclusion",
                                "reported_mb": SKIP_LARGE[remote_path]})
                continue
            expected.append(remote_path)
            if not local_path.exists():
                files.append({"path": remote_path, "status": "MISSING_LOCAL"})
                continue
            item = tree.get(remote_path, {})
            lfs_oid = item.get("lfs", {}).get("oid")
            remote_etag = lfs_oid or item.get("oid", "")
            algorithm = "sha256" if lfs_oid else "git_blob_sha1"
            local_digest = sha256(local_path) if algorithm == "sha256" else git_blob_sha1(local_path)
            files.append({
                "path": remote_path,
                "local_path": str(local_path.relative_to(ROOT)),
                "bytes": local_path.stat().st_size,
                "algorithm": algorithm,
                "local_digest": local_digest,
                "remote_digest": remote_etag,
                "repo_commit": revision,
                "status": "MATCH" if local_digest == remote_etag else "MISMATCH",
            })

    counts = Counter(item["status"] for item in files)
    result = {
        "status": "VERIFIED" if counts == {"MATCH": len(files)} else "FAILED",
        "dataset_id": DATASET_ID,
        "revision": revision,
        "upstream_head_at_audit": upstream.get("sha"),
        "upstream_last_modified": upstream.get("lastModified"),
        "retrieved_api_at": datetime.now(timezone.utc).date().isoformat(),
        "upstream_card_license_tag": upstream.get("cardData", {}).get("license"),
        "local_scope": {
            "included_files": len(files),
            "omitted_files": omitted,
            "selection": "all configured files except two predeclared large-file exclusions",
        },
        "counts": dict(counts),
        "files": files,
        "notes": [
            "The snapshot extends the original seven-language release with Kotlin and Python.",
            "The local benchmark is therefore named the 9-language extended snapshot, not the original release.",
            "The dataset card uses license:other; underlying repository licenses must also be respected.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "dataset_revision.json").write_text(json.dumps(result, indent=2) + "\n")

    lines = [
        "# Dataset revision audit", "",
        f"- Status: **{result['status']}**",
        f"- Dataset: `{DATASET_ID}`",
        f"- Pinned revision: `{revision}`",
        f"- Upstream last modified: `{result['upstream_last_modified']}`",
        f"- Included files: **{len(files)}**; matched: **{counts.get('MATCH', 0)}**",
        f"- Explicitly omitted: **{len(omitted)}** (`js/sveltejs__svelte`, `ts/mui__material-ui`)",
        "- Scope name: **9-language extended snapshot (57 repositories, 1,791 instances)**",
        "- License status: dataset card is `license:other`; this audit does not relicense upstream code.",
        "", "## Omitted files", "",
    ]
    for item in omitted:
        lines.append(f"- `{item['path']}` — {item['reason']} ({item['reported_mb']} MB)")
    lines.extend(["", "## Per-file verification", "",
                  "| remote path | bytes | digest | status |", "|---|---:|---|---|"])
    for item in files:
        digest = item.get("local_digest", "-")
        lines.append(f"| `{item['path']}` | {item.get('bytes', 0)} | `{digest[:16]}…` | {item['status']} |")
    (OUT_DIR / "dataset_revision.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "revision", "counts", "local_scope")}, indent=2))
    if result["status"] != "VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
