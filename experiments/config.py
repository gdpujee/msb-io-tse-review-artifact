"""Project configuration. Paths are absolute and derived from PROJECT_ROOT."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"              # downloaded jsonl from HF
SRC_DIR = DATA_DIR / "src"              # temporary extracted repo sources (deleted after parse)
INDEX_DIR = DATA_DIR / "index"          # parsed structural representations
RESULTS_DIR = PROJECT_ROOT / "results"

for _d in (RAW_DIR, SRC_DIR, INDEX_DIR, RESULTS_DIR / "raw", RESULTS_DIR / "processed",
           RESULTS_DIR / "tables", RESULTS_DIR / "figures"):
    _d.mkdir(parents=True, exist_ok=True)

HF_DATASET_REVISION = "56ff018c04a38e27ada1e9d0a6d5839a51f88f0d"
HF_BASE = ("https://huggingface.co/datasets/ByteDance-Seed/Multi-SWE-bench/resolve/"
           f"{HF_DATASET_REVISION}")

# HF file listing measured on 2026-09-13 (sizes in MB). We skip very large repos
# to keep disk usage bounded; decision recorded in DECISIONS.md.
LANG_FILES = {
    "c":       ["facebook__zstd_dataset.jsonl", "jqlang__jq_dataset.jsonl", "ponylang__ponyc_dataset.jsonl"],
    "cpp":     ["catchorg__Catch2_dataset.jsonl", "fmtlib__fmt_dataset.jsonl",
                "nlohmann__json_dataset.jsonl", "simdjson__simdjson_dataset.jsonl",
                "yhirose__cpp-httplib_dataset.jsonl"],
    "go":      ["cli__cli_dataset.jsonl", "grpc__grpc-go_dataset.jsonl", "zeromicro__go-zero_dataset.jsonl"],
    "java":    ["alibaba__fastjson2_dataset.jsonl", "apache__dubbo_dataset.jsonl",
                "elastic__logstash_dataset.jsonl", "fasterxml__jackson-core_dataset.jsonl",
                "fasterxml__jackson-databind_dataset.jsonl", "fasterxml__jackson-dataformat-xml_dataset.jsonl",
                "google__gson_dataset.jsonl", "googlecontainertools__jib_dataset.jsonl",
                "mockito__mockito_dataset.jsonl"],
    "js":      ["Kong__insomnia_dataset.jsonl", "anuraghazra__github-readme-stats_dataset.jsonl",
                "axios__axios_dataset.jsonl", "expressjs__express_dataset.jsonl",
                "iamkun__dayjs_dataset.jsonl", "sveltejs__svelte_dataset.jsonl"],
    "kotlin":  ["GradleUp__shadow_dataset.jsonl", "Hannah-Sten__TeXiFy-IDEA_dataset.jsonl",
                "Kotlin__dataframe_dataset.jsonl", "ankidroid__Anki-Android_dataset.jsonl",
                "detekt__detekt_dataset.jsonl", "oss-review-toolkit__ort_dataset.jsonl",
                "pinterest__ktlint_dataset.jsonl", "square__okhttp_dataset.jsonl"],
    "python":  ["multi_swe_bench_python.jsonl"],
    "rust":    ["BurntSushi__ripgrep_dataset.jsonl", "clap-rs__clap_dataset.jsonl",
                "nushell__nushell_dataset.jsonl", "rayon-rs__rayon_dataset.jsonl",
                "serde-rs__serde_dataset.jsonl", "sharkdp__bat_dataset.jsonl",
                "sharkdp__fd_dataset.jsonl", "tokio-rs__bytes_dataset.jsonl",
                "tokio-rs__tokio_dataset.jsonl", "tokio-rs__tracing_dataset.jsonl"],
    "ts":      ["darkreader__darkreader_dataset.jsonl", "mui__material-ui_dataset.jsonl",
                "vuejs__core_dataset.jsonl"],
}

# Dataset files deliberately excluded because their JSONL downloads are hundreds
# of MB. This list must match the actual local scope; go/cli is included in V2.
SKIP_LARGE = {
    "ts/mui__material-ui_dataset.jsonl": 749.8,
    "js/sveltejs__svelte_dataset.jsonl": 503.2,
}

# tree-sitter language binding per our language key
TS_LANG = {
    "c": "tree_sitter_c",
    "cpp": "tree_sitter_cpp",
    "go": "tree_sitter_go",
    "java": "tree_sitter_java",
    "js": "tree_sitter_javascript",
    "python": "tree_sitter_python",
    "rust": "tree_sitter_rust",
    "ts": "tree_sitter_typescript",
    "kotlin": None,  # no maintained pip binding known; handled by fallback
}

# file extensions we consider source (used when walking a repo)
SRC_EXT = {
    "c": {".c", ".h"},
    "cpp": {".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx"},
    "go": {".go"},
    "java": {".java"},
    "js": {".js", ".jsx", ".mjs", ".cjs"},
    "python": {".py"},
    "rust": {".rs"},
    "ts": {".ts", ".tsx"},
    "kotlin": {".kt", ".kts"},
}

# heuristics for test-file detection (used to exclude test files from candidates
# and to study the effect of that decision on results -- see RQ4)
TEST_PATH_HINTS = ("test", "tests", "spec", "specs", "__tests__", "testing",
                   "conftest", "fixture", "fixtures", "benchmark", "bench")
