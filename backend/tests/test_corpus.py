"""Unit tests for harness.corpus — registry, provenance, cache paths.

No network, no API key, no audio device. The corpus module must be importable
with no key, so `gnani` is imported lazily inside ensure(); the TTS test injects
a stub module instead of touching the real client.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

from harness import corpus

BACKEND = Path(__file__).resolve().parents[1]


class RegistryTest(unittest.TestCase):
    def test_hindi_corpus_lookup(self):
        entry = corpus.get("hi-IN")
        self.assertEqual(len(entry["texts"]), 10)
        self.assertIn("मेरा नाम गौतम कुमार शर्मा है।", entry["texts"])
        self.assertEqual(corpus.REFERENCE_TEXTS, entry["texts"])

    def test_bengali_corpus_lookup(self):
        entry = corpus.get("bn-IN")
        self.assertGreaterEqual(len(entry["texts"]), 8)
        self.assertLessEqual(len(entry["texts"]), 10)
        self.assertEqual(entry["voice"], "Shivani")

    def test_every_language_has_8_to_10_unique_sentences(self):
        for lang in ("hi-IN", "bn-IN"):
            texts = corpus.get(lang)["texts"]
            self.assertGreaterEqual(len(texts), 8, lang)
            self.assertLessEqual(len(texts), 10, lang)
            self.assertEqual(len(set(texts)), len(texts), f"duplicate in {lang}")

    def test_bengali_covers_the_everyday_relay_turns(self):
        joined = " ".join(corpus.get("bn-IN")["texts"])
        for keyword in ("নাম", "টাকা", "অ্যাপয়েন্টমেন্ট", "আবার", "আস্তে"):
            self.assertIn(keyword, joined)

    def test_bengali_numbers_are_words_not_digits(self):
        # TTS reads digits by its own rules; the reference must be the spoken
        # form, and wer.normalize only folds Devanagari digits.
        for text in corpus.get("bn-IN")["texts"]:
            self.assertFalse(any(c.isdigit() for c in text), text)
            self.assertFalse(any("\u09e6" <= c <= "\u09ef" for c in text), text)

    def test_provenance_is_recorded_and_not_claimed_as_checked(self):
        for lang in ("hi-IN", "bn-IN"):
            entry = corpus.get(lang)
            self.assertEqual(entry["author"], "assistant")
            self.assertIsNone(entry["checked_by"])
            self.assertTrue(entry["note"])
            self.assertTrue(corpus.is_provisional(entry))

    def test_unknown_language_raises_a_clear_error(self):
        with self.assertRaises(ValueError) as ctx:
            corpus.get("ta-IN")
        message = str(ctx.exception)
        self.assertIn("ta-IN", message)
        self.assertIn("hi-IN", message)
        self.assertIn("bn-IN", message)


class CachePathTest(unittest.TestCase):
    def test_path_includes_language(self):
        hi = corpus._path("नमस्ते", "Shivani", 16000, "hi-IN", "cache/corpus")
        bn = corpus._path("নমস্কার", "Shivani", 16000, "bn-IN", "cache/corpus")
        self.assertIn("hi-IN", os.path.basename(hi))
        self.assertIn("bn-IN", os.path.basename(bn))
        self.assertEqual(os.path.dirname(hi), "cache/corpus")

    def test_same_text_in_two_languages_does_not_collide(self):
        hi = corpus._path("x", "Shivani", 16000, "hi-IN", "cache/corpus")
        bn = corpus._path("x", "Shivani", 16000, "bn-IN", "cache/corpus")
        self.assertNotEqual(hi, bn)

    def test_ensure_passes_language_to_tts_and_to_the_cache_path(self):
        calls = []
        fake = types.ModuleType("gnani")
        fake.tts = lambda text, **kw: calls.append((text, kw))

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(sys.modules, {"gnani": fake}):
                pairs = corpus.ensure(["আমার নাম সৌরভ।"], out_dir=tmp,
                                      lang="bn-IN")

        self.assertEqual(len(pairs), 1)
        path, text = pairs[0]
        self.assertTrue(path.startswith(tmp))
        self.assertIn("bn-IN", os.path.basename(path))
        self.assertEqual(calls[0][0], text)
        self.assertEqual(calls[0][1]["lang"], "bn-IN")


class LazyImportTest(unittest.TestCase):
    def test_importing_corpus_does_not_import_gnani(self):
        """CI has no key; importing the registry must not trigger gnani.py."""
        code = textwrap.dedent("""
            import sys

            class BlockGnani:
                def find_spec(self, name, path=None, target=None):
                    if name == "gnani":
                        raise RuntimeError("harness.corpus imported gnani eagerly")

            sys.meta_path.insert(0, BlockGnani())
            import harness.corpus
            print("imported")
        """)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(BACKEND) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run([sys.executable, "-c", code], cwd=BACKEND,
                              env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("imported", proc.stdout)


if __name__ == "__main__":
    unittest.main()
