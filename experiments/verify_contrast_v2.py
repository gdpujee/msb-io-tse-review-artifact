#!/usr/bin/env python3
"""Independent check that the contrast arms stay out of every Protocol V2 result.

The contrast exists to answer one question, and its rows are deliberately
produced under a query rule the paper rejects.  The risk is not that the
contrast is wrong; it is that a leaked row is quietly absorbed into a V2
aggregate, which would corrupt a published number while leaving every other
check green.  This verifier looks for exactly that, and for the structural
conditions that would make it possible.

Checks
------
1. every released row carries ``issue_only_v2`` and nothing else;
2. every contrast row carries ``legacy_mixed_v1`` and nothing else;
3. the two arms hold the expected number of rows;
4. every contrast row's ``query_sha256`` equals the audited hash of the
   superseded query for that instance, and no contrast row carries the query
   text itself;
5. no table under ``results/tables_v2/`` outside the contrast family mentions
   the treatment protocol, and every table inside that family both exists and
   names it, so the family cannot be widened to silence a real hit;
6. ``verify_results_v2.py`` reads ``results/raw_v2`` literally and does not walk
   the results tree, so it cannot reach a contrast directory.

Exit status is 0 only when every check passes.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

import audit_query_leakage as aql  # noqa: E402

RAW_DIR = ROOT / "results" / "raw_v2"
CONTRAST_DIRS = {
    ROOT / "results" / "contrast_leaky_v1": 14_328,
    ROOT / "results" / "contrast_leaky_dense_v1": 1_791,
}
TABLE_DIR = ROOT / "results" / "tables_v2"
RELEASED = "issue_only_v2"
TREATMENT = "legacy_mixed_v1"
CONTRAST_TABLES = (
    "t12_leak_contrast",
    "t13_dense_leak_contrast",
    "t14_leak_ranking",
)


def main() -> int:
    fails: list[str] = []
    audited = json.loads(aql.LEGACY_HASHES.read_text(encoding="utf-8"))

    # ---- 1 and 3: the released arm ---------------------------------------
    released_rows = 0
    for path in sorted(glob.glob(str(RAW_DIR / "*.jsonl"))):
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            released_rows += 1
            if row.get("query_protocol") != RELEASED:
                fails.append(f"{Path(path).name}: released row carries "
                             f"{row.get('query_protocol')!r}")
    expected_released = sum(CONTRAST_DIRS.values())
    if released_rows != expected_released:
        fails.append(f"released arm holds {released_rows} rows, expected "
                     f"{expected_released} (the lexical and dense released arms together)")

    # ---- 2, 3 and 4: the contrast arms -----------------------------------
    for directory, expected in CONTRAST_DIRS.items():
        rows = 0
        for path in sorted(glob.glob(str(directory / "*.jsonl"))):
            for line in Path(path).read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                rows += 1
                if row.get("query_protocol") != TREATMENT:
                    fails.append(f"{Path(path).name}: contrast row carries "
                                 f"{row.get('query_protocol')!r}")
                recorded = row.get("query_sha256")
                want = audited.get(row["instance_id"])
                if want is None:
                    fails.append(f"{row['instance_id']}: absent from the audited hash set")
                elif recorded != want:
                    fails.append(f"{row['instance_id']}: contrast row was not scored on "
                                 f"the audited superseded query")
                # The rows identify the query by hash and must not carry its text:
                # the superseded queries are leaked by construction, so shipping
                # them would republish the thing the paper reports as a defect.
                if "query" in row:
                    fails.append(f"{row['instance_id']}: contrast row carries the "
                                 f"superseded query text")
        if rows != expected:
            fails.append(f"{directory.name} holds {rows} rows, expected {expected}")

    # ---- 5: no V2 table absorbed a treatment row --------------------------
    # A table belongs to the contrast family when its stated purpose is to compare
    # the two query rules, which is exactly when it must name the treatment
    # protocol.  Widening this tuple therefore has to be a deliberate act, and the
    # check below is what makes it one: each allowlisted family must exist and must
    # be anchored by at least one file that really names the protocol, so the
    # allowlist cannot be padded with an unrelated prefix to silence a real hit.
    # Only the primary table needs to name it; the generated section and claim
    # files derived from that table legitimately do not.
    for prefix in CONTRAST_TABLES:
        matches = [p for p in TABLE_DIR.iterdir()
                   if p.is_file() and p.name.startswith(prefix)]
        if not matches:
            fails.append(f"contrast-family allowlist names {prefix}, but no such "
                         f"table exists")
            continue
        named = [p for p in matches if p.suffix in (".json", ".md", ".csv")
                 and TREATMENT in p.read_text(encoding="utf-8", errors="replace")]
        if not named:
            fails.append(f"no file in the {prefix} family names {TREATMENT}; the "
                         f"allowlist is too wide")
    for path in sorted(TABLE_DIR.iterdir()):
        if not path.is_file() or path.name.startswith(CONTRAST_TABLES):
            continue
        if path.suffix not in (".json", ".md", ".csv"):
            continue
        if TREATMENT in path.read_text(encoding="utf-8", errors="replace"):
            fails.append(f"{path.name} mentions {TREATMENT}; a V2 table must not")

    # ---- 6: the released verifier cannot reach a contrast directory -------
    verifier = (ROOT / "experiments" / "verify_results_v2.py").read_text(encoding="utf-8")
    for directory in CONTRAST_DIRS:
        if directory.name in verifier:
            fails.append(f"verify_results_v2.py names {directory.name}")
    if 'raw_dir = RESULTS_DIR / "raw_v2"' not in verifier:
        fails.append("verify_results_v2.py does not read results/raw_v2 literally; "
                     "a broader scan could pick up a contrast arm")
    if "rglob" in verifier or "walk(" in verifier:
        fails.append("verify_results_v2.py walks the results tree; it must read "
                     "results/raw_v2 only")

    if fails:
        print(f"FAILED ({len(fails)})")
        for item in fails:
            print("  -", item)
        return 1
    print(f"VERIFIED: {released_rows} released rows carry {RELEASED}; "
          f"{sum(CONTRAST_DIRS.values())} contrast rows carry {TREATMENT} and "
          f"match the audited superseded queries; no V2 table absorbed one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
