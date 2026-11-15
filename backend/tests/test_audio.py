"""Unit tests for audio.py — frame maths and G.711. No network, no key."""
import os
import tempfile
import unittest
import wave

import numpy as np

import audio


class FramesTest(unittest.TestCase):
    def test_exact_multiple(self):
        self.assertEqual(audio.frames(b"\x00" * 2048), [b"\x00" * 1024] * 2)

    def test_short_tail_is_padded(self):
        out = audio.frames(b"\x01" * 1100)
        self.assertEqual([len(f) for f in out], [1024, 1024])
        self.assertEqual(out[1][:76], b"\x01" * 76)
        self.assertEqual(out[1][76:], b"\x00" * (1024 - 76))

    def test_empty(self):
        self.assertEqual(audio.frames(b""), [])

    def test_samples_per_frame_constant(self):
        self.assertEqual(audio.SAMPLES_PER_FRAME * 2, audio.FRAME_BYTES)


class ULawTest(unittest.TestCase):
    def test_round_trip_preserves_waveform(self):
        t = np.linspace(0, 0.2, 3200, endpoint=False)
        pcm = (np.sin(2 * np.pi * 440 * t) * 12000).astype(np.int16).tobytes()
        back = np.frombuffer(audio.ulaw_to_pcm16(audio.pcm16_to_ulaw(pcm)),
                             dtype=np.int16).astype(float)
        ref = np.frombuffer(pcm, dtype=np.int16).astype(float)
        self.assertGreater(np.corrcoef(ref, back)[0, 1], 0.999)

    def test_round_trip_is_close_in_amplitude(self):
        pcm = (np.random.default_rng(0).normal(0, 5000, 2000)).astype(np.int16).tobytes()
        back = np.frombuffer(audio.ulaw_to_pcm16(audio.pcm16_to_ulaw(pcm)), dtype=np.int16)
        self.assertLess(abs(int(back.std()) - 5000) / 5000, 0.05)


class WavTest(unittest.TestCase):
    def test_duration_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.wav")
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(8000)
                w.writeframes(b"\x00" * (8000 * 2))     # 1 second
            self.assertAlmostEqual(audio.duration_s(path), 1.0, places=3)
            pcm, rate = audio.read_wav(path)
            self.assertEqual(rate, 8000)
            self.assertEqual(len(pcm), 16000)


if __name__ == "__main__":
    unittest.main()
