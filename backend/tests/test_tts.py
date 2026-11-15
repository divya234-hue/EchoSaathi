"""Unit tests for the two voices: dispatch and cache separation, no network.

`sounddevice` is never touched because the blocking helpers are patched, and
`gnani` is never called because the cloned helper is patched too.
"""
import base64
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("GNANI_API_KEY", "test-key-not-used")

import tts  # noqa: E402


class SpeakModeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pashyanti-tts-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        old_cache, old_embedding = tts.CACHE_DIR, tts.EMBEDDING
        tts.CACHE_DIR = self.tmp
        self.addCleanup(setattr, tts, "CACHE_DIR", old_cache)
        self.addCleanup(setattr, tts, "EMBEDDING", old_embedding)

    async def test_default_mode_uses_the_streaming_voice(self):
        tts.EMBEDDING = None
        calls = []

        def fake_stream(text, voice, model, rate, mode, lang):
            calls.append((text, voice, model, rate, lang))
            return 10, os.path.join(tts.CACHE_DIR, "x.pcm")

        with patch.object(tts, "_play_and_cache", fake_stream):
            ttfa, cached = await tts.speak("hello", mode=tts.MODE_DEFAULT)

        self.assertEqual((ttfa, cached), (10, False))
        self.assertEqual(calls, [("hello", tts.VOICE, tts.MODEL, tts.RATE,
                                  tts.DEFAULT_LANG)])

    async def test_cloned_mode_calls_the_clone_endpoint(self):
        tts.EMBEDDING = {"embedding": "stub", "shape": [1, 768]}
        calls = []

        def fake_cloned(text, lang):
            calls.append((text, lang))
            return 12

        with patch.object(tts, "_play_and_cache_cloned", fake_cloned), \
             patch.object(tts, "_play_and_cache") as streamed:
            ttfa, cached = await tts.speak("hello", mode=tts.MODE_CLONED)

        self.assertEqual((ttfa, cached), (12, False))
        self.assertEqual(calls, [("hello", tts.DEFAULT_LANG)])
        streamed.assert_not_called()

    async def test_cloned_without_an_embedding_falls_back_to_default(self):
        tts.EMBEDDING = None
        with patch.object(tts, "_play_and_cache", return_value=(7, "p")) as streamed, \
             patch.object(tts, "_play_and_cache_cloned") as cloned:
            ttfa, cached = await tts.speak("hello", mode=tts.MODE_CLONED)

        self.assertEqual((ttfa, cached), (7, False))
        cloned.assert_not_called()
        streamed.assert_called_once()

    async def test_cached_clone_is_played_without_synthesising(self):
        tts.EMBEDDING = {"embedding": "stub"}
        path = tts._key("hello", tts.MODE_CLONED, tts.MODEL_CLONE, tts.RATE,
                        tts.MODE_CLONED)
        os.makedirs(tts.CACHE_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"\x00\x00")
        with patch.object(tts, "_play_and_cache_cloned") as cloned, \
             patch.object(tts, "_play_cached") as played:
            ttfa, cached = await tts.speak("hello", mode=tts.MODE_CLONED)

        self.assertEqual((ttfa, cached), (0, True))
        cloned.assert_not_called()
        played.assert_called_once_with(path, tts.RATE)


class CacheKeyTest(unittest.TestCase):
    def test_the_two_modes_never_share_a_cache_file(self):
        default = tts._key("same", tts.VOICE, tts.MODEL, tts.RATE,
                           tts.MODE_DEFAULT)
        cloned = tts._key("same", tts.VOICE, tts.MODEL, tts.RATE,
                          tts.MODE_CLONED)
        self.assertNotEqual(default, cloned)

    def test_has_clone_tracks_the_embedding(self):
        with patch.object(tts, "EMBEDDING", None):
            self.assertFalse(tts.has_clone())
        with patch.object(tts, "EMBEDDING", {"embedding": "stub"}):
            self.assertTrue(tts.has_clone())


