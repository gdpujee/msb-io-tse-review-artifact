from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

from dataset import QUERY_PROTOCOL, TEST_FILTER_PROTOCOL, _looks_test, build_query  # noqa: E402
from config import RAW_DIR, SKIP_LARGE, TEST_PATH_HINTS  # noqa: E402
from run_experiment import eval_instance  # noqa: E402
from stats_v2 import exact_mcnemar, rank_biserial  # noqa: E402


class QueryProtocolTests(unittest.TestCase):
    def test_pr_text_and_hints_never_enter_query(self):
        row = {
            "title": "PR fixes secret/File.py",
            "body": "The solution edits secret/File.py",
            "hints": "secret/File.py",
            "resolved_issues": [{"number": 7, "title": "Crash on startup", "body": "Stack trace"}],
        }
        query, stats = build_query(row)
        self.assertEqual(query, "Crash on startup\n\nStack trace")
        self.assertNotIn("secret/File.py", query)
        self.assertEqual(stats["query_protocol"], QUERY_PROTOCOL)
        self.assertEqual(stats["query_source"], "resolved_issues")

    def test_problem_statement_is_exclusive_source(self):
        row = {
            "title": "placeholder",
            "body": "placeholder",
            "problem_statement": "Observed failure before the fix",
            "resolved_issues": [{"title": "duplicate", "body": "duplicate body"}],
        }
        query, stats = build_query(row)
        self.assertEqual(query, "Observed failure before the fix")
        self.assertEqual(stats["query_source"], "problem_statement")


class EvaluationProtocolTests(unittest.TestCase):
    def test_unreachable_gold_penalizes_ap_but_not_any_hit(self):
        doc = {
            "query": "Please inspect src/a.py",
            "gold_files": ["src/a.py", "src/new.py"],
            "test_files": [],
        }
        metrics, info = eval_instance(doc, ["src/a.py", "src/b.py"], {"src/a.py", "src/b.py"})
        self.assertEqual(metrics.hit_at[1], 1)
        self.assertEqual(metrics.n_gold, 2)
        self.assertEqual(metrics.n_gold_reachable, 1)
        self.assertEqual(metrics.n_unreachable, 1)
        self.assertEqual(metrics.ap, 0.5)
        self.assertEqual(info["reachable_ap"], 1.0)
        self.assertTrue(info["query_mentions_gold_path"])
        self.assertEqual(info["all_hit@1"], 0)


class StatisticsTests(unittest.TestCase):
    def test_exact_mcnemar_uses_only_discordant_pairs(self):
        p_value, n = exact_mcnemar([1, 1, 1, 0], [0, 0, 0, 0])
        self.assertEqual(n, 3)
        self.assertAlmostEqual(p_value, 0.25)

    def test_rank_biserial_direction(self):
        self.assertEqual(rank_biserial([1, 2, 3], [0, 1, 2]), 1.0)
        self.assertEqual(rank_biserial([0, 1, 2], [1, 2, 3]), -1.0)


class DatasetScopeTests(unittest.TestCase):
    def test_declared_exclusions_match_local_scope(self):
        """An included local file must never remain in the default skip list."""
        for remote_path in SKIP_LARGE:
            lang, name = remote_path.split("/", 1)
            self.assertFalse((RAW_DIR / f"{lang}__{name}").exists(), remote_path)


class TestPathProtocolTests(unittest.TestCase):
    def test_component_aware_conventions_are_excluded(self):
        self.assertEqual(TEST_FILTER_PROTOCOL, "component_aware_test_filter_v6")
        paths = (
            "app/src/androidTest/java/FooTest.java",
            "module/src/integration-test/java/Foo.java",
            "analyzer/src/funTest/kotlin/AnalyzerFunTest.kt",
            "crates/clap_test/src/lib.rs",
            "src/widget.spec.tsx",
            "grep-searcher/src/testutil.rs",
            "programs/bench.c",
            "interop/test_utils.go",
            "projects/XCode/OCTest/OCTest/TestObj.h",
            "astropy/nddata/_testing.py",
        )
        for path in paths:
            self.assertTrue(_looks_test(path, TEST_PATH_HINTS), path)

    def test_test_substrings_inside_words_are_not_new_false_positives(self):
        self.assertFalse(_looks_test("src/main/java/Latest.java", TEST_PATH_HINTS))
        self.assertFalse(_looks_test("src/contest/results.py", TEST_PATH_HINTS))
        self.assertFalse(_looks_test("astropy/coordinates/spectral_coordinate.py", TEST_PATH_HINTS))
        self.assertFalse(_looks_test("src/specialized/specification.py", TEST_PATH_HINTS))
        self.assertFalse(_looks_test("detekt-core/src/main/ProcessingSpecSettingsBridge.kt", TEST_PATH_HINTS))
        self.assertFalse(_looks_test("include/internal/catch_test_spec.cpp", TEST_PATH_HINTS))
        self.assertFalse(_looks_test("src/_pytest/unittest.py", TEST_PATH_HINTS))


if __name__ == "__main__":
    unittest.main()
