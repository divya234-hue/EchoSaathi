"""Live API test — skipped unless you ask for it.

It spends credits, so it never runs in CI:

    cd divya/backend
    RUN_LIVE=1 .venv/bin/python -m unittest tests.test_live_api -v

What it proves that the stubs cannot: the key works, Timbre returns a WAV whose
header we can patch, and Prisma transcribes our own synthesis back.
"""
import os
import tempfile
import unittest
import wave

from gnani import stt_file, tts

PHRASE = "नमस्ते, मैं पश्यन्ती हूँ।"


@unittest.skipUnless(os.environ.get("RUN_LIVE") == "1",
                     "set RUN_LIVE=1 to spend credits on a real API call")
class LiveApiTest(unittest.TestCase):
    def test_synthesise_then_transcribe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "roundtrip.wav")
            tts(PHRASE, out=path, rate=16000)

            with wave.open(path) as w:
                seconds = w.getnframes() / w.getframerate()
                self.assertEqual(w.getframerate(), 16000)
            self.assertGreater(seconds, 0.5, "TTS produced almost no audio")

            out = stt_file(path, lang="hi-IN", fmt="verbatim")
            self.assertEqual(out.get("model"), "prisma-v3.0")
            self.assertEqual(out.get("detected_language_code"), "hi-IN")
            self.assertIn("पश्यन्ती", out.get("transcript", ""))


if __name__ == "__main__":
    unittest.main()