class LanguageTest(unittest.IsolatedAsyncioTestCase):
    """The reply follows the caller's language, not the UI locale (D-012)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pashyanti-tts-lang-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        old_cache, old_embedding = tts.CACHE_DIR, tts.EMBEDDING
        tts.CACHE_DIR = self.tmp
        self.addCleanup(setattr, tts, "CACHE_DIR", old_cache)
        self.addCleanup(setattr, tts, "EMBEDDING", old_embedding)

    def test_the_language_reaches_the_sse_payload(self):
        captured = {}

        class Response:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_lines(self):
                # A reply is only a reply if the stream finished: the payload
                # test still has to look like a real one.
                audio = base64.b64encode(b"\x01\x00" * 64).decode()
                return iter([
                    b"data: " + json.dumps({"audio": audio}).encode(),
                    b"data: " + json.dumps({"is_final": True}).encode()])

        def fake_post(url, headers=None, json=None, stream=None, timeout=None):
            captured.update(json)
            return Response()

        with patch.object(tts._SESSION, "post", fake_post):
            list(tts._sse_stream("নমস্কার", tts.VOICE, tts.MODEL, tts.RATE,
                                 "bn-IN"))

        self.assertEqual(captured["language"], "bn-IN")
        self.assertEqual(captured["text"], "নমস্কার")

    def test_a_bare_code_gets_its_region_and_the_default_is_hindi(self):
        self.assertEqual(tts.reply_language("bn"), "bn-IN")
        self.assertEqual(tts.reply_language("hi-IN"), "hi-IN")
        self.assertEqual(tts.reply_language("ta"), "ta-IN")
        self.assertEqual(tts.reply_language(None), "hi-IN")
        self.assertEqual(tts.reply_language("   "), "hi-IN")

    def test_the_cache_key_separates_languages(self):
        hi = tts._key("same", tts.VOICE, tts.MODEL, tts.RATE,
                      tts.MODE_DEFAULT, "hi-IN")
        bn = tts._key("same", tts.VOICE, tts.MODEL, tts.RATE,
                      tts.MODE_DEFAULT, "bn-IN")
        again = tts._key("same", tts.VOICE, tts.MODEL, tts.RATE,
                         tts.MODE_DEFAULT, "hi-IN")
        self.assertNotEqual(hi, bn)
        self.assertEqual(hi, again)

    async def test_a_non_hindi_reply_does_not_use_the_hindi_clone(self):
        tts.EMBEDDING = {"embedding": "stub"}
        langs = []

        def fake_stream(text, voice, model, rate, mode, lang):
            langs.append(lang)
            return 9, "p"

        with patch.object(tts, "_play_and_cache", fake_stream), \
             patch.object(tts, "_play_and_cache_cloned") as cloned:
            ttfa, cached = await tts.speak("হ্যাঁ", mode=tts.MODE_CLONED,
                                           lang="bn-IN")

        self.assertEqual((ttfa, cached), (9, False))
        cloned.assert_not_called()
        self.assertEqual(langs, ["bn-IN"])

    async def test_a_hindi_reply_still_uses_the_clone(self):
        tts.EMBEDDING = {"embedding": "stub"}
        with patch.object(tts, "_play_and_cache_cloned", return_value=5) as cloned, \
             patch.object(tts, "_play_and_cache") as streamed:
            ttfa, cached = await tts.speak("ठीक है", mode=tts.MODE_CLONED,
                                           lang="hi-IN")

        self.assertEqual((ttfa, cached), (5, False))
        cloned.assert_called_once_with("ठीक है", "hi-IN")
        streamed.assert_not_called()

    def test_effective_mode_rules(self):
        with patch.object(tts, "EMBEDDING", {"embedding": "stub"}):
            self.assertEqual(tts.effective_mode(tts.MODE_CLONED, "hi-IN"),
                             tts.MODE_CLONED)
            self.assertEqual(tts.effective_mode(tts.MODE_CLONED, "hi"),
                             tts.MODE_CLONED)
            self.assertEqual(tts.effective_mode(tts.MODE_CLONED, "bn-IN"),
                             tts.MODE_DEFAULT)
        with patch.object(tts, "EMBEDDING", None):
            self.assertEqual(tts.effective_mode(tts.MODE_CLONED, "hi-IN"),
                             tts.MODE_DEFAULT)


if __name__ == "__main__":
    unittest.main()
