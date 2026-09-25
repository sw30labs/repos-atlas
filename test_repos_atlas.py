#!/usr/bin/env python3
"""Test the pure logic of repos-atlas: parsing, formatting, pruning, prompts.

No network, no git walk. Everything here touches only the stdlib and the
importable functions in survey.py / atlas.py / review.py.

  python3 -m unittest -v
"""
import json, os, tempfile, unittest
from unittest import mock

import atlas
import survey
import review


class TestFormatting(unittest.TestCase):
    def test_human_units(self):
        self.assertEqual(atlas.human(None), "-")
        self.assertEqual(atlas.human(0), "0")
        self.assertEqual(atlas.human(999), "999")
        self.assertEqual(atlas.human(1_234), "1.2k")
        self.assertEqual(atlas.human(2_000_000), "2.0M")

    def test_bytes_units(self):
        self.assertEqual(atlas.bytes_h(0), "0B")
        self.assertEqual(atlas.bytes_h(1023), "1023B")
        self.assertEqual(atlas.bytes_h(2048), "2KB")
        self.assertEqual(atlas.bytes_h(3 * 1024 * 1024), "3MB")

    def test_esc(self):
        self.assertEqual(atlas.esc('<script>&"'), "&lt;script&gt;&amp;&quot;")
        self.assertEqual(atlas.esc(None), "")


class TestRecency(unittest.TestCase):
    def test_days_since_invalid(self):
        self.assertIsNone(atlas.days_since(""))
        self.assertIsNone(atlas.days_since("not-a-date"))
        self.assertIsNone(atlas.days_since(None))

    def test_days_since_utc_z_suffix(self):
        y = atlas.days_since("2020-01-01T00:00:00+00:00")
        self.assertIsNotNone(y)
        self.assertGreater(y, 500)

    def test_bucket_boundaries(self):
        self.assertEqual(atlas.bucket(7), 0)     # this week
        self.assertEqual(atlas.bucket(31), 2)    # this quarter (30 < x <= 90)
        self.assertEqual(atlas.bucket(None), atlas.NO_HISTORY)

    def test_bucket_monotonic(self):
        seq = [atlas.bucket(d) for d in (1, 29, 30, 89, 364, 400, 10**9 + 1)]
        self.assertEqual(seq, sorted(seq))  # older -> larger bucket, never gets smaller


class TestSparkline(unittest.TestCase):
    def test_spark_zero_is_safe(self):
        r = {"months": {}}
        s = atlas.spark(r)
        self.assertIn('<span class="spark"', s)
        self.assertIn("<i", s)  # renders the full window of bars

    def test_spark_scales_to_max(self):
        r = {"months": {"2026-01": 5, "2026-02": 10}}
        # force NOW so the window is deterministic
        with mock.patch.object(atlas, "NOW",
                               atlas.datetime.datetime(2026, 3, 1)):
            s = atlas.spark(r, tail=3)
        # the richest month must hit ~100% height
        self.assertIn("height:100%", s)
        self.assertIn("opacity:0.25", s)  # empty bars are dimmed


class TestSurveyPruning(unittest.TestCase):
    def test_skip_names_and_dotdirs(self):
        entries = ["node_modules", "vendor", ".git", ".cache", ".github", "src", "build"]
        kept = survey.prune("/x", entries)
        self.assertIn("src", kept)
        self.assertIn(".github", kept)      # .github is allowed through
        self.assertNotIn("node_modules", kept)
        self.assertNotIn("vendor", kept)
        self.assertNotIn(".git", kept)
        self.assertNotIn(".cache", kept)
        self.assertNotIn("build", kept)

    def test_egg_info_pruned(self):
        kept = survey.prune("/x", ["foo.egg-info", "bar"])
        self.assertEqual(kept, ["bar"])

    def test_is_env_detects_markers(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(survey.is_env(td))
            with open(os.path.join(td, "pyvenv.cfg"), "w") as f:
                f.write("x")
            self.assertTrue(survey.is_env(td))

    def test_env_pruned_from_walk(self):
        with tempfile.TemporaryDirectory() as td:
            env = os.path.join(td, "myenv")
            os.makedirs(env)
            with open(os.path.join(env, "pyvenv.cfg"), "w") as f:
                f.write("x")
            self.assertNotIn("myenv", survey.prune(td, os.listdir(td)))


class TestReadmeBlurb(unittest.TestCase):
    def test_skips_headings_and_images(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "README.md"), "w") as f:
                f.write("# Title\n![logo](x.png)\n\nA real sentence about the thing.\n")
            b = survey.readme_blurb(td)
            self.assertIn("A real sentence", b)
            self.assertNotIn("Title", b)
            self.assertNotIn("logo", b)

    def test_no_readme(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(survey.readme_blurb(td), "")


class TestRunNoOptionalLocks(unittest.TestCase):
    def test_git_gets_no_optional_locks(self):
        with mock.patch.object(survey.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="  3\n")
            out = survey.run(["git", "rev-list", "--count", "HEAD"], "/tmp")
            self.assertEqual(out, "3")
            args = run.call_args[0][0]
            self.assertEqual(args[0], "git")
            self.assertIn("--no-optional-locks", args)

    def test_nonzero_returns_empty(self):
        with mock.patch.object(survey.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=128, stdout="fatal\n")
            self.assertEqual(survey.run(["git", "x"], "/tmp"), "")


class TestExtractJson(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(review.extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_and_padded(self):
        self.assertEqual(review.extract_json('Output:\n```json\n{"a": 1}\n```\n-- end'),
                         {"a": 1})

    def test_nested_braces(self):
        self.assertEqual(review.extract_json('here {"a": {"b": [1, 2]}} trailing'),
                         {"a": {"b": [1, 2]}})

    def test_garbage_returns_none(self):
        self.assertIsNone(review.extract_json("no braces here"))
        self.assertIsNone(review.extract_json("{unclosed"))
        self.assertIsNone(review.extract_json("[1, 2]"))


class TestPickBrief(unittest.TestCase):
    def test_bare_object(self):
        obj = {"one_liner": "a thing", "kind": "cli"}
        self.assertEqual(review.pick_brief(obj, "foo"), obj)

    def test_keyed_object(self):
        obj = {"foo": {"one_liner": "a thing"}}
        self.assertEqual(review.pick_brief(obj, "foo")["one_liner"], "a thing")

    def test_wrong_key_returns_none(self):
        self.assertIsNone(review.pick_brief({"bar": {"one_liner": "x"}}, "foo"))

    def test_non_dict_returns_none(self):
        self.assertIsNone(review.pick_brief(["not", "a", "dict"], "foo"))


class TestFingerprint(unittest.TestCase):
    def test_changes_with_evidence(self):
        rec = {"last": "2026-01-01", "commits": 3}
        a = review.fingerprint(rec, "ev1")
        b = review.fingerprint(dict(rec, commits=4), "ev1")
        self.assertNotEqual(a, b)

    def test_stable_hex(self):
        fp = review.fingerprint({"last": "x", "commits": 1}, "ev")
        self.assertRegex(fp, "^[0-9a-f]{16}$")


class TestDomains(unittest.TestCase):
    def test_every_domain_has_a_domain_of_mapping(self):
        for dom, names in atlas.DOMAINS:
            for n in names:
                self.assertEqual(atlas.DOMAIN_OF[n], dom)

    def test_unknown_defaults_to_meta(self):
        self.assertEqual(atlas.DOMAIN_OF.get("does-not-exist", "Meta & Tooling"),
                         "Meta & Tooling")


if __name__ == "__main__":
    unittest.main()
