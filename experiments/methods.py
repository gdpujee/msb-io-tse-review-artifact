"""Proposed components: symbol anchors + dependency-graph expansion.

B5 = B4 + symbol anchors matching
B6 = B5 + dependency-graph expansion   (the proposed method)

Why these two components (motivation from the literature):
* BLAgent (2026) reports that 5/14 of its failures are "Hidden Dependency":
  the fix lives in an imported helper/base class, not in the file the issue
  text points at. Dependency edges are exactly the signal that can recover it.
* Issue text often names identifiers verbatim (tracebacks, API names). Exact
  symbol matching is orthogonal to fuzzy semantic similarity.

All components are deterministic and need no LLM.
"""
from __future__ import annotations

import re
from collections import defaultdict

from retrieval import tokenize_code

# --- anchor extraction from issue text ---------------------------------------

_TICK_RE = re.compile(r"`([^`\n]{2,120})`")
_PATH_RE = re.compile(r"\b[A-Za-z0-9_./\\-]+\.(?:py|rs|go|java|js|jsx|ts|tsx|c|h|hpp|cc|cpp|kt)\b")
_QUALIFIED_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_CAMEL_RE = re.compile(r"\b[a-z][a-zA-Z0-9]*[A-Z][A-Za-z0-9]*\b")
_SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,4}\b")
_DUNDER_RE = re.compile(r"\b__[a-z_]+__\b")
_FUNC_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")

# generic English/boilerplate words that must never count as anchors
_STOP = set("""the and for with that this from into your you are not but have has been
was were will can could should would may might must if else then when where what which
who how why all any some more most other such only own same than too very just also
should now new old first last next previous after before while during under over
again further once here there both each few own does did doing done get got make made
use used using want need like well good bad best better worse true false null none
issue bug fix error crash fail fails failed work works working report reports please
thanks thank hi hello note notes see look seems seems_i version versions code file
files line lines function functions method methods class classes module modules
test tests example examples result results value values type types name names""".split())


def extract_anchor_candidates(query: str) -> set[str]:
    """Candidate code identifiers mentioned in the issue text."""
    cands: set[str] = set()
    for m in _FUNC_CALL_RE.finditer(query):
        cands.add(m.group(1))
    for m in _TICK_RE.finditer(query):
        for piece in re.split(r"[^A-Za-z0-9_./]+", m.group(1)):
            if piece:
                cands.add(piece)
    for m in _QUALIFIED_RE.finditer(query):
        cands.add(m.group(0))
        cands.update(m.group(0).split("."))
    for m in _DUNDER_RE.finditer(query):
        cands.add(m.group(0))
    for m in _CAMEL_RE.finditer(query):
        cands.add(m.group(0))
    for m in _SNAKE_RE.finditer(query):
        cands.add(m.group(0))
    # sorted() so that the iteration order is fixed across processes
    # (see FAILURES F009 / rank_list docstring)
    return sorted(c for c in cands
                  if len(c) >= 3 and c.lower() not in _STOP and not c.isdigit())


def extract_path_candidates(query: str) -> set[str]:
    out = set()
    for m in _PATH_RE.finditer(query):
        p = m.group(0).strip("./\\")
        out.add(p)
        out.add(p.split("/")[-1])
    return sorted(out)


# --- repository symbol tables -------------------------------------------------

