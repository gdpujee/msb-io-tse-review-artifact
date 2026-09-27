"""Download Multi-SWE-bench instance files and (optionally) repo source tarballs.

Everything is resumable: existing non-empty files are skipped.
Large repos are skipped by default (see config.SKIP_LARGE) to respect the disk budget.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RAW_DIR, SRC_DIR, HF_BASE, LANG_FILES, SKIP_LARGE, DATA_DIR, SRC_EXT  # noqa: E402

# ---------------------------------------------------------------------------
# Selective extraction.
#
# Failure F008 (2026-09-13): extracting whole commit tarballs exhausted the
# disk (ENOSPC) on fasterxml__jackson-databind, whose tarball contains ~240 MB
# of generated javadoc HTML. Those files are never used: parse_repo() only
# walks files whose extension is in SRC_EXT. We therefore extract *only*
# source files, with hard per-file / per-repo budgets so that a pathological
# repo can no longer take down the whole run.
# ---------------------------------------------------------------------------
KEEP_EXT = {e for exts in SRC_EXT.values() for e in exts}
# Safety valves only. They are set far above anything observed (largest single
# repo source tree measured so far: 8.0 MB for FasterXML/jackson-databind, whose
# 52 MB tarball is 94% javadoc HTML) so that in practice the corpus is exactly
# "every file with a source extension at the base commit" -- identical to what
# parse_repo() already sees, and therefore identical to the indexes already
# built before F008. See DECISIONS.md D004.
MAX_REPO_BYTES = 400_000_000    # refuse a repo whose source exceeds ~400 MB
MIN_FREE_BYTES = 3_000_000_000  # refuse to run with < 3 GiB free


def _free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except Exception:  # noqa: BLE001
        return -1


def _wanted(m: tarfile.TarInfo) -> bool:
    """Keep a member iff it is a source file, by extension only."""
    return m.isfile() and Path(m.name).suffix.lower() in KEEP_EXT


def stream_source(org: str, repo: str, sha: str,
                  exts: set[str] | None = None,
                  max_bytes: int = 400_000_000):
    """Stream a commit tarball from GitHub and yield (relpath, source_text).

    Nothing is written to disk. Two reasons (FAILURES.md F008 / F008b):
      1. whole-tarball extraction wasted hundreds of MB on generated files
         (javadoc HTML etc.) that parse_repo() never reads, and exhausted the
         disk;
      2. deleting thousands of extracted files tripped the sandbox bulk-delete
         guard, killing the indexing run.
    Only members whose extension is in `exts` are materialised, in memory.

    `exts` MUST be the *language's own* extension set (config.SRC_EXT[lang]),
    not the union over all languages. Using the union silently polluted the
    corpus: Python indexes picked up Django's vendored static .js (6.6% of
    files), js indexes picked up .ts (10.7%), kotlin picked up .java test
    resources (5.5%). See FAILURES F010.
    """
    exts = exts if exts is not None else KEEP_EXT
    url = f"https://github.com/{org}/{repo}/archive/{sha}.tar.gz"
    req = urllib.request.Request(url, headers={"User-Agent": "research-agent/1.0"})
    total = 0
    with urllib.request.urlopen(req, timeout=300) as r:
        with tarfile.open(fileobj=r, mode="r|gz") as tf:
            for m in tf:
                if not m.isfile():
                    continue
                if Path(m.name).suffix.lower() not in exts:
                    continue
                name = Path(m.name)
                # strip the "{repo}-{sha}/" archive root
                rel = str(Path(*name.parts[1:])) if len(name.parts) > 1 else ""
                if not rel:
                    continue
                if total + m.size > max_bytes:
                    raise RuntimeError(
                        f"{org}/{repo}: source exceeds {max_bytes / 1e6:.0f} MB budget")
                total += m.size
                f = tf.extractfile(m)
                if f is None:
                    continue
                yield rel, f.read()


def _download(url: str, dest: Path, timeout: int = 300) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "research-agent/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(dest)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ! failed {url}: {e}")
        if tmp.exists():
            tmp.unlink()
        return False


def fetch_instances(langs: list[str] | None = None, include_large: bool = False) -> int:
    langs = langs or list(LANG_FILES)
    n = 0
    for lang in langs:
        for fn in LANG_FILES.get(lang, []):
            key = f"{lang}/{fn}"
            if not include_large and key in SKIP_LARGE:
                print(f"  - skip (large): {key} [{SKIP_LARGE[key]} MB]")
                continue
            dest = RAW_DIR / f"{lang}__{fn}"
            if _download(f"{HF_BASE}/{lang}/{fn}", dest):
                n += 1
    return n


def fetch_source(org: str, repo: str, sha: str, dest_dir: Path) -> Path | None:
    """Download and extract a single commit tarball; returns extracted root dir.

    dest_dir must not exist yet (or be empty). The tarball is removed right
    after extraction to keep disk usage bounded.
    """
    if dest_dir.exists() and any(dest_dir.iterdir()):
        return dest_dir
    free = _free_bytes(dest_dir.parent)
    if 0 <= free < MIN_FREE_BYTES:
        print(f"  ! low disk ({free / 1e9:.1f} GiB free), refusing to download")
        return None
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    tgz = dest_dir.parent / f"{dest_dir.name}.tar.gz"
    tmp_extract = dest_dir.parent / f"{dest_dir.name}__x"
    shutil.rmtree(tmp_extract, ignore_errors=True)
    url = f"https://github.com/{org}/{repo}/archive/{sha}.tar.gz"
    if not _download(url, tgz, timeout=300):
        return None
    try:
        tmp_extract.mkdir(parents=True, exist_ok=True)
        total = 0
        with tarfile.open(tgz) as tf:
            members = []
            for m in tf.getmembers():
                if m.name.startswith("/") or ".." in Path(m.name).parts:
                    continue  # path-traversal guard for untrusted tarballs
                if not _wanted(m):
                    continue
                if total + m.size > MAX_REPO_BYTES:
                    print(f"  ! {org}/{repo}: source exceeds "
                          f"{MAX_REPO_BYTES / 1e6:.0f} MB budget, skipped")
                    return None
                total += m.size
                members.append(m)
            tf.extractall(tmp_extract, members=members)
        subs = [p for p in tmp_extract.iterdir() if p.is_dir()]
        if not subs:
            subs = [p for p in tmp_extract.iterdir() if p.is_file()]
            if not subs:
                print(f"  ! {org}/{repo}: no source files found")
                return None
            tmp_extract.rename(dest_dir)
            return dest_dir
        shutil.move(str(subs[0]), str(dest_dir))
        shutil.rmtree(tmp_extract, ignore_errors=True)
        return dest_dir
    except Exception as e:  # noqa: BLE001
        print(f"  ! extract failed {tgz}: {e}")
        shutil.rmtree(dest_dir, ignore_errors=True)
        return None
    finally:
        if tgz.exists():
            tgz.unlink()
        shutil.rmtree(tmp_extract, ignore_errors=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="*", default=None)
    ap.add_argument("--include-large", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    n = fetch_instances(args.langs, args.include_large)
    total = sum(p.stat().st_size for p in RAW_DIR.glob("*.jsonl"))
    print(f"downloaded/verified {n} files, {total/1e6:.1f} MB total, in {time.time()-t0:.1f}s")
