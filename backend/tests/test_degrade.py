"""Unit tests for harness.degrade — the phone-line simulation. Pure numpy."""
import unittest

import numpy as np

from harness import degrade


def sine(freq, seconds=0.2, rate=16000, amp=10000):
    t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
    return np.sin(2 * np.pi * freq * t) * amp


def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x, dtype=float) ** 2)))


class BandLimitTest(unittest.TestCase):
    def test_passband_survives(self):
        x = sine(1000)
        self.assertGreater(rms(degrade.band_limit(x, 16000)) / rms(x), 0.9)

    def test_stopband_is_removed(self):
        x = sine(6000)
        self.assertLess(rms(degrade.band_limit(x, 16000)) / rms(x), 0.05)

    def test_empty_input(self):
        self.assertEqual(degrade.band_limit(np.array([]), 16000).size, 0)


class ResampleTest(unittest.TestCase):
    def test_halves_the_length(self):
        x = sine(440, rate=16000)
        self.assertEqual(degrade.resample(x, 16000, 8000).size, x.size // 2)

    def test_same_rate_is_identity(self):
        x = sine(440)
        self.assertIs(degrade.resample(x, 16000, 16000), x)


class NoiseTest(unittest.TestCase):
    def test_noise_floor_matches_requested_snr(self):
        x = sine(440)
        out = degrade.add_noise(x, snr_db=10.0, seed=1)
        noise = out - x
        measured = 20 * np.log10(degrade.speech_rms(x) / rms(noise))
        self.assertAlmostEqual(measured, 10.0, delta=1.5)

    def test_louder_request_means_more_noise(self):
        x = sine(440)
        quiet = rms(degrade.add_noise(x, -5, seed=1) - x)
        loud = rms(degrade.add_noise(x, -20, seed=1) - x)
        self.assertGreater(loud, quiet)

    def test_speech_rms_beats_whole_clip_rms(self):
        # half silence, half signal
        x = np.concatenate([np.zeros(16000), sine(440, rate=16000)])
        self.assertGreater(degrade.speech_rms(x), rms(x))


class TelephonyTest(unittest.TestCase):
    def test_output_is_8k_and_same_duration(self):
        x = sine(440, seconds=0.5)
        pcm = np.clip(x, -32768, 32767).astype(np.int16).tobytes()
        out, rate = degrade.telephony(pcm, 16000, snr_db=10.0)
        self.assertEqual(rate, 8000)
        self.assertEqual(len(out), 8000 * 2 * 0.5)   # 0.5 s of 16-bit mono

    def test_noise_can_be_skipped(self):
        pcm = (sine(440) * 3).astype(np.int16).tobytes()
        noisy, _ = degrade.telephony(pcm, 16000, snr_db=-18.0)
        clean, _ = degrade.telephony(pcm, 16000, snr_db=None)
        self.assertGreater(rms(np.frombuffer(noisy, np.int16)),
                           rms(np.frombuffer(clean, np.int16)))


if __name__ == "__main__":
    unittest.main()
