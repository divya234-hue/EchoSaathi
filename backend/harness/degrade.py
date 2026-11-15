"""Telephony degradation: clean studio audio -> what a phone line does to it.

Pure functions over numpy int16 arrays. No network, no state, so it is cheap
to test and easy to change.

A phone line does four things worth simulating separately:
  1. band-limits to ~300-3400 Hz
  2. resamples to 8 kHz
  3. quantises to G.711 µ-law (8 bits, companded)
  4. adds background noise
"""
import numpy as np

from audio import pcm16_to_ulaw, ulaw_to_pcm16

BAND = (300.0, 3400.0)


def _to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float64)


def _to_pcm(x: np.ndarray) -> bytes:
    return np.clip(np.rint(x), -32768, 32767).astype(np.int16).tobytes()


def band_limit(x: np.ndarray, rate: int, band=BAND) -> np.ndarray:
    """Zero every frequency outside `band` using the real FFT."""
    if x.size == 0:
        return x
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(x.size, d=1.0 / rate)
    keep = (freqs >= band[0]) & (freqs <= band[1])
    spec[~keep] = 0
    return np.fft.irfft(spec, n=x.size)


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Linear resample. Safe here because the input is already band-limited."""
    if src == dst or x.size == 0:
        return x
    n = int(round(x.size * dst / src))
    return np.interp(
        np.linspace(0, x.size - 1, n, dtype=np.float64),
        np.arange(x.size, dtype=np.float64),
        x,
    )


def speech_rms(x: np.ndarray, frame: int = 512) -> float:
    """RMS of the loud parts only.

    Dividing by the RMS of the whole clip would quietly inflate the noise
    level, because silence is part of the average. SNR is defined on speech.
    """
    n = x.size // frame
    if n < 2:
        return float(np.sqrt(np.mean(x ** 2))) or 1.0
    frames = x[: n * frame].reshape(n, frame)
    return float(np.percentile(np.sqrt((frames ** 2).mean(axis=1)), 90)) or 1.0


def add_noise(x: np.ndarray, snr_db: float, seed: int = 0) -> np.ndarray:
    """White noise at a given SNR, plus a low rumble (fan / traffic)."""
    if x.size == 0:
        return x
    rng = np.random.default_rng(seed)
    signal_rms = speech_rms(x)
    noise = rng.normal(0.0, 1.0, x.size)
    noise *= signal_rms / (float(np.sqrt(np.mean(noise ** 2))) * 10 ** (snr_db / 20.0))
    rumble = rng.normal(0.0, 1.0, x.size)
    rumble = np.convolve(rumble, np.ones(9) / 9, mode="same")   # low-passed
    rumble *= noise.std() * 0.6
    return x + noise + rumble


def telephony(pcm: bytes, rate: int, snr_db: float | None = -18.0,
              seed: int = 0) -> tuple[bytes, int]:
    """Apply the full phone-line chain. Returns (pcm16 mono, 8000)."""
    x = _to_float(pcm)
    x = band_limit(x, rate)
    x = resample(x, rate, 8000)
    if snr_db is not None:
        x = add_noise(x, snr_db, seed=seed)
    pcm8 = _to_pcm(x)
    pcm8 = ulaw_to_pcm16(pcm16_to_ulaw(pcm8))     # 8-bit companding, both ways
    return pcm8, 8000
