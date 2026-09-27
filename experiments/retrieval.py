"""Retrieval baselines for file-level issue localization.

Implemented so far (method ladder from notes/research_design.md):
  B1  BM25 over file content
  B2  BM25 over (file path repeated + content)   <- path augmentation
Later: dense, RRF fusion, symbol anchors, dependency-graph expansion.
"""
from __future__ import annotations

import math
import re
from collections import Counter

# --- code-aware tokenization -------------------------------------------------
# Splitting identifiers matters a lot for code: `parseRepoURL` -> parse repo url
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")


def tokenize_code(text: str, min_len: int = 2) -> list[str]:
    toks: list[str] = []
    for raw in _NON_ALNUM_RE.split(text):
        if not raw:
            continue
        parts = _CAMEL_RE.split(raw)
        for p in parts:
            p = p.lower()
            if len(p) >= min_len:
                toks.append(p)
    return toks


class BM25:
    """Okapi BM25 with an inverted index (build cost O(total tokens)).

    The naive 'for each term scan every doc' build is O(vocab * ndocs), which is
    far too slow for 900-file repositories; we build postings instead.
    """

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(corpus_tokens)
        self.doc_len = [len(d) for d in corpus_tokens]
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        postings: dict[str, list[tuple[int, int]]] = {}
        for i, toks in enumerate(corpus_tokens):
            for term, f in Counter(toks).items():
                postings.setdefault(term, []).append((i, f))
        self.idf = {t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5))
                    for t, p in postings.items()}
        # precompute per-posting contribution: idf * tf * (k1+1) / (tf + k1*(...))
        self.index: dict[str, list[tuple[float, int]]] = {}
        for term, plist in postings.items():
            idf = self.idf[term]
            contribs = []
            for i, f in plist:
                denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1))
                contribs.append((idf * f * (self.k1 + 1) / denom, i))
            self.index[term] = contribs

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = [0.0] * self.n
        qt = Counter(query_tokens)
        for term, qf in qt.items():
            for score, i in self.index.get(term, ()):
                out[i] += score * qf
        return out

    def topk(self, query_tokens: list[str], k: int = 10) -> list[tuple[int, float]]:
        s = self.scores(query_tokens)
        idx = sorted(range(self.n), key=lambda i: -s[i])[:k]
        return [(i, s[i]) for i in idx if s[i] > 0]


def build_corpus(files: list[dict], path_repeat: int = 1, max_chars: int = 60_000) -> tuple[list[str], list[list[str]]]:
    """Return (doc_ids, token_lists). path_repeat>1 implements path augmentation."""
    ids, toks = [], []
    for f in files:
        text = (f["path"] + "\n") * path_repeat + f.get("text", "")[:max_chars]
        ids.append(f["path"])
        toks.append(tokenize_code(text))
    return ids, toks
