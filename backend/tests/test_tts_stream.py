"""Talk mode's reply path: Timbre's PCM into a sink instead of the speaker.

`stream_pcm` is what the page hears. These tests patch the SSE generator (no
network, no credits) and the clone fetch, and assert the three properties the
call depends on: chunks arrive as they are produced, a complete clip is cached
under the same key `speak` uses, and a failed stream is never cached.
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

PCM = b"\x01\x00" * 3000            # 6000 bytes of s16le


class StreamPcmTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pashyanti-stream-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        old_cache, old_embedding = tts.CACHE_DIR, tts.EMBEDDING
        tts.CACHE_DIR = self.tmp
        self.addCleanup(setattr, tts, "CACHE_DIR", old_cache)
        self.addCleanup(setattr, tts, "EMBEDDING", old_embedding)
        self.emitted = []

    async def emit(self, chunk):
        self.emitted.append(chunk)

    def cached_path(self, text, mode=tts.MODE_DEFAULT):
        voice = tts.MODE_CLONED if mode == tts.MODE_CLONED else tts.VOICE
        model = tts.MODEL_CLONE if mode == tts.MODE_CLONED else tts.MODEL
        return tts._key(text, voice, model, tts.RATE, mode)

    # --- cached clips ----------------------------------------------------

    async def test_a_cached_clip_is_emitted_without_synthesising(self):
        path = self.cached_path("hello")
        with open(path, "wb") as f:
            f.write(PCM)

        with patch.object(tts, "_sse_stream") as sse:
            ttfa, cached = await tts.stream_pcm("hello", self.emit)

        self.assertEqual((ttfa, cached), (0, True))
        self.assertEqual(b"".join(self.emitted), PCM)
        sse.assert_not_called()

    async def test_a_large_cached_clip_arrives_in_bounded_chunks(self):
        path = self.cached_path("long")
        with open(path, "wb") as f:
            f.write(PCM * 50)           # 300 kB

        with patch.object(tts, "_sse_stream"):
            await tts.stream_pcm("long", self.emit)

        self.assertEqual(b"".join(self.emitted), PCM * 50)
        self.assertGreater(len(self.emitted), 1)
        self.assertTrue(all(len(chunk) <= 32 * 1024 for chunk in self.emitted))

    async def test_a_cached_clone_is_emitted_without_calling_the_api(self):
        tts.EMBEDDING = {"embedding": "stub"}
        path = self.cached_path("hello", tts.MODE_CLONED)
        with open(path, "wb") as f:
            f.write(PCM)

        with patch.object(tts, "_clone_and_cache") as clone:
            ttfa, cached = await tts.stream_pcm(
                "hello", self.emit, mode=tts.MODE_CLONED)

        self.assertEqual((ttfa, cached), (0, True))
        self.assertEqual(b"".join(self.emitted), PCM)
        clone.assert_not_called()

    # --- the live stream -------------------------------------------------

    async def test_chunks_are_emitted_as_the_stream_produces_them(self):
        chunks = [b"\x01\x00" * 512, b"\x02\x00" * 512, b"\x03\x00" * 512]

        def fake_sse(text, voice, model, rate, lang):
            self.assertEqual((text, voice, model, rate, lang),
                             ("hello", tts.VOICE, tts.MODEL, tts.RATE,
                              tts.DEFAULT_LANG))
            yield from chunks

        with patch.object(tts, "_sse_stream", fake_sse):
            ttfa, cached = await tts.stream_pcm("hello", self.emit)

        self.assertEqual(self.emitted, chunks)
        self.assertFalse(cached)
        self.assertIsInstance(ttfa, int)

    async def test_a_complete_stream_is_cached_for_the_next_tap(self):
        with patch.object(tts, "_sse_stream", lambda *a: iter([PCM])):
            await tts.stream_pcm("hello", self.emit)

        path = self.cached_path("hello")
        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), PCM)

        self.emitted.clear()
        with patch.object(tts, "_sse_stream") as sse:
            ttfa, cached = await tts.stream_pcm("hello", self.emit)
        self.assertEqual((ttfa, cached), (0, True))
        sse.assert_not_called()

    async def test_a_failed_stream_is_not_cached_and_raises(self):
        def broken(text, voice, model, rate, lang):
            yield PCM
            raise RuntimeError("TTS 500: technical difficulties")

        with patch.object(tts, "_sse_stream", broken):
            with self.assertRaises(RuntimeError):
                await tts.stream_pcm("hello", self.emit)

        self.assertEqual(self.emitted, [PCM])       # what arrived did play
        self.assertFalse(os.path.exists(self.cached_path("hello")))

    async def test_a_stream_that_produces_no_audio_is_retried_once(self):
        # Timbre intermittently answers 200 with a stream that carries no audio.
        # The caller must still hear the reply, so one silent attempt is retried.
        calls = []

        def flaky(text, voice, model, rate, lang):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("TTS produced no audio")
            yield PCM

        with patch.object(tts, "_sse_stream", flaky):
            await tts.stream_pcm("retry me", self.emit)

        self.assertEqual(len(calls), 2)
        self.assertEqual(self.emitted, [PCM])
        self.assertTrue(os.path.exists(self.cached_path("retry me")))

    async def test_a_stream_that_dies_after_audio_is_not_retried(self):
        # Once audio has left, a retry would repeat the sentence out loud.
        calls = []

        def dying(text, voice, model, rate, lang):
            calls.append(1)
            yield PCM
            raise RuntimeError("connection reset")

        with patch.object(tts, "_sse_stream", dying):
            with self.assertRaises(RuntimeError):
                await tts.stream_pcm("partial", self.emit)

        self.assertEqual(len(calls), 1)
        self.assertEqual(self.emitted, [PCM])
        self.assertFalse(os.path.exists(self.cached_path("partial")))

    async def test_the_clone_endpoint_path_emits_the_whole_clip(self):
        tts.EMBEDDING = {"embedding": "stub"}

        def fake_clone(text, rate, lang):
            self.assertEqual((text, lang), ("hello", tts.DEFAULT_LANG))
            return PCM

        with patch.object(tts, "_clone_and_cache", fake_clone):
            ttfa, cached = await tts.stream_pcm(
                "hello", self.emit, mode=tts.MODE_CLONED)

        self.assertEqual(b"".join(self.emitted), PCM)
        self.assertFalse(cached)
        self.assertIsInstance(ttfa, int)

    async def test_clone_without_an_embedding_uses_the_default_voice(self):
        tts.EMBEDDING = None
        with patch.object(tts, "_sse_stream", lambda *a: iter([PCM])), \
             patch.object(tts, "_clone_and_cache") as clone:
            await tts.stream_pcm("hello", self.emit, mode=tts.MODE_CLONED)

        clone.assert_not_called()
        self.assertEqual(b"".join(self.emitted), PCM)

    async def test_a_dead_socket_mid_stream_raises_instead_of_hanging(self):
        def slow(text, voice, model, rate, lang):
            for _ in range(50):
                yield PCM

        async def drop(_chunk):
            raise ConnectionResetError("page gone")

        with patch.object(tts, "_sse_stream", slow):
            with self.assertRaises(ConnectionResetError):
                await tts.stream_pcm("hello", drop)


if __name__ == "__main__":
    unittest.main()


def _sse_lines(*events):
    out = []
    for event in events:
        out.append(b"event: chunk")
        out.append(b"data: " + json.dumps(event).encode())
        out.append(b"")
    return out


class ParseSseTest(unittest.TestCase):
    """Completeness, not just arrival: a stream that stops early is not a reply."""

    def test_a_finished_stream_yields_its_audio(self):
        encoded = base64.b64encode(PCM).decode()
        chunks = list(tts.parse_sse_lines(_sse_lines(
            {"chunk_index": 0, "audio": encoded},
            {"chunk_index": 1, "audio": "", "is_final": True})))
        self.assertEqual(b"".join(chunks), PCM)

    def test_a_stream_that_stops_without_is_final_raises(self):
        encoded = base64.b64encode(PCM).decode()
        with self.assertRaises(RuntimeError) as caught:
            list(tts.parse_sse_lines(_sse_lines({"chunk_index": 0,
                                                 "audio": encoded})))
        self.assertIn("is_final", str(caught.exception))

    def test_a_stream_with_no_audio_raises(self):
        with self.assertRaises(RuntimeError) as caught:
            list(tts.parse_sse_lines(_sse_lines(
                {"chunk_index": 0, "audio": "", "is_final": True})))
        self.assertIn("no audio", str(caught.exception))

    def test_noise_lines_are_ignored(self):
        encoded = base64.b64encode(PCM).decode()
        lines = [b": keep-alive", b"event: chunk", b"",
                 b"data: " + json.dumps({"audio": encoded}).encode(), b"",
                 b"data: {not json", b"",
                 b"data: " + json.dumps({"is_final": True}).encode()]
        self.assertEqual(b"".join(tts.parse_sse_lines(lines)), PCM)