class RepoSymbols:
    """Symbol -> defining files, plus file->file dependency edges."""

    def __init__(self, files: list[dict], common_df_ratio: float = 0.05):
        self.files = files
        self.paths = [f["path"] for f in files]
        self.sym2files: dict[str, set[int]] = defaultdict(set)
        for i, f in enumerate(files):
            for d in f.get("defs", []):
                self.sym2files[d["name"]].add(i)
        # Very common symbol names (new, get, unwrap, ...) create spurious edges:
        # a symbol defined in more than `common_df_ratio` of files carries almost
        # no localisation signal, so we treat it as non-informative.
        n = max(1, len(files))
        self.common_symbols = {s for s, js in self.sym2files.items()
                               if len(js) > max(3, int(common_df_ratio * n))}
        self.n_common = len(self.common_symbols)
        # basename index for path anchors, e.g. separable.py -> full path
        self.base2files: dict[str, set[int]] = defaultdict(set)
        for i, p in enumerate(self.paths):
            self.base2files[p.split("/")[-1]].add(i)
        self._call_edges: dict[int, set[int]] | None = None
        self._import_edges: dict[int, set[int]] | None = None

    # -- edges ---------------------------------------------------------------
    def call_edges(self) -> dict[int, set[int]]:
        """A --calls--> B when a symbol called in A is defined in B."""
        if self._call_edges is not None:
            return self._call_edges
        edges: dict[int, set[int]] = defaultdict(set)
        for i, f in enumerate(self.files):
            for cname in set(f.get("calls", [])):
                if cname in self.common_symbols:
                    continue
                js = self.sym2files.get(cname)
                # only *unambiguous* definitions: a name defined in many files
                # (typical for headers / duplicated helpers) creates noise edges
                if not js or len(js) != 1:
                    continue
                j = next(iter(js))
                if j != i:
                    edges[i].add(j)
        self._call_edges = dict(edges)
        return self._call_edges

    def import_edges(self) -> dict[int, set[int]]:
        """A --imports--> B when an import statement in A resolves to file B.

        Resolution is deliberately conservative: we match the *last* path
        segment of the import against file basenames (and against the file's
        module path for dotted imports). Unresolvable imports are ignored.
        """
        if self._import_edges is not None:
            return self._import_edges
        edges: dict[int, set[int]] = defaultdict(set)
        for i, f in enumerate(self.files):
            for imp in f.get("imports", []):
                for target in self._resolve_import(imp):
                    for j in target:
                        if j != i:
                            edges[i].add(j)
        self._import_edges = dict(edges)
        return self._import_edges

    def _resolve_import(self, imp: str):
        """Yield sets of file indices that this import may refer to.

        Resolution is ordered by confidence. Crucially, an *ambiguous* basename
        is dropped: `#include "lib/common/zstd_internal.h"` must not also match
        `contrib/linux-kernel/lib/zstd/zstd_internal.h`. Measured on the C
        subset, naive basename matching produced clearly wrong edges.
        """
        txt = re.sub(r"\b(import|from|use|require|include|package|extern|crate|mod|pub|std)\b",
                     " ", imp)
        for tok in re.findall(r"[A-Za-z0-9_./\\:-]+", txt):
            tok = tok.replace("::", "/").strip("./\\")
            if len(tok) < 2:
                continue
            # (1) exact / suffix path match -- highest confidence
            hit = [j for j, p in enumerate(self.paths)
                   if p == tok or p.endswith("/" + tok) or tok.endswith("/" + p)]
            if hit:
                yield set(hit)
                continue
            # (2) unique basename match only (ambiguous names are dropped)
            base_cands = [tok, *(tok + e for e in
                                 (".py", ".rs", ".go", ".java", ".js", ".ts", ".c", ".h", ".cpp", ".hpp"))]
            for b in base_cands:
                js = self.base2files.get(b)
                if js and len(js) == 1:
                    yield set(js)
                    break

    def all_edges(self, use_import: bool = True, use_call: bool = True) -> dict[int, set[int]]:
        out: dict[int, set[int]] = defaultdict(set)
        if use_import:
            for i, js in self.import_edges().items():
                out[i] |= js
        if use_call:
            for i, js in self.call_edges().items():
                out[i] |= js
        return out


# --- scoring components -------------------------------------------------------

