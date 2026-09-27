#!/usr/bin/env python3
"""Build the reproduction package for this paper, deterministically.

Why deterministic
-----------------
``zipfile`` stamps every entry with the wall-clock time and records the host OS,
so two builds of the same inputs normally differ.  This builder pins the entry
timestamp to a fixed epoch, forces the create system, sorts the entry order, and
fixes the deflate level.  The result is that the same working tree always yields
the same archive bytes, which is what makes the printed digest a checkable claim
rather than a snapshot of when the build happened.

The archive must be a function of what it ships, and of nothing else
-------------------------------------------------------------------
An earlier revision of this builder also embedded a live inventory of the
*excluded* trees -- file counts and byte sizes, read off the filesystem.  One of
those trees is ``.git``, which changes on every commit, so the archive digest was
a function of version-control scratch state and could never be reproduced from a
given source tree.  The ``--verify`` mode could not catch it: it built twice back
to back, so both builds saw the same ``.git`` and agreed with each other.  A gate
that cannot fail is not a gate.  See FAILURES.md F030.

Two consequences are now structural rather than commented:
  * the archive carries the exclusion *policy* (which trees, and why) and never
    live sizes of those trees; the sizes are printed to the console instead;
  * ``--verify`` takes its second build with a sentinel file present in an
    excluded tree, so it tests independence from scratch state rather than
    merely repeating itself.

What is included, and what is only declared
-------------------------------------------
Included with content and per-file SHA-256:
  code (``experiments/``, ``tests/``), the manuscript, the released benchmark
  (``benchmark/``), the verified result families (``results/raw_v2/``,
  ``results/tables_v2/``, ``results/audit_v2/``, ``results/figures/``), the
  environment record, the review records, and the top-level control documents.

Declared excluded, never hashed:
  ``data/`` (upstream rows and repository indexes; fetched by script),
  ``.hf_cache/`` (model weights), and every invalidated result family, which is
  retained on disk as failure evidence but must not travel as if it were a
  result.  The archive records why each is out; it does not record how big each
  is now, because that number is not reproducible.

Usage
-----
    python experiments/build_artifact.py                 # writes reproduction_package.zip
    python experiments/build_artifact.py --verify        # rebuild and compare digests
    python experiments/build_artifact.py --check         # is the committed package stale?

The archive must not quote its own digest
-----------------------------------------
A document that travels inside the archive and quotes the archive's sha256 makes
that digest unverifiable: editing the quoted value changes the archive, and hence
the digest.  The digest therefore belongs in the commit message, which is outside
the archive, and ``--check`` answers the companion question: does the manifest on
disk still describe the files on disk?  A file edited after the last build means
the shipped archive is one revision behind, which is a silent defect unless it is
checked for.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reproduction_package.zip"
MANIFEST = ROOT / "ARTIFACT_MANIFEST.sha256"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)

INCLUDE_DIRS = (
    "experiments", "tests", "paper", "benchmark",
    "results/raw_v2", "results/tables_v2", "results/audit_v2", "results/figures",
    # The two treatment arms of the query-provenance contrast.  Their rows carry
    # the superseded protocol identifier and are excluded from every V2
    # aggregate, but they are shipped because the contrast is only checkable if
    # the rows that produced it are present.  collect() skips a directory that
    # does not exist, so the dense arm is included only once it has run.
    "results/contrast_leaky_v1", "results/contrast_leaky_dense_v1",
    "env", "review", "notes", "literature",
)

# Retained on disk as evidence, deliberately not shipped as content.  The archive
# carries this declaration -- path plus reason -- and nothing about how large
# these trees currently are; see the module docstring.
EXCLUSIONS: tuple[tuple[str, str], ...] = (
    ("data", "upstream rows and repository indexes; fetched by script"),
    (".hf_cache", "model weights; re-downloaded, not redistributed"),
    (".git", "version-control machinery, not paper evidence"),
    ("results/raw", "Protocol V1 output; superseded and CONTAMINATED"),
    ("results/tables", "Protocol V1 tables; superseded"),
    ("results/processed", "Protocol V1 intermediate; superseded"),
    ("results/raw_v2_pre_testfilter", "V2 rows from before the v6 test filter; invalid"),
    ("results/tables_v2_pre_testfilter", "tables derived from those invalid rows"),
    ("results/tables_v2_pilot", "pilot run; superseded by the full V2 run"),
    ("results/raw_v2_component_filter_v2_invalid", "v2 filter rule; invalid, kept as failure evidence"),
    ("results/raw_v2_filter_iteration_mixed_invalid_2", "mixed-protocol iteration; invalid"),
    ("results/raw_v2_metric_protocol_v1_invalid", "metric-protocol v1 rows; invalid"),
    ("results/logs_v2", "run logs of the invalidated filter iteration"),
    ("results/logs_v2_filter_iteration_mixed_invalid_2", "run logs of the invalidated iteration"),
    ("results/logs_v2_pre_filter_v3_mixed", "run logs from before the v3 filter"),
)

SKIP_SUFFIX = (".pyc", ".DS_Store", ".zip")
SKIP_PARTS = ("__pycache__", ".ipynb_checkpoints")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def collect() -> list[Path]:
    files: list[Path] = []
    for name in sorted(p.name for p in ROOT.iterdir() if p.is_file()):
        if (name.endswith((".md", ".txt")) or name == "LICENSE") and name != MANIFEST.name:
            files.append(ROOT / name)
    for rel in INCLUDE_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if rel == "paper" and path.name != "manuscript_ESE_v2.md":
                # The cover letter is for the editor; V1 and draft manuscripts
                # are preserved in Git but are not part of this release.
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.name.endswith(SKIP_SUFFIX):
                continue
            files.append(path)
    return sorted(set(files))


def exclusion_report() -> list[dict]:
    """Live size of the excluded trees, for the console only.

    Deliberately NOT written into the archive.  These are mutable areas -- ``.git``
    changes on every commit, ``data/`` and ``.hf_cache/`` are fetched -- so a
    snapshot of their size is not reproducible and has no business inside a
    content-addressed artifact.
    """
    rows = []
    for rel, reason in EXCLUSIONS:
        base = ROOT / rel
        if not base.is_dir():
            continue
        count = 0
        total = 0
        for path in base.rglob("*"):
            if path.is_file():
                count += 1
                total += path.stat().st_size
        rows.append({"path": rel, "reason": reason, "files": count, "bytes": total})
    return rows


def check_stale() -> int:
    """Report whether the manifest on disk still describes the working tree.

    The manifest and the archive are committed together, so a file that changed
    after the last build means the shipped archive is one revision behind.  That
    is the defect this check exists for.  Read-only: it never rebuilds anything.
    """
    if not MANIFEST.exists():
        print(f"NO MANIFEST: {MANIFEST.name} is absent, so the package cannot be checked")
        return 1

    recorded: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            sha, name = line.split("  ", 1)
            recorded[name] = sha

    current = {
        path.relative_to(ROOT).as_posix(): digest(path.read_bytes())
        for path in collect()
    }

    changed = sorted(n for n in recorded.keys() & current.keys() if recorded[n] != current[n])
    added = sorted(current.keys() - recorded.keys())
    removed = sorted(recorded.keys() - current.keys())
    for label, names in (
        ("changed since the last build", changed),
        ("in the tree but not in the package", added),
        ("in the package but missing from the tree", removed),
    ):
        for name in names:
            print(f"  {label}: {name}")

    if changed or added or removed:
        print(f"STALE: {len(changed)} changed, {len(added)} added, {len(removed)} removed "
              f"since {MANIFEST.name} was written; rebuild before committing")
        return 1
    print(f"CLEAN: all {len(current)} packaged files match {MANIFEST.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true",
                        help="rebuild and confirm the archive bytes are reproducible")
    parser.add_argument("--check", action="store_true",
                        help="read-only: report files that changed since the package was built")
    args = parser.parse_args()

    if args.check:
        return check_stale()

    files = collect()
    entries = []
    for path in files:
        payload = path.read_bytes()
        entries.append((path.relative_to(ROOT).as_posix(), payload, digest(payload)))

    manifest_lines = [f"{sha}  {name}" for name, _, sha in entries]
    manifest_text = "\n".join(manifest_lines) + "\n"
    policy_text = json.dumps(
        [{"path": rel, "reason": reason} for rel, reason in EXCLUSIONS], indent=1
    ) + "\n"

    def build(target: Path) -> str:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, payload, _ in entries:
                info = zipfile.ZipInfo(filename=name, date_time=FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0o644 << 16
                archive.writestr(info, payload, compresslevel=9)
            info = zipfile.ZipInfo(filename="ARTIFACT_MANIFEST.sha256", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0o644 << 16
            archive.writestr(info, manifest_text, compresslevel=9)
            info = zipfile.ZipInfo(filename="ARTIFACT_EXCLUSIONS.json", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0o644 << 16
            archive.writestr(info, policy_text, compresslevel=9)
        return digest(target.read_bytes())

    def verify() -> int:
        """Prove the archive does not depend on excluded scratch state.

        Building twice back to back proves almost nothing: both builds see the same
        filesystem, so a builder that hashes mutable scratch state still agrees with
        itself.  That is exactly how F030 stayed invisible.  So the middle build is
        taken with a sentinel file present in an excluded tree, and the last build
        confirms removing it restores the bytes.
        """
        first = build(OUT)
        probe_dir = next((ROOT / rel for rel, _ in EXCLUSIONS if (ROOT / rel).is_dir()), ROOT)
        probe = probe_dir / ".reproducibility_probe"
        probe.write_bytes(b"probe\n")
        try:
            with_probe = build(OUT)
        finally:
            probe.unlink(missing_ok=True)
        after = build(OUT)

        rel = probe_dir.relative_to(ROOT).as_posix() or "."
        problems = []
        if with_probe != first:
            problems.append(
                f"a sentinel file in {rel} changed the archive:\n"
                f"      without probe: {first}\n"
                f"      with probe   : {with_probe}"
            )
        if after != first:
            problems.append(
                f"removing the sentinel did not restore the archive:\n"
                f"      before: {first}\n"
                f"      after : {after}"
            )
        if problems:
            print("NOT REPRODUCIBLE -- the archive depends on excluded scratch state")
            for p in problems:
                print("  " + p)
            return 1
        print(f"VERIFIED: identical bytes across three builds, one of them with a probe "
              f"file in {rel} ({first})")
        return 0

    first = build(OUT)
    MANIFEST.write_text(manifest_text, encoding="utf-8")

    print(f"files included : {len(entries)}")
    print(f"bytes on disk  : {sum(len(p) for _, p, _ in entries):,}")
    print(f"archive bytes  : {OUT.stat().st_size:,}")
    print(f"archive sha256 : {first}")
    print("excluded trees (live sizes -- a console report, NOT archive content):")
    for row in exclusion_report():
        print(f"  {row['path']:52s} {row['files']:6d} files  {row['bytes'] / 1e6:9.1f} MB"
              f"  {row['reason']}")
    print("note: the archive carries the exclusion *policy*, not these sizes, so its "
          "bytes stay a function of what it ships")

    if args.verify:
        return verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
