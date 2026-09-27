"""Load Multi-SWE-bench instances and turn them into localization tasks.

Design notes (all decisions recorded in DECISIONS.md):
* ground truth = files touched by `fix_patch` (the fix), NOT by `test_patch`.
* query text is issue-only.  Top-level `title`/`body` in Multi-SWE-bench are
  pull-request text and are post-solution information, so they are never used.
  We prefer `problem_statement` where present; otherwise we use linked issue
  titles/bodies from `resolved_issues`.
* kotlin rows in the HF dump lack `instance_id`; we synthesize the same
  `org__repo-number` convention used by the other languages.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

from config import RAW_DIR, LANG_FILES, SRC_EXT, DATA_DIR

_DIFF_GIT_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)
_MINUS_RE = re.compile(r"^--- (a/\S+|/dev/null)", re.M)
_PLUS_RE = re.compile(r"^\+\+\+ (b/\S+|/dev/null)", re.M)


def patch_files(patch: str) -> list[str]:
    """Return the set of file paths touched by a unified diff, in order."""
    if not patch:
        return []
    out: list[str] = []
    for m in _DIFF_GIT_RE.finditer(patch):
        a, b = m.group(1), m.group(2)
        path = b if b != "/dev/null" else a
        if path != "/dev/null":
            out.append(path)
    if not out:  # fall back to --- / +++ headers
        for minus, plus in zip(_MINUS_RE.findall(patch), _PLUS_RE.findall(patch)):
            path = plus[2:] if plus.startswith("b/") else minus[2:]
            if path and path != "/dev/null":
                out.append(path)
    # de-duplicate, preserve order
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _clean(txt: str | None) -> str:
    return (txt or "").replace("\r\n", "\n").strip()


_PLACEHOLDER = {"placeholder", "none", "n/a", ""}
QUERY_PROTOCOL = "issue_only_v2"
TEST_FILTER_PROTOCOL = "component_aware_test_filter_v6"


def build_query(row: dict) -> tuple[str, dict]:
    """Assemble a pre-solution, issue-only localization query.

    Field provenance differs across subsets (measured, not assumed):
      * SWE-bench Verified style (python subset) ships `problem_statement`
        and sets `title`/`body` to the literal string "placeholder".
      * Multi-SWE-bench style has PR text in top-level `title`/`body` and the
        pre-solution issue text in `resolved_issues[]`.

    Mixing these sources caused target leakage in protocol V1.  V2 therefore
    selects exactly one issue source and records its provenance.  PR fields and
    hints are measured for the audit only and can never enter ``query``.
    """
    parts: list[str] = []
    body = _clean(row.get("body"))
    title = _clean(row.get("title"))
    ps = _clean(row.get("problem_statement"))
    source = "problem_statement" if ps and ps.lower() not in _PLACEHOLDER else "resolved_issues"
    if source == "problem_statement":
        parts.append(ps)
    issues = row.get("resolved_issues") or []
    n_issue_title_chars = 0
    n_issue_chars = 0
    for it in issues:
        if isinstance(it, dict):
            t, b = _clean(it.get("title")), _clean(it.get("body"))
            if t and t.lower() not in _PLACEHOLDER:
                n_issue_title_chars += len(t)
                if source == "resolved_issues":
                    parts.append(t)
            if b and b.lower() not in _PLACEHOLDER:
                n_issue_chars += len(b)
                if source == "resolved_issues":
                    parts.append(b)
    query = "\n\n".join(p for p in parts if p).strip()
    stats = {
        "query_protocol": QUERY_PROTOCOL,
        "query_source": source,
        "fields_used": [source],
        "fields_excluded": ["title", "body", "hints", "hints_text"],
        "n_linked_issues": len(issues),
        "excluded_pr_title_chars": len(title) if title.lower() not in _PLACEHOLDER else 0,
        "excluded_pr_body_chars": len(body) if body.lower() not in _PLACEHOLDER else 0,
        "linked_issue_title_chars": n_issue_title_chars,
        "linked_issue_chars": n_issue_chars,
        "problem_statement_chars": len(ps),
        "query_chars": len(query),
        "query_empty": len(query) == 0,
    }
    return query, stats


@dataclass
class Instance:
    instance_id: str
    org: str
    repo: str
    number: int
    lang: str
    base_sha: str
    query: str
    gold_files: list[str]
    test_files: list[str]
    stats: dict = field(default_factory=dict)

    @property
    def gold_files_nontest(self) -> list[str]:
        from config import TEST_PATH_HINTS
        return [f for f in self.gold_files if not _looks_test(f, TEST_PATH_HINTS)]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gold_files_nontest"] = self.gold_files_nontest
        return d


def _looks_test(path: str, hints: tuple[str, ...]) -> bool:
    """Detect test/benchmark paths without substring-matching normal words."""
    low = path.lower()
    original_parts = path.replace("\\", "/").split("/")
    directory_tags = set(hints) | {
        "testdata", "unittest", "benches", "benchmarks",
        "testlib", "testutil", "testutils", "testsupport",
        "gtest", "googletest", "gbenchmark",
    }
    filename_tags = set(hints)

    def component_tokens(component: str) -> set[str]:
        # Split both delimiter compounds (integration-test, test_package) and
        # camel case (androidTest, funTest, benchmarkDictBuilder).  Deliberately
        # do not use prefix substring checks: "/spec" incorrectly classified
        # production names such as spectral_coordinate.py.
        acronym_split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", component)
        camel_split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", acronym_split)
        return {token.lower() for token in re.split(r"[^A-Za-z0-9]+", camel_split) if token}

    compound_test_token = re.compile(
        r"^(?:test|testing|spec|fixture|bench)(?:util|utils|helper|helpers|support|data|lib|v\d+)$"
    )
    for component in original_parts[:-1]:
        tokens = component_tokens(component)
        if tokens & directory_tags or any(compound_test_token.fullmatch(token) for token in tokens):
            return True

    suffix_match = low.endswith((
        "_test.go", "_test.py", "_tests.py", "_testing.py",
        "_test.c", "_test.cc", "_test.cpp",
        "_tests.c", "_tests.cc", "_tests.cpp",
        ".test.js", ".test.jsx", ".test.ts", ".test.tsx",
        ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx",
    ))
    if suffix_match:
        return True

    filename = original_parts[-1] if original_parts else path
    stem = filename.rsplit(".", 1)[0]
    acronym_stem = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", stem)
    camel_stem = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", acronym_stem)
    stem_tokens = [
        token.lower() for token in re.split(r"[^A-Za-z0-9]+", camel_stem) if token
    ]
    # Filenames are more ambiguous than directory names: production classes
    # such as ProcessingSpecSettingsBridge contain an internal "Spec" token.
    # Exact names are safe across languages. Java/Kotlin conventionally use
    # terminal class tokens (FooTest/FooSpec); applying that rule to every
    # language would wrongly discard Catch2's production catch_test_spec.cpp.
    suffix = Path(filename).suffix.lower()
    java_kotlin_terminal = suffix in {".java", ".kt", ".kts"} and (
        stem_tokens and stem_tokens[-1] in filename_tags
    )
    leading_test_helper = suffix in {".go", ".py", ".rs"} and stem.lower().startswith(
        ("test_", "tests_", "spec_")
    )
    if stem.lower() in filename_tags or java_kotlin_terminal or leading_test_helper:
        return True

    # A few ecosystems use unsplit lowercase helper filenames.  Keep this list
    # exact so ordinary words beginning with "test" or "spec" remain source.
    return stem.lower() in {
        "testutil", "testutils", "testhelper", "testhelpers",
        "testsupport", "specutil", "specutils", "benchfn", "benchzstd",
    } or bool(compound_test_token.fullmatch(stem.lower()))


def load_language(lang: str, raw_dir: Path = RAW_DIR) -> list[Instance]:
    files = LANG_FILES.get(lang, [])
    insts: list[Instance] = []
    for fn in files:
        p = raw_dir / f"{lang}__{fn}"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            insts.append(_row_to_instance(row, lang))
    return insts


def _row_to_instance(row: dict, lang: str) -> Instance:
    org, repo = row["org"], row["repo"]
    number = row.get("number")
    iid = row.get("instance_id") or f"{org}__{repo}-{number}"
    base = row.get("base") or {}
    query, stats = build_query(row)
    gold = patch_files(row.get("fix_patch", ""))
    test = patch_files(row.get("test_patch", ""))
    return Instance(
        instance_id=iid,
        org=org,
        repo=repo,
        number=number,
        lang=lang,
        base_sha=base.get("sha", ""),
        query=query,
        gold_files=gold,
        test_files=test,
        stats=stats,
    )


def load_all(langs: Iterable[str] | None = None, raw_dir: Path = RAW_DIR) -> list[Instance]:
    langs = list(langs) if langs else list(LANG_FILES)
    out: list[Instance] = []
    for lang in langs:
        got = load_language(lang, raw_dir)
        out.extend(got)
    return out


if __name__ == "__main__":
    import argparse
    from collections import Counter

    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", type=Path, default=DATA_DIR / "instances.jsonl")
    args = ap.parse_args()

    all_insts = load_all()
    print(f"loaded {len(all_insts)} instances")
    by_lang = Counter(i.lang for i in all_insts)
    for lang, n in sorted(by_lang.items()):
        sub = [i for i in all_insts if i.lang == lang]
        empty = sum(1 for i in sub if i.stats["query_empty"])
        short = sum(1 for i in sub if 0 < i.stats["excluded_pr_body_chars"] < 50)
        no_gold = sum(1 for i in sub if not i.gold_files)
        print(f"  {lang:8s} n={n:5d}  query_empty={empty:4d}  excluded_pr_body<50chars={short:4d}  no_gold_files={no_gold:3d}")
    with args.dump.open("w", encoding="utf-8") as f:
        for i in all_insts:
            f.write(json.dumps(i.to_dict(), ensure_ascii=False) + "\n")
    print(f"wrote {args.dump}")