def anchor_scores(sym: RepoSymbols, query: str, mode: str = "both") -> dict[int, float]:
    """Score each file by how many *real* symbols/paths from the issue it defines.

    mode:
      "both"   symbol matches + path matches (default, the full component)
      "symbol" only identifiers extracted from the issue text
      "path"   only file paths mentioned in the issue text

    The split exists because the two sub-signals have very different
    availability across languages: path matching needs no parser at all, while
    symbol matching depends entirely on parser coverage (measured: JavaScript
    yields 0.54 defs/file and Kotlin yields 0.00 -- see t9_parse_coverage).
    """
    scores: dict[int, float] = defaultdict(float)
    if mode in ("both", "symbol"):
        for a in extract_anchor_candidates(query):
            js = sym.sym2files.get(a)
            if js:
                w = 1.0
                for j in js:
                    scores[j] += w
            else:
                # substring match on defined symbol names (e.g. `parse_repo_url` vs `parse`)
                for s, js2 in sym.sym2files.items():
                    if len(a) >= 5 and a in s:
                        for j in js2:
                            scores[j] += 0.5
                        break
    if mode in ("both", "path"):
        for p in extract_path_candidates(query):
            base = p.split("/")[-1]
            if base in sym.base2files:
                for j in sym.base2files[base]:
                    scores[j] += 3.0  # a path mentioned verbatim is a very strong signal
    return dict(scores)


def graph_expand(sym: RepoSymbols, seeds: dict[int, float], edges: dict[int, set[int]],
                 hops: int = 1, decay: float = 0.5, reverse: bool = True) -> dict[int, float]:
    """Propagate seed scores along dependency edges (optionally reversed too).

    reverse=True also propagates along *incoming* edges (who imports/calls me),
    which is the direction that recovers BLAgent's "hidden dependency" cases:
    the fix often sits in a helper that the symptom file depends on.
    """
    rev: dict[int, set[int]] = defaultdict(set)
    if reverse:
        for i, js in edges.items():
            for j in js:
                rev[j].add(i)
    out: dict[int, float] = defaultdict(float)
    frontier = dict(seeds)
    for hop in range(1, hops + 1):
        nxt: dict[int, float] = defaultdict(float)
        w = decay ** hop
        # iterate in fixed index order: float accumulation is not associative,
        # so a varying iteration order would change results across runs (F009)
        for i in sorted(frontier):
            s = frontier[i]
            for j in sorted(edges.get(i, ())):
                nxt[j] += s * w
            if reverse:
                for j in sorted(rev.get(i, ())):
                    nxt[j] += s * w
        for j, s in nxt.items():
            out[j] += s
        frontier = nxt
        if not frontier:
            break
    return dict(out)


def minmax_norm(d: dict[int, float]) -> dict[int, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-12:
        return {k: (1.0 if hi > 0 else 0.0) for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def rank_list(scores: dict[int, float], limit: int | None = None) -> list[int]:
    """Descending order of score; only entries with score > 0 are 'retrieved'.

    Ties are broken by file index (x[0]). This is NOT cosmetic: Python
    randomises string hashing per process, so iterating a set of strings (e.g.
    the anchors extracted from an issue) yields a different insertion order
    into `scores` on every run. With `sort(key=-s)` only, tied files kept that
    arbitrary order and therefore received different RRF contributions -- the
    *same* input produced *different* rankings across runs (measured on
    ponylang__ponyc-2214: 3 runs gave MRR 0.5 / 1.0 / 1.0). See FAILURES F009.
    """
    items = [(i, s) for i, s in scores.items() if s > 0]
    items.sort(key=lambda x: (-x[1], x[0]))
    idx = [i for i, _ in items]
    return idx[:limit] if limit else idx


def rrf_fuse(lists: list[list[int]], k: int = 60, weights: list[float] | None = None) -> dict[int, float]:
    """Reciprocal Rank Fusion.

    Chosen over weighted score summation because the components live on
    incomparable scales: BM25 is 0..~600, anchors are small integers. Min-max
    normalisation was tried first and *hurt* (measured), because it stretches a
    single incidental anchor hit to 1.0 -- the same weight as the best lexical
    match. RRF only rewards being retrieved at a good rank, and ignores
    documents a component did not retrieve.
    """
    out: dict[int, float] = defaultdict(float)
    ws = weights or [1.0] * len(lists)
    for w, lst in zip(ws, lists):
        for rank, i in enumerate(lst):
            out[i] += w / (k + rank + 1)
    return dict(out)
