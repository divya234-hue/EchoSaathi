"""Unit tests for the streaming phone-line transform (no microphone, no network).

The rule under test is the 1024-byte one: two 16 kHz frames in, one 8 kHz frame
out, never a 512-byte frame.
"""
import os
import unittest

import numpy as np

os.environ.setdefault("GNANI_API_KEY", "test-key-not-used")

import stt  # noqa: E402
from audio import FRAME_BYTES  # noqa: E402
from harness.phone_line import PhoneLine  # noqa: E402


def tone(freq=1000.0, amp=8000, samples=512, rate=16000):
    t = np.arange(samples) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.int16).tobytes()


def rms(pcm):
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(x ** 2)))


class PhoneLineTest(unittest.TestCase):
    def test_one_frame_produces_no_output_yet(self):
        self.assertEqual(PhoneLine().process(tone()), [])

    def test_two_frames_produce_one_output_frame(self):
        line = PhoneLine()
        self.assertEqual(line.process(tone()), [])
        out = line.process(tone())
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]), FRAME_BYTES)

    def test_four_frames_produce_two_frames(self):
        line = PhoneLine()
        out = []
        for _ in range(4):
            out.extend(line.process(tone()))
        self.assertEqual(len(out), 2)
        for frame in out:
            self.assertEqual(len(frame), FRAME_BYTES)

    def test_wrong_frame_size_is_rejected(self):
        with self.assertRaises(ValueError):
            PhoneLine().process(b"\x00" * 512)

    def test_non_integer_resampling_is_rejected(self):
        with self.assertRaises(ValueError):
            PhoneLine(in_rate=16000, out_rate=11025)

    def test_noise_raises_the_rms(self):
        clean = rms(b"".join(self._feed(PhoneLine(snr_db=None))))
        noisy = rms(b"".join(self._feed(PhoneLine(snr_db=10.0, seed=1))))
        self.assertGreater(noisy, clean)

    def test_a_1khz_tone_still_dominates(self):
        out = b"".join(self._feed(PhoneLine(snr_db=None)))
        x = np.frombuffer(out, dtype=np.int16).astype(np.float64)
        spectrum = np.abs(np.fft.rfft(x))
        freqs = np.fft.rfftfreq(x.size, d=1.0 / 8000)
        peak = freqs[int(np.argmax(spectrum[1:])) + 1]
        self.assertAlmostEqual(peak, 1000.0, delta=20.0)

    @staticmethod
    def _feed(line):
        out = []
        for _ in range(4):
            out.extend(line.process(tone()))
        return out


class MicSessionRateTest(unittest.TestCase):
    def test_phone_line_asks_for_8khz_but_captures_16khz(self):
        mic = stt.MicSession(lambda *args: None, telephony=True)
        self.assertEqual(mic.rate, 16000)
        self.assertEqual(mic.send_rate, 8000)
        self.assertIsNotNone(mic.phone)
        self.assertEqual(
            stt.headers(mic.lang, mic.send_rate, True)["x-sample-rate"], "8000")

    def test_clean_mode_keeps_16khz(self):
        mic = stt.MicSession(lambda *args: None, telephony=False)
        self.assertEqual(mic.send_rate, 16000)
        self.assertIsNone(mic.phone)
        self.assertEqual(
            stt.headers(mic.lang, mic.send_rate)["x-sample-rate"], "16000")


if __name__ == "__main__":
    unittest.main()
