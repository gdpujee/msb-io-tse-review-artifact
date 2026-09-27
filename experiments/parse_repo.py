"""Language-agnostic repository parsing with tree-sitter.

Goal: for every source file produce
  * the list of defined symbols (functions / methods / types) with line ranges,
  * the identifiers that are *called* in the file (call sites),
  * the module paths that are *imported* by the file,
  * the parent/inheritance relations when the grammar exposes them.

We deliberately use a **generic node-type walk** rather than per-language SCM
queries so that 8 languages share one code path. Precision is lower than
hand-written queries, but:
  * it is uniform across languages (essential for a cross-language study), and
  * we *measure* parse coverage per language and report it (see RQ1/threats).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tree_sitter import Language, Parser

from config import SRC_EXT, TS_LANG

# A file larger than this is excluded from the corpus. This is part of the
# corpus definition (DECISIONS.md D004), not a performance knob: it is applied
# identically to every language and to every instance.
MAX_FILE_BYTES = 2_000_000

# --- node type vocabularies (multi-language) --------------------------------

DEF_TYPES = {
    "function_definition", "function_declaration", "method_declaration",
    "method_definition", "constructor_declaration", "class_declaration",
    "class_definition", "class_specifier", "struct_item", "struct_specifier",
    "enum_item", "enum_specifier", "interface_declaration", "trait_item",
    "impl_item", "mod_item", "type_declaration", "type_item",
}

CALL_TYPES = {
    "call", "call_expression", "method_invocation", "object_creation_expression",
    "new_expression", "macro_invocation",
}

IMPORT_TYPES = {
    "import_statement", "import_from_statement", "import_declaration",
    "use_declaration", "preproc_include", "package_declaration",
}

INHERIT_TYPES = {"superclass", "superclass_clause", "interfaces", "base_list"}


def _load_language(lang: str):
    """Return a tree_sitter.Language or None if unavailable."""
    mod_name = TS_LANG.get(lang)
    if not mod_name:
        return None
    try:
        mod = __import__(mod_name)
    except Exception:
        return None
    try:
        if lang == "ts":
            return Language(mod.language_typescript())
        return Language(mod.language())
    except Exception:
        return None


_LANG_CACHE: dict[str, Language | None] = {}


def get_language(lang: str):
    if lang not in _LANG_CACHE:
        _LANG_CACHE[lang] = _load_language(lang)
    return _LANG_CACHE[lang]


def _node_text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _first_identifier(node):
    for ch in node.children:
        if ch.type in ("identifier", "type_identifier", "primitive_type"):
            return ch
    return None


def _def_name(node, src: bytes) -> str | None:
    n = node.child_by_field_name("name")
    if n is not None:
        return _node_text(n, src)
    ident = _first_identifier(node)
    return _node_text(ident, src) if ident else None


def _callee_name(node, src: bytes) -> str | None:
    fn = node.child_by_field_name("function") or node.child_by_field_name("name")
    if fn is not None:
        txt = _node_text(fn, src)
        # keep only the trailing identifier for qualified calls a.b.c()
        for sep in (".", "::", "->"):
            if sep in txt:
                txt = txt.split(sep)[-1]
        txt = txt.strip()
        return txt or None
    return None


@dataclass
class FileFacts:
    path: str
    lang: str
    n_lines: int
    defs: list[dict] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    parse_ok: bool = True
    error: str = ""

    def to_dict(self):
        return {
            "path": self.path, "lang": self.lang, "n_lines": self.n_lines,
            "defs": self.defs, "calls": self.calls, "imports": self.imports,
            "parse_ok": self.parse_ok, "error": self.error,
        }


def parse_file(path: Path, rel: str, lang: str, src: bytes) -> FileFacts:
    text = src.decode("utf-8", errors="ignore")
    facts = FileFacts(path=rel, lang=lang, n_lines=text.count("\n") + 1)
    language = get_language(lang)
    if language is None:
        facts.parse_ok = False
        facts.error = "no_parser"
        return facts
    parser = Parser(language)
    tree = parser.parse(src)
    root = tree.root_node
    if root.has_error:
        # still usable, but flag it
        facts.error = "has_error"

    def walk(node, depth=0):
        if depth > 200:
            return
        t = node.type
        if t in DEF_TYPES:
            nm = _def_name(node, src)
            if nm:
                facts.defs.append({
                    "name": nm, "kind": t,
                    "start": node.start_point[0] + 1, "end": node.end_point[0] + 1,
                })
        elif t in CALL_TYPES:
            nm = _callee_name(node, src)
            if nm:
                facts.calls.append(nm)
        elif t in IMPORT_TYPES:
            facts.imports.append(_node_text(node, src).strip()[:200])
        for ch in node.children:
            walk(ch, depth + 1)

    walk(root)
    return facts


def parse_sources(pairs: Iterable[tuple[str, bytes]], lang: str,
                  max_bytes: int = MAX_FILE_BYTES) -> dict:
    """Parse in-memory `(relative_path, source_bytes)` pairs.

    This is the single parsing implementation. It takes no filesystem access,
    which lets the pipeline stream a GitHub tarball straight from the network
    into the index without ever writing it to disk (see FAILURES.md F008b).
    """
    files: list[dict] = []
    n_skipped = 0
    for rel, src in sorted(pairs, key=lambda kv: kv[0]):
        if not src or len(src) > max_bytes:
            n_skipped += 1
            continue
        facts = parse_file(Path(rel), rel, lang, src)
        files.append(facts.to_dict())
    n_ok = sum(1 for f in files if f["parse_ok"] and f["error"] == "")
    n_err = sum(1 for f in files if f["error"] == "has_error")
    return {
        "lang": lang,
        "n_files": len(files),
        "n_parse_clean": n_ok,
        "n_parse_has_error": n_err,
        "n_no_parser": sum(1 for f in files if f["error"] == "no_parser"),
        "n_skipped": n_skipped,
        "files": files,
    }


def parse_repo(root: Path, lang: str, exts: set[str] | None = None,
               max_bytes: int = MAX_FILE_BYTES) -> dict:
    """Parse every source file under `root` (disk-based; delegates to parse_sources)."""
    exts = exts or SRC_EXT.get(lang, set())

    def _pairs():
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            try:
                rel = str(p.relative_to(root))
            except ValueError:
                continue
            try:
                yield (rel, p.read_bytes())
            except Exception:  # noqa: BLE001
                continue

    return parse_sources(_pairs(), lang, max_bytes=max_bytes)


def index_stats(idx: dict) -> dict:
    files = idx["files"]
    n_def = sum(len(f["defs"]) for f in files)
    n_call = sum(len(f["calls"]) for f in files)
    n_imp = sum(len(f["imports"]) for f in files)
    n_files_with_defs = sum(1 for f in files if f["defs"])
    return {
        "lang": idx["lang"], "n_files": idx["n_files"],
        "n_defs": n_def, "n_calls": n_call, "n_imports": n_imp,
        "files_with_defs": n_files_with_defs,
        "frac_files_with_defs": round(n_files_with_defs / max(1, idx["n_files"]), 3),
        "n_parse_has_error": idx["n_parse_has_error"],
        "n_no_parser": idx["n_no_parser"],
    }


if __name__ == "__main__":
    # smoke test: parse this repo's own python files
    root = Path(__file__).resolve().parent
    idx = parse_repo(root, "python")
    print(json.dumps(index_stats(idx), indent=2))
    for f in idx["files"][:3]:
        print(f["path"], [d["name"] for d in f["defs"]][:6], f["imports"][:2])
