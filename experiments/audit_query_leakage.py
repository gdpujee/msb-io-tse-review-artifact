#!/usr/bin/env python3
"""Measure query-level solution leakage for both the superseded and the released
query protocols, on the same instance set.

The claim this gate tests
-------------------------
A localization query is *leaked* when it reproduces text that was written after
the fix.  For this corpus the post-solution text is the pull request: the
top-level ``title`` and ``body`` of each upstream row.  So the test is direct and
needs no model -- does the query contain the PR title, or any MIN_BODY_SPAN
consecutive characters of the PR body, verbatim?

Both comparisons are made on CRLF-normalised text, because that is what the
query builders produce: ``_clean`` converts ``\r\n`` to ``\n`` before assembling
a query.  Comparing a raw body against a normalised query reports "no match" for
every CRLF-authored row, which under-counted body matches by an order of
magnitude until F021.

Two protocols are measured, not one
-----------------------------------
``issue_only``   the released rule: only pre-solution fields are admitted
                 (``problem_statement``, or linked-issue titles and bodies).
``legacy_mixed`` the superseded rule, reconstructed from the raw rows: the
                 top-level PR ``title`` and ``body`` were concatenated with the
                 issue text, with a synthetic ``Issue #0`` entry added for the
                 SWE-bench-Verified-style Python rows that ship no
                 ``resolved_issues``.  This reconstruction reproduces all 1,791
                 superseded queries byte-for-byte (see ``--verify-legacy``), so
                 the baseline is reproducible from ``data/raw/`` and does not
                 depend on retaining a file full of leaked queries.

Why the target is not zero
--------------------------
Maintainers routinely title a pull request after the issue it closes, and issue
authors routinely write the proposed fix *inside* the issue.  Both directions
make a legitimately issue-only query share a string with the PR title, and
deleting the string would delete genuine query text.  The success criterion is
therefore not "zero matches" but "every match is attributable to pre-solution
text".  Three attributions are accepted, and one is not:

``issue_title``       the PR title equals, contains, or is contained in a linked
                      issue's own title -- the ordinary "PR named after the
                      issue" convention.
``issue_proposal``    the PR title occurs inside an issue's text as the
                      reporter's own proposed wording, and that occurrence is
                      not part of a pull-request reference.
``pr_reference``      the match lies on a line naming *the instance's own* pull
                      request (``/pull/<n>`` or ``#<n>``, with ``<n>`` the
                      instance number).  This is *upstream issue-body
                      contamination*: the issue field itself was edited after the
                      fix, by a bot or a maintainer, to list the submitted PRs.
                      It is real residual leakage and it is reported, not hidden.
                      The rule is deliberately narrow -- see ``own_pr_line`` --
                      so the residual it reports is a lower bound.
``unexplained``       anything else.  For the released protocol this aborts.

The distinction matters because it decides what the fix is.  ``issue_title`` and
``issue_proposal`` need no action.  ``pr_reference`` cannot be fixed by choosing
a different field: the corpus would have to be re-scraped at the issue's pre-fix
revision.  That is a limit of the data, and the paper states it.

Usage
-----
    python audit_query_leakage.py                       # both protocols
    python audit_query_leakage.py --verify-legacy       # also check the hashes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from config import LANG_FILES, RAW_DIR  # noqa: E402
from dataset import _PLACEHOLDER, _clean, load_all  # noqa: E402

PLACEHOLDER = {"placeholder", "none", "n/a", ""}
MIN_BODY_SPAN = 40
LEGACY_HASHES = ROOT / "results" / "audit_v2" / "legacy_query_hashes.json"

# The only pull-request reference that makes a query line report the *solution*
# is a reference to this instance's own pull request.  A generic "/pull/<n>" or
# "pull request" match also fires on the reporter citing an earlier, unrelated
# pull request and on documentation page titles, and counting those as residual
# leakage manufactures findings.  Inspection of what the loose form matched
# showed exactly that failure -- three of five body hits and thirty-nine of
# forty-one title hits were unrelated references -- so the loose form is gone.


# --------------------------------------------------------------- query rules
def legacy_query(row: dict) -> str:
    """The superseded query rule, reconstructed.  Verified byte-exact on 1,791."""
    parts: list[str] = []
    for key in ("title", "body"):
        value = _clean(row.get(key))
        if value and value.lower() not in _PLACEHOLDER:
            parts.append(value)
    problem = _clean(row.get("problem_statement"))
    if problem and problem.lower() not in _PLACEHOLDER:
        parts.append(problem)
    issues = list(row.get("resolved_issues") or [])
    if not issues and problem and problem.lower() not in _PLACEHOLDER:
        # SWE-bench-Verified-style rows ship no resolved_issues; the superseded
        # loader synthesized one holding the problem statement under number 0.
        issues = [{"number": 0, "title": "placeholder", "body": problem}]
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        number = issue.get("number")
        title = _clean(issue.get("title"))
        body = _clean(issue.get("body"))
        if title and title.lower() not in _PLACEHOLDER:
            parts.append(f"Issue #{number} title: {title}")
        if body and body.lower() not in _PLACEHOLDER:
            parts.append(f"Issue #{number} body: {body}")
    return "\n\n".join(parts).strip()


def load_raw_corpus() -> dict[str, dict]:
    """instance_id -> {lang, row}, for every language actually present."""
    corpus: dict[str, dict] = {}
    for lang, files in LANG_FILES.items():
        for name in files:
            path = RAW_DIR / f"{lang}__{name}"
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    iid = row.get("instance_id") or (
                        f"{row['org']}__{row['repo']}-{row.get('number')}"
                    )
                    corpus[iid] = {"lang": lang, "row": row}
    return corpus


# ---------------------------------------------------------------- attribution
def issue_titles(row: dict) -> list[str]:
    titles = []
    for issue in row.get("resolved_issues") or []:
        if isinstance(issue, dict):
            title = _clean(issue.get("title"))
            if title and title.lower() not in PLACEHOLDER:
                titles.append(title)
    return titles


def issue_bodies(row: dict) -> list[str]:
    bodies = []
    for issue in row.get("resolved_issues") or []:
        if isinstance(issue, dict):
            body = _clean(issue.get("body"))
            if body and body.lower() not in PLACEHOLDER:
                bodies.append(body)
    return bodies


def issue_text(row: dict) -> str:
    """Every pre-solution string a row offers, joined, for span containment."""
    return "\n\n".join(issue_titles(row) + issue_bodies(row))


def enclosing_line(text: str, index: int) -> str:
    """The single line of ``text`` that contains position ``index``."""
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return text[start:] if end == -1 else text[start:end]


def first_body_span(query: str, body: str, span: int = MIN_BODY_SPAN) -> str | None:
    """The first ``span``-character window of ``body`` that occurs in ``query``.

    The query's windows are hashed once and the body's windows looked up against
    them, which keeps this linear in text length instead of quadratic; it runs on
    every instance of two protocols.
    """
    if len(body) < span or len(query) < span:
        return None
    windows = {query[i:i + span] for i in range(len(query) - span + 1)}
    for i in range(len(body) - span + 1):
        window = body[i:i + span]
        if window in windows:
            return window
    return None


def own_pr_line(line: str, number) -> bool:
    """Does ``line`` reference *this instance's own* pull request?

    Precise by construction, and therefore a lower bound on residual leakage:
    a post-hoc bot comment that names some other pull request is not counted.
    """
    if not line or number is None:
        return False
    n = re.escape(str(number))
    return re.search(rf"(?:/pull/{n}(?!\d)|#{n}(?!\d))", line) is not None


# Any pull-request mention at all.  Used only to count how many matches the
# precise rule above leaves unexamined, so that the lower bound is quantified
# rather than asserted.  It is never an attribution.
_ANY_PR = re.compile(r"(?:/pull/\d+|\bpull request\b)", re.IGNORECASE)

# GitHub's merge-queue bot writes this sentence into a pull request once the
# merge queue accepts it.  Finding it in an *issue* field means the field was
# written to after the pull request existed.  Counted separately so that the
# manuscript's breakdown of the unexamined matches is derived, not eyeballed.
_BOT_PR_LINE = re.compile(r"will be added to the merge queue", re.IGNORECASE)


def other_pr_line(query: str, needle: str, number) -> bool:
    """Is ``needle`` on a line mentioning some pull request that is not ours?"""
    position = query.find(needle)
    if position < 0:
        return False
    line = enclosing_line(query, position)
    return bool(_ANY_PR.search(line)) and not own_pr_line(line, number)


def bot_pr_line(query: str, needle: str) -> bool:
    """Is ``needle`` on a line written by the merge-queue bot?"""
    position = query.find(needle)
    if position < 0:
        return False
    return bool(_BOT_PR_LINE.search(enclosing_line(query, position)))


def attribute(query: str, title: str, titles: list[str], bodies: list[str],
              number=None) -> str | None:
    """Decide where a query/PR-title overlap came from, or return None."""
    for candidate in titles:
        if title == candidate or title in candidate or candidate in title:
            return "issue_title"
    position = query.find(title)
    if position >= 0 and own_pr_line(enclosing_line(query, position), number):
        return "pr_reference"
    for body in bodies:
        if title in body:
            return "issue_proposal"
    return None


def attribute_body(query: str, span: str, row: dict) -> str | None:
    """Decide where a query/PR-body overlap came from, or return None.

    A span is accepted only if the pre-solution issue text really contains it --
    that is the claim, so it is tested rather than assumed.  The exception is a
    span on a line naming the instance's own pull request, which is residual
    whatever else it matches, because the line is then reporting the solution
    rather than the problem.
    """
    position = query.find(span)
    if position >= 0 and own_pr_line(enclosing_line(query, position), row.get("number")):
        return "pr_reference"
    if span in issue_text(row):
        return "issue_text"
    return None


def classify(instance_id: str, query: str, entry: dict) -> dict:
    row = entry["row"]
    # Normalise exactly as both query builders do: ``_clean`` maps CRLF to LF
    # before assembling a query, so comparing raw fields against a query reports
    # "no match" for every CRLF-authored row.  That mismatch is F021.
    title = _clean(row.get("title"))
    body = _clean(row.get("body"))
    titles = issue_titles(row)

    title_hit = title.lower() not in PLACEHOLDER and title in query
    span = first_body_span(query, body)
    body_hit = span is not None
    number = row.get("number")
    attribution = (attribute(query, title, titles, issue_bodies(row), number)
                   if title_hit else None)
    body_attribution = attribute_body(query, span, row) if body_hit else None

    return {
        "instance_id": instance_id,
        "lang": entry["lang"],
        "pr_title_in_query": title_hit,
        "pr_body_in_query": body_hit,
        "body_span": span,
        "attribution": attribution,
        "body_attribution": body_attribution,
        "unexplained": title_hit and attribution is None,
        "body_unexplained": body_hit and body_attribution is None,
        # Quantifies what the precise rule leaves unexamined: a body span on a
        # line that mentions some pull request, but not this instance's own.
        "body_other_pr_line": bool(body_hit) and other_pr_line(query, span, number),
        "body_bot_pr_line": bool(body_hit) and bot_pr_line(query, span),
    }


# ------------------------------------------------------------------ measuring
def measure(records: list[dict]) -> dict:
    total = len(records)
    counts = {name: sum(1 for r in records if r["attribution"] == name)
              for name in ("issue_title", "issue_proposal", "pr_reference")}
    body_counts = {name: sum(1 for r in records if r["body_attribution"] == name)
                   for name in ("issue_text", "pr_reference")}
    unexplained = [r for r in records if r["unexplained"]]
    body_unexplained = [r for r in records if r["body_unexplained"]]
    title_hits = sum(r["pr_title_in_query"] for r in records)
    body_hits = sum(r["pr_body_in_query"] for r in records)

    per_language: dict[str, dict] = {}
    for lang in sorted({r["lang"] for r in records}):
        subset = [r for r in records if r["lang"] == lang]
        per_language[lang] = {
            "instances": len(subset),
            "pr_title_in_query": sum(r["pr_title_in_query"] for r in subset),
            "pr_body_in_query": sum(r["pr_body_in_query"] for r in subset),
            "issue_title": sum(1 for r in subset if r["attribution"] == "issue_title"),
            "issue_proposal": sum(1 for r in subset if r["attribution"] == "issue_proposal"),
            "pr_reference": sum(1 for r in subset if r["attribution"] == "pr_reference"),
            "unexplained": sum(r["unexplained"] for r in subset),
            "body_issue_text": sum(1 for r in subset if r["body_attribution"] == "issue_text"),
            "body_pr_reference": sum(1 for r in subset if r["body_attribution"] == "pr_reference"),
            "body_unexplained": sum(r["body_unexplained"] for r in subset),
        }

    return {
        "instances": total,
        "pr_title_in_query": title_hits,
        "pr_title_in_query_fraction": round(title_hits / total, 6) if total else 0.0,
        "pr_body_in_query": body_hits,
        "pr_body_in_query_fraction": round(body_hits / total, 6) if total else 0.0,
        "body_span_chars": MIN_BODY_SPAN,
        "attributed_issue_title": counts["issue_title"],
        "attributed_issue_proposal": counts["issue_proposal"],
        "attributed_pr_reference": counts["pr_reference"],
        "residual_unexplained": len(unexplained),
        "unexplained_examples": [r["instance_id"] for r in unexplained[:10]],
        "body_attributed_issue_text": body_counts["issue_text"],
        "body_attributed_pr_reference": body_counts["pr_reference"],
        "residual_body_unexplained": len(body_unexplained),
        "body_unexplained_examples": [r["instance_id"] for r in body_unexplained[:10]],
        "body_on_other_pr_line": sum(r["body_other_pr_line"] for r in records),
        "body_on_bot_pr_line": sum(r["body_bot_pr_line"] for r in records),
        "per_language": per_language,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Query-level solution leakage",
        "",
        "Both protocols are measured on the same instances against the upstream "
        "pull-request text, so the two rows are directly comparable. A PR-body "
        f"match is any {report['protocols']['issue_only'].get('body_span_chars', MIN_BODY_SPAN)}"
        "-character window of the body occurring in the query; every match is "
        "attributed, and the attribution columns are counts of matches.",
        "",
        "| protocol | instances | PR title | PR body | title: issue_title | "
        "title: issue_proposal | title: pr_reference | title: unexplained | "
        "body: issue_text | body: pr_reference | body: unexplained |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, block in report["protocols"].items():
        lines.append(
            f"| {name} | {block['instances']} | "
            f"{block['pr_title_in_query']} ({block['pr_title_in_query_fraction']:.1%}) | "
            f"{block['pr_body_in_query']} ({block['pr_body_in_query_fraction']:.1%}) | "
            f"{block['attributed_issue_title']} | {block['attributed_issue_proposal']} | "
            f"{block['attributed_pr_reference']} | {block['residual_unexplained']} | "
            f"{block['body_attributed_issue_text']} | "
            f"{block['body_attributed_pr_reference']} | "
            f"{block['residual_body_unexplained']} |"
        )
    for name, block in report["protocols"].items():
        lines += ["", f"## {name}: per language", "",
                  "| lang | instances | PR title | PR body | title: issue_title | "
                  "title: issue_proposal | title: pr_reference | title: unexplained | "
                  "body: issue_text | body: pr_reference | body: unexplained |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for lang, row in block["per_language"].items():
            lines.append(
                f"| {lang} | {row['instances']} | {row['pr_title_in_query']} | "
                f"{row['pr_body_in_query']} | {row['issue_title']} | "
                f"{row['issue_proposal']} | {row['pr_reference']} | {row['unexplained']} | "
                f"{row['body_issue_text']} | {row['body_pr_reference']} | "
                f"{row['body_unexplained']} |"
            )
    lines += ["", report["criterion"], ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-legacy", action="store_true",
                        help="check the reconstructed legacy queries against stored hashes")
    args = parser.parse_args()

    corpus = load_raw_corpus()
    released = {item.instance_id: item.query for item in load_all()}
    missing = sorted(set(released) - set(corpus))

    protocols = {
        "issue_only": {
            iid: classify(iid, query, corpus[iid])
            for iid, query in released.items() if iid in corpus
        },
        "legacy_mixed": {
            iid: classify(iid, legacy_query(entry["row"]), entry)
            for iid, entry in corpus.items()
        },
    }

    report = {
        "criterion": (
            "A residual overlap with the pull request is acceptable when it is "
            "attributable to pre-solution text. For the title: the PR is named "
            "after a linked issue (issue_title) or quotes the reporter's own "
            "wording (issue_proposal). For a body span: the span occurs in the "
            "pre-solution issue text (issue_text), which is what a pull-request "
            "body quoting the report looks like. A match on a line naming the "
            "instance's own pull request (pr_reference) is upstream issue-body "
            "contamination -- the issue field was edited after the fix -- and is "
            "reported as residual leakage rather than hidden. The rule is "
            "narrow by design: a reference to some other pull request is not "
            "counted, so the residual is a lower bound. An unattributable match "
            "of either kind fails the released protocol."
        ),
        "instances_missing_from_corpus": len(missing),
        "protocols": {name: measure(list(records.values()))
                      for name, records in protocols.items()},
    }

    if args.verify_legacy:
        stored = json.loads(LEGACY_HASHES.read_text())
        exact = sum(
            1 for iid, digest in stored.items()
            if hashlib.sha256(legacy_query(corpus[iid]["row"]).encode()).hexdigest() == digest
        )
        report["legacy_reconstruction"] = {
            "stored_hashes": len(stored),
            "byte_exact": exact,
            "all_reproduced": exact == len(stored),
        }

    released_block = report["protocols"]["issue_only"]
    legacy_block = report["protocols"]["legacy_mixed"]
    problems = []
    if missing:
        problems.append(f"{len(missing)} instances missing from the raw corpus")
    if released_block["residual_unexplained"]:
        problems.append(
            f"released protocol has {released_block['residual_unexplained']} "
            "unattributable title matches"
        )
    if released_block["residual_body_unexplained"]:
        problems.append(
            f"released protocol has {released_block['residual_body_unexplained']} "
            "unattributable body-span matches"
        )
    if args.verify_legacy and not report["legacy_reconstruction"]["all_reproduced"]:
        problems.append("legacy query reconstruction is not byte-exact")

    report["status"] = "VERIFIED" if not problems else "FAILED"

    out_dir = ROOT / "results" / "audit_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "query_leakage.json").write_text(json.dumps(report, indent=1) + "\n",
                                                encoding="utf-8")
    (out_dir / "query_leakage.md").write_text(render_markdown(report), encoding="utf-8")

    for name, block in report["protocols"].items():
        print(f"{name:14s} instances={block['instances']}  "
              f"PR-title={block['pr_title_in_query']} "
              f"({block['pr_title_in_query_fraction']:.1%})  "
              f"PR-body={block['pr_body_in_query']} "
              f"({block['pr_body_in_query_fraction']:.1%})  "
              f"[title] issue_title={block['attributed_issue_title']} "
              f"issue_proposal={block['attributed_issue_proposal']} "
              f"pr_reference={block['attributed_pr_reference']} "
              f"unexplained={block['residual_unexplained']}  "
              f"[body] issue_text={block['body_attributed_issue_text']} "
              f"pr_reference={block['body_attributed_pr_reference']} "
              f"unexplained={block['residual_body_unexplained']}")
    if "legacy_reconstruction" in report:
        rec = report["legacy_reconstruction"]
        print(f"legacy reconstruction: {rec['byte_exact']}/{rec['stored_hashes']} byte-exact")
    print(f"status: {report['status']}")
    if problems:
        for item in problems:
            print("  -", item)
        return 1
    print("VERIFIED: every title match and every body span under the released "
          "protocol is attributable to pre-solution text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
